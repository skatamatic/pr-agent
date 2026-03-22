"""
Robust Cache Service - Production-ready caching with proper memory management

Addresses critical issues:
- Cache-through pattern for complete query results
- Memory-based size limits with LRU eviction
- Async locks instead of threading locks
- Cache warming on startup
- Robust error handling and retry mechanisms
- Logs caching with appropriate constraints
"""
import asyncio
import logging
import psutil
import weakref
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Set, Tuple
from dataclasses import dataclass, field
from collections import OrderedDict, defaultdict
import uuid
import sys
from timezone_utils import to_utc_iso

logger = logging.getLogger(__name__)

@dataclass
class CacheEntry:
    """Cache entry with access tracking for LRU"""
    data: Any
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    last_accessed: datetime = field(default_factory=datetime.utcnow)
    access_count: int = field(default=0)
    dirty: bool = field(default=True)
    size_bytes: int = field(default=0)
    
    def __post_init__(self):
        self.size_bytes = self._calculate_size()
        
    def _calculate_size(self) -> int:
        """Estimate memory size of the data"""
        try:
            return sys.getsizeof(self.data) + sys.getsizeof(self.__dict__)
        except:
            return 1024  # Fallback estimate
            
    def mark_accessed(self):
        self.last_accessed = datetime.utcnow()
        self.access_count += 1
        
    def mark_dirty(self):
        self.dirty = True
        self.updated_at = datetime.utcnow()
        self.mark_accessed()

@dataclass
class CacheStats:
    """Cache statistics for monitoring"""
    hits: int = 0
    misses: int = 0
    evictions: int = 0
    memory_usage_bytes: int = 0
    entry_count: int = 0
    last_cleanup: datetime = field(default_factory=datetime.utcnow)
    
    @property
    def hit_rate(self) -> float:
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0.0
        
    @property
    def memory_usage_mb(self) -> float:
        return self.memory_usage_bytes / (1024 * 1024)

class LRUCache:
    """Memory-aware LRU cache with size limits"""
    
    def __init__(self, max_entries: int = 5000, max_memory_mb: int = 128):
        self.max_entries = max_entries
        self.max_memory_bytes = max_memory_mb * 1024 * 1024
        self.entries: OrderedDict[str, CacheEntry] = OrderedDict()
        self.stats = CacheStats()
        self._lock = asyncio.Lock()
        
    async def get(self, key: str) -> Optional[CacheEntry]:
        """Get entry and mark as accessed (LRU)"""
        async with self._lock:
            if key in self.entries:
                entry = self.entries[key]
                entry.mark_accessed()
                # Move to end (most recently used)
                self.entries.move_to_end(key)
                self.stats.hits += 1
                return entry
            else:
                self.stats.misses += 1
                return None
                
    async def put(self, key: str, entry: CacheEntry):
        """Put entry and enforce size limits"""
        async with self._lock:
            # Remove existing entry if present
            if key in self.entries:
                old_entry = self.entries[key]
                self.stats.memory_usage_bytes -= old_entry.size_bytes
                
            # Add new entry
            self.entries[key] = entry
            self.stats.memory_usage_bytes += entry.size_bytes
            self.stats.entry_count = len(self.entries)
            
            # Move to end (most recently used)
            self.entries.move_to_end(key)
            
            # Enforce limits
            await self._enforce_limits()
            
    async def remove(self, key: str) -> bool:
        """Remove entry from cache"""
        async with self._lock:
            if key in self.entries:
                entry = self.entries[key]
                self.stats.memory_usage_bytes -= entry.size_bytes
                del self.entries[key]
                self.stats.entry_count = len(self.entries)
                return True
            return False
            
    async def clear(self):
        """Clear all entries"""
        async with self._lock:
            self.entries.clear()
            self.stats.memory_usage_bytes = 0
            self.stats.entry_count = 0
            
    async def _enforce_limits(self):
        """Enforce memory and count limits with LRU eviction"""
        while (len(self.entries) > self.max_entries or 
               self.stats.memory_usage_bytes > self.max_memory_bytes):
            if not self.entries:
                break
                
            # Remove least recently used (first in OrderedDict)
            key, entry = self.entries.popitem(last=False)
            self.stats.memory_usage_bytes -= entry.size_bytes
            self.stats.evictions += 1
            
        self.stats.entry_count = len(self.entries)

class AsyncPersistenceQueue:
    """Enhanced persistence queue with retry and error handling"""
    
    def __init__(self, database_manager):
        self.database = database_manager
        self.queue = asyncio.Queue()
        self.retry_queue = asyncio.Queue()
        self.running = False
        self.worker_task = None
        self.retry_task = None
        self.failed_operations: List[Dict] = []
        
    async def start(self):
        """Start persistence workers"""
        if not self.running:
            self.running = True
            self.worker_task = asyncio.create_task(self._persistence_worker())
            self.retry_task = asyncio.create_task(self._retry_worker())
            logger.info("Enhanced persistence workers started")
            
    async def stop(self):
        """Stop persistence workers"""
        if self.running:
            # Best-effort flush before stopping workers so in-flight/queued writes
            # (especially lower-priority log entries) are not lost on deploy shutdown.
            flush_result = await self.flush(timeout_seconds=8.0)
            logger.info(
                "Persistence queue flush before stop: processed=%s failed=%s queue_remaining=%s retry_remaining=%s",
                flush_result.get("processed", 0),
                flush_result.get("failed", 0),
                flush_result.get("queue_remaining", 0),
                flush_result.get("retry_remaining", 0),
            )
            self.running = False
            for task in [self.worker_task, self.retry_task]:
                if task:
                    task.cancel()
                    try:
                        await task
                    except asyncio.CancelledError:
                        pass
            logger.info("Enhanced persistence workers stopped")

    async def flush(self, timeout_seconds: float = 8.0) -> Dict[str, int]:
        """
        Best-effort synchronous flush of queued operations to DB.
        Used during shutdown to minimize data loss on fast restarts/deploys.
        """
        deadline = datetime.utcnow() + timedelta(seconds=max(0.1, timeout_seconds))
        processed = 0
        failed_total = 0

        # Let active workers continue; we drain any remaining items ourselves.
        while datetime.utcnow() < deadline:
            operations: List[Dict] = []

            # Prefer retry queue first to avoid starving retries at shutdown.
            while len(operations) < 50:
                try:
                    operations.append(self.retry_queue.get_nowait())
                except asyncio.QueueEmpty:
                    break

            while len(operations) < 50:
                try:
                    operations.append(self.queue.get_nowait())
                except asyncio.QueueEmpty:
                    break

            if not operations:
                # If no items are visible now, queue is effectively drained.
                break

            successful, failed = await self._process_operations_batch(operations)
            processed += len(successful)
            failed_total += len(failed)

            # One immediate retry pass for failed ops during shutdown.
            if failed:
                successful_retry, failed_retry = await self._process_operations_batch(failed)
                processed += len(successful_retry)
                failed_total += len(failed_retry)
                if failed_retry:
                    self.failed_operations.extend(failed_retry)

        return {
            "processed": processed,
            "failed": failed_total,
            "queue_remaining": self.queue.qsize(),
            "retry_remaining": self.retry_queue.qsize(),
        }
            
    async def enqueue_operation(self, operation_type: str, table: str, 
                              data: Dict[str, Any], key: str = None, priority: int = 0):
        """Enqueue operation with priority support"""
        operation = {
            'type': operation_type,
            'table': table,
            'data': data,
            'key': key,
            'timestamp': datetime.utcnow(),
            'priority': priority,
            'retry_count': 0
        }
        await self.queue.put(operation)
        
    async def _persistence_worker(self):
        """Enhanced persistence worker with error handling"""
        while self.running:
            try:
                operations = []
                try:
                    # Get operations with timeout
                    operation = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                    operations.append(operation)
                    
                    # Batch additional operations
                    while len(operations) < 20:  # Larger batch size
                        try:
                            operation = self.queue.get_nowait()
                            operations.append(operation)
                        except asyncio.QueueEmpty:
                            break
                            
                except asyncio.TimeoutError:
                    continue
                
                if operations:
                    # Sort by priority
                    operations.sort(key=lambda x: x.get('priority', 0), reverse=True)
                    success, failed = await self._process_operations_batch(operations)
                    
                    # Queue failed operations for retry
                    for op in failed:
                        op['retry_count'] += 1
                        if op['retry_count'] <= 3:
                            await self.retry_queue.put(op)
                        else:
                            self.failed_operations.append(op)
                            logger.error(f"Operation failed permanently: {op}")
                    
            except Exception as e:
                logger.error(f"Error in enhanced persistence worker: {e}")
                await asyncio.sleep(1)
                
    async def _retry_worker(self):
        """Worker for retrying failed operations"""
        while self.running:
            try:
                await asyncio.sleep(5)  # Wait before retrying
                
                retry_ops = []
                while True:
                    try:
                        op = self.retry_queue.get_nowait()
                        retry_ops.append(op)
                    except asyncio.QueueEmpty:
                        break
                        
                if retry_ops:
                    logger.info(f"Retrying {len(retry_ops)} failed operations")
                    success, failed = await self._process_operations_batch(retry_ops)
                    
                    for op in failed:
                        op['retry_count'] += 1
                        if op['retry_count'] <= 3:
                            await self.retry_queue.put(op)
                        else:
                            self.failed_operations.append(op)
                            
            except Exception as e:
                logger.error(f"Error in retry worker: {e}")
                
    async def _process_operations_batch(self, operations: List[Dict]) -> Tuple[List[Dict], List[Dict]]:
        """Process batch with individual error handling"""
        successful = []
        failed = []
        
        try:
            from database import SessionLocal
            
            db = SessionLocal()
            try:
                for op in operations:
                    try:
                        await self._execute_database_operation(db, op)
                        successful.append(op)
                    except Exception as e:
                        logger.warning(f"Operation failed: {op.get('type')} on {op.get('table')}: {e}")
                        failed.append(op)
                        
                if successful:
                    db.commit()
                    logger.debug(f"Successfully persisted {len(successful)} operations")
                    
            except Exception as e:
                db.rollback()
                logger.error(f"Batch commit failed: {e}")
                failed.extend(successful)  # All operations failed
                successful = []
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Database session error: {e}")
            failed.extend(operations)
            
        return successful, failed
        
    def _convert_datetime_strings(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Convert ISO datetime strings back to datetime objects for SQLAlchemy"""
        datetime_fields = {
            'started_at', 'completed_at', 'last_updated', 'timestamp', 
            'created_at', 'updated_at', 'last_checked', 'last_login'
        }
        
        converted_data = data.copy()
        for field, value in data.items():
            if field in datetime_fields and isinstance(value, str):
                try:
                    # Convert ISO string to datetime object
                    converted_data[field] = datetime.fromisoformat(value.replace('Z', '+00:00'))
                except (ValueError, AttributeError):
                    # If conversion fails, keep original value
                    pass
                    
        return converted_data
        
    async def _execute_database_operation(self, db, operation: Dict):
        """Execute database operation with proper error handling"""
        table = operation['table']
        op_type = operation['type']
        data = self._convert_datetime_strings(operation['data'])  # Convert datetime strings
        key = operation.get('key')
        
        if table == 'jobs':
            await self._handle_job_operation(db, op_type, data, key)
        elif table == 'operations':
            await self._handle_operation_operation(db, op_type, data, key)
        elif table == 'log_entries':
            await self._handle_log_operation(db, op_type, data, key)
        elif table == 'metrics_aggregate':
            await self._handle_metrics_operation(db, op_type, data, key)
        else:
            raise ValueError(f"Unknown table: {table}")
            
    async def _handle_job_operation(self, db, op_type: str, data: Dict, key: str = None):
        """Handle job operations with validation"""
        from models import JobDB
        
        # Filter out invalid fields that don't exist on the model
        valid_fields = {
            'job_id', 'job_type', 'source', 'status', 'repository', 'pr_url', 
            'trigger_user', 'trigger_event', 'installation_id', 'request_id', 
            'webhook_payload', 'started_at', 'completed_at', 'last_updated', 
            'duration', 'operations_count', 'completed_operations', 'failed_operations',
            'total_logs', 'error_count', 'warning_count', 'result_summary', 'error_details'
        }
        
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        
        if op_type == 'insert':
            # Validate required fields
            required_fields = ['job_id', 'job_type', 'source', 'status']
            for field in required_fields:
                if field not in filtered_data:
                    raise ValueError(f"Missing required field: {field}")
            job = JobDB(**filtered_data)
            db.add(job)
        elif op_type == 'update':
            job = db.query(JobDB).filter(JobDB.job_id == filtered_data['job_id']).first()
            if job:
                for field, value in filtered_data.items():
                    if field != 'job_id' and hasattr(job, field):  # Don't update primary key
                        setattr(job, field, value)
        elif op_type == 'delete':
            if key:
                db.query(JobDB).filter(JobDB.job_id == key).delete()
                
    async def _handle_operation_operation(self, db, op_type: str, data: Dict, key: str = None):
        """Handle operation operations with validation"""
        from models import OperationDB
        
        # Filter out invalid fields that don't exist on the model
        valid_fields = {
            'operation_id', 'job_id', 'operation_type', 'command', 'status', 'repo', 
            'pr_url', 'installation_id', 'sender', 'request_id', 'started_at', 
            'last_updated', 'completed_at', 'duration', 'error_details', 'response_time',
            'context_fetch_time', 'ai_processing_time', 'model_used', 'input_tokens',
            'output_tokens', 'estimated_dev_hours_saved', 'suggestions_count', 
            'errors_count', 'warnings_count', 'result_data', 'current_step',
            'ai_models_used', 'total_input_tokens', 'total_output_tokens'
        }
        
        filtered_data = {k: v for k, v in data.items() if k in valid_fields}
        
        if op_type == 'insert':
            required_fields = ['operation_id', 'job_id', 'operation_type', 'command', 'status']
            for field in required_fields:
                if field not in filtered_data:
                    raise ValueError(f"Missing required field: {field}")
            operation = OperationDB(**filtered_data)
            db.add(operation)
        elif op_type == 'update':
            operation = db.query(OperationDB).filter(OperationDB.operation_id == filtered_data['operation_id']).first()
            if operation:
                for field, value in filtered_data.items():
                    if field != 'operation_id' and hasattr(operation, field):  # Don't update primary key
                        setattr(operation, field, value)
        elif op_type == 'delete':
            if key:
                db.query(OperationDB).filter(OperationDB.operation_id == key).delete()
                
    async def _handle_log_operation(self, db, op_type: str, data: Dict, key: str = None):
        """Handle log operations"""
        from models import LogEntryDB
        
        if op_type == 'insert':
            # Map fields correctly for LogEntryDB
            log_data = data.copy()
            
            # Handle 'source' field - map to module/app_name
            if 'source' in log_data:
                source_value = log_data.pop('source')  # Remove source field
                # Use source as module if module is not set
                if not log_data.get('module') and source_value:
                    log_data['module'] = source_value
                # Use source as app_name if app_name is not set 
                if not log_data.get('app_name') and source_value:
                    log_data['app_name'] = source_value
                    
            # Handle 'repository' field - should be 'repo' in database
            if 'repository' in log_data:
                repo_value = log_data.pop('repository')
                if not log_data.get('repo') and repo_value:
                    log_data['repo'] = repo_value
                    
            # Handle 'severity' field - not in database model
            if 'severity' in log_data:
                log_data.pop('severity')
            
            # Always use database-managed IDs for logs.
            # If an ID is present from older callers, drop it to avoid overflow/collisions.
            if 'id' in log_data:
                log_data.pop('id')
                
            # Convert timestamp string to datetime if needed
            if 'timestamp' in log_data and isinstance(log_data['timestamp'], str):
                from datetime import datetime
                try:
                    log_data['timestamp'] = datetime.fromisoformat(log_data['timestamp'].replace('Z', '+00:00'))
                except:
                    log_data['timestamp'] = datetime.utcnow()
                    
            log_entry = LogEntryDB(**log_data)
            db.add(log_entry)
            # Flush so the generated ID is available to the caller before commit.
            db.flush()
            return log_entry.id
        elif op_type == 'delete':
            if key:
                db.query(LogEntryDB).filter(LogEntryDB.id == key).delete()
        return None
                
    async def _handle_metrics_operation(self, db, op_type: str, data: Dict, key: str = None):
        """Handle metrics operations"""
        from models import MetricsAggregateDB
        
        if op_type == 'insert':
            metrics = MetricsAggregateDB(**data)
            db.add(metrics)
        elif op_type == 'update':
            metrics = db.query(MetricsAggregateDB).filter(MetricsAggregateDB.id == data.get('id', 1)).first()
            if metrics:
                for field, value in data.items():
                    if hasattr(metrics, field):
                        setattr(metrics, field, value)

class RobustCacheService:
    """Production-ready cache service with comprehensive features"""
    
    def __init__(self, database_manager):
        self.database = database_manager
        self.persistence_queue = AsyncPersistenceQueue(database_manager)
        
        # Separate caches with different configurations
        self.jobs_cache = LRUCache(max_entries=2000, max_memory_mb=64)
        self.operations_cache = LRUCache(max_entries=5000, max_memory_mb=96) 
        self.logs_cache = LRUCache(max_entries=10000, max_memory_mb=32)  # Smaller per-entry
        self.metrics_cache = LRUCache(max_entries=100, max_memory_mb=8)
        
        # Indexes for fast querying
        self.jobs_by_status: Dict[str, Set[str]] = defaultdict(set)
        self.jobs_by_repository: Dict[str, Set[str]] = defaultdict(set)
        self.operations_by_job: Dict[str, Set[str]] = defaultdict(set)
        self.operations_by_status: Dict[str, Set[str]] = defaultdict(set)
        self.logs_by_job: Dict[str, Set[int]] = defaultdict(set)
        self.logs_by_operation: Dict[str, Set[int]] = defaultdict(set)
        
        # Configuration
        self.cache_ttl = timedelta(hours=24)
        self.warming_enabled = True
        self.circuit_breaker_failures = 0
        self.circuit_breaker_threshold = 5
        self.circuit_breaker_open = False
        
        # Background tasks
        self.cleanup_task = None
        self.monitoring_task = None
        
    async def start(self):
        """Start cache service with warming"""
        await self.persistence_queue.start()
        
        # Start background tasks
        self.cleanup_task = asyncio.create_task(self._cleanup_worker())
        self.monitoring_task = asyncio.create_task(self._monitoring_worker())
        
        # Warm cache if enabled
        if self.warming_enabled:
            await self._warm_cache()
            
        logger.info("Robust cache service started")
        
    async def stop(self):
        """Stop cache service"""
        await self.persistence_queue.stop()
        
        # Cancel background tasks
        for task in [self.cleanup_task, self.monitoring_task]:
            if task:
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
                    
        logger.info("Robust cache service stopped")
        
    async def _warm_cache(self):
        """Warm cache with recent data from database"""
        try:
            logger.info("Warming cache from database...")
            
            from database import SessionLocal
            from models import JobDB, OperationDB, LogEntryDB
            
            db = SessionLocal()
            try:
                # Warm recent jobs (last 30 days)
                cutoff = datetime.utcnow() - timedelta(days=30)
                recent_jobs = db.query(JobDB).filter(
                    JobDB.started_at >= cutoff
                ).order_by(JobDB.started_at.desc()).limit(10000).all()
                
                for job in recent_jobs:
                    job_data = self._job_db_to_dict(job)
                    entry = CacheEntry(data=job_data, dirty=False)
                    await self.jobs_cache.put(job.job_id, entry)
                    await self._update_job_indexes(job.job_id, job_data)
                    
                # Warm recent operations
                recent_ops = db.query(OperationDB).filter(
                    OperationDB.started_at >= cutoff
                ).order_by(OperationDB.started_at.desc()).limit(2000).all()
                
                for op in recent_ops:
                    op_data = self._operation_db_to_dict(op)
                    entry = CacheEntry(data=op_data, dirty=False)
                    await self.operations_cache.put(op.operation_id, entry)
                    await self._update_operation_indexes(op.operation_id, op_data)
                    
                # Warm recent logs (last 7 days only)
                log_cutoff = datetime.utcnow() - timedelta(days=7)
                recent_logs = db.query(LogEntryDB).filter(
                    LogEntryDB.timestamp >= log_cutoff
                ).order_by(LogEntryDB.timestamp.desc()).limit(10000).all()
                
                for log in recent_logs:
                    log_data = self._log_db_to_dict(log)
                    entry = CacheEntry(data=log_data, dirty=False)
                    await self.logs_cache.put(str(log.id), entry)
                    await self._update_log_indexes(log.id, log_data)
                    
                logger.info(f"Cache warmed: {len(recent_jobs)} jobs, {len(recent_ops)} operations, {len(recent_logs)} logs")
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Cache warming failed: {e}")
            # Don't fail startup due to warming issues
            
    def _job_db_to_dict(self, job) -> Dict[str, Any]:
        """Convert JobDB to dictionary"""
        return {
            'job_id': job.job_id,
            'job_type': job.job_type,
            'source': job.source,
            'status': job.status,
            'repository': job.repository,
            'pr_url': job.pr_url,
            'trigger_user': job.trigger_user,
            'trigger_event': job.trigger_event,
            'installation_id': job.installation_id,
            'request_id': job.request_id,
            'webhook_payload': job.webhook_payload,
            'started_at': to_utc_iso(job.started_at),
            'completed_at': to_utc_iso(job.completed_at),
            'last_updated': to_utc_iso(job.last_updated),
            'duration': job.duration,
            'operations_count': job.operations_count,
            'completed_operations': job.completed_operations,
            'failed_operations': job.failed_operations,
            'total_logs': job.total_logs,
            'error_count': job.error_count,
            'warning_count': job.warning_count,
            'result_summary': job.result_summary,
            'error_details': job.error_details
        }
        
    def _operation_db_to_dict(self, operation) -> Dict[str, Any]:
        """Convert OperationDB to dictionary"""
        return {
            'operation_id': operation.operation_id,
            'job_id': operation.job_id,
            'operation_type': operation.operation_type,
            'command': operation.command,
            'status': operation.status,
            'repo': operation.repo,
            'pr_url': operation.pr_url,
            'installation_id': operation.installation_id,
            'sender': operation.sender,
            'request_id': operation.request_id,
            'started_at': to_utc_iso(operation.started_at),
            'completed_at': to_utc_iso(operation.completed_at),
            'last_updated': to_utc_iso(operation.last_updated),
            'duration': operation.duration,
            'error_details': operation.error_details,
            'result_data': operation.result_data,
            'model_used': operation.model_used,
            'input_tokens': operation.input_tokens,
            'output_tokens': operation.output_tokens,
            'estimated_dev_hours_saved': operation.estimated_dev_hours_saved,
            'current_step': operation.current_step,
            'ai_models_used': operation.ai_models_used,
            'total_input_tokens': operation.total_input_tokens,
            'total_output_tokens': operation.total_output_tokens,
            'insights': operation.insights
        }
        
    def _log_db_to_dict(self, log) -> Dict[str, Any]:
        """Convert LogEntryDB to dictionary"""
        return {
            'id': log.id,
            'timestamp': to_utc_iso(log.timestamp),
            'level': log.level,
            'message': log.message,
            'source': log.module or log.app_name or 'unknown',  # Use module or app_name as source
            'job_id': log.job_id,
            'operation_id': log.operation_id,
            # Include both keys to keep client contracts stable.
            'repository': log.repo,
            'repo': log.repo,
            'status': log.status,
            'module': log.module,
            'function': log.function,
            'line': log.line,
            'pr_url': log.pr_url,
            'command': log.command,
            'installation_id': log.installation_id,
            'sender': log.sender,
            'request_id': log.request_id,
            'sub_feature': log.sub_feature,
            'analytics': log.analytics,
            'app_name': log.app_name,
            'git_provider': log.git_provider,
            'artifact': log.artifact,
            'artifacts': log.artifacts,
            'error': log.error,
            'build_number': log.build_number,
            'received_at': log.received_at
        }
        
    async def _update_job_indexes(self, job_id: str, job_data: Dict[str, Any]):
        """Update job indexes"""
        if 'status' in job_data and job_data['status']:
            self.jobs_by_status[job_data['status']].add(job_id)
        if 'repository' in job_data and job_data['repository']:
            self.jobs_by_repository[job_data['repository']].add(job_id)
            
    async def _update_operation_indexes(self, operation_id: str, operation_data: Dict[str, Any]):
        """Update operation indexes"""
        if 'job_id' in operation_data and operation_data['job_id']:
            self.operations_by_job[operation_data['job_id']].add(operation_id)
        if 'status' in operation_data and operation_data['status']:
            self.operations_by_status[operation_data['status']].add(operation_id)
            
    async def _update_log_indexes(self, log_id: int, log_data: Dict[str, Any]):
        """Update log indexes"""
        if 'job_id' in log_data and log_data['job_id']:
            self.logs_by_job[log_data['job_id']].add(log_id)
        if 'operation_id' in log_data and log_data['operation_id']:
            self.logs_by_operation[log_data['operation_id']].add(log_id)
            
    # ============= CACHE-THROUGH JOB OPERATIONS =============
    
    async def create_job(self, job_data: Dict[str, Any]) -> str:
        """Create job with immediate cache storage"""
        job_id = job_data['job_id']
        
        # Add to cache immediately
        entry = CacheEntry(data=job_data.copy())
        await self.jobs_cache.put(job_id, entry)
        await self._update_job_indexes(job_id, job_data)
        
        # Queue for persistence with high priority
        await self.persistence_queue.enqueue_operation('insert', 'jobs', job_data, priority=10)
        
        logger.debug(f"Job {job_id} added to robust cache")
        return job_id
        
    async def update_job(self, job_id: str, updates: Dict[str, Any]) -> bool:
        """Update job with cache-through pattern"""
        # First, get current job (cache or DB)
        current_job = await self.get_job(job_id)
        if not current_job:
            return False
            
        # Apply updates
        updated_job = current_job.copy()
        old_status = updated_job.get('status')
        old_repository = updated_job.get('repository')
        
        updated_job.update(updates)
        updated_job['last_updated'] = to_utc_iso(datetime.utcnow())
        
        # Update cache
        entry = CacheEntry(data=updated_job, dirty=True)
        await self.jobs_cache.put(job_id, entry)
        
        # Update indexes if key fields changed
        if 'status' in updates and updates['status'] != old_status:
            if old_status:
                self.jobs_by_status[old_status].discard(job_id)
            self.jobs_by_status[updates['status']].add(job_id)
            
        if 'repository' in updates and updates['repository'] != old_repository:
            if old_repository:
                self.jobs_by_repository[old_repository].discard(job_id)
            self.jobs_by_repository[updates['repository']].add(job_id)
            
        # Queue for persistence
        await self.persistence_queue.enqueue_operation('update', 'jobs', updated_job, priority=8)
        
        logger.debug(f"Job {job_id} updated in robust cache")
        return True
        
    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get job with cache-through pattern"""
        # Try cache first
        entry = await self.jobs_cache.get(job_id)
        if entry:
            return entry.data.copy()
            
        # Cache miss - try database
        job_data = await self._load_job_from_db(job_id)
        if job_data:
            # Add to cache for future requests
            entry = CacheEntry(data=job_data, dirty=False)
            await self.jobs_cache.put(job_id, entry)
            await self._update_job_indexes(job_id, job_data)
            
        return job_data
        
    async def get_jobs(self, limit: int = 100, status: str = None,
                      repository: str = None, **filters) -> List[Dict[str, Any]]:
        """Get jobs with cache-through pattern - merges cache AND database results"""
        # Get cache results
        cache_results = await self._get_jobs_from_cache(limit, status, repository, **filters)
        cache_job_ids = {job['job_id'] for job in cache_results}
        
        # Get database results
        db_results = await self._get_jobs_from_db(limit, status, repository, **filters)
        
        # Merge results, preferring cache (more up-to-date)
        merged_results = cache_results.copy()
        
        for db_job in db_results:
            if db_job['job_id'] not in cache_job_ids:
                merged_results.append(db_job)
                # Add to cache for future requests
                entry = CacheEntry(data=db_job, dirty=False)
                await self.jobs_cache.put(db_job['job_id'], entry)
                await self._update_job_indexes(db_job['job_id'], db_job)
                
        # Sort by started_at (newest first) and limit
        merged_results.sort(key=lambda x: x.get('started_at', ''), reverse=True)
        return merged_results[:limit]
        
    async def _get_jobs_from_cache(self, limit: int, status: str = None,
                                  repository: str = None, **filters) -> List[Dict[str, Any]]:
        """Get jobs from cache only"""
        # Start with all cached job IDs
        candidate_ids = set()
        
        # Use indexes for filtering
        if status:
            candidate_ids = self.jobs_by_status.get(status, set())
        elif repository:
            candidate_ids = self.jobs_by_repository.get(repository, set())
        else:
            # Get all job IDs from cache
            all_entries = {}
            for cache_name in ['jobs_cache']:
                cache = getattr(self, cache_name)
                async with cache._lock:
                    all_entries.update(cache.entries)
            candidate_ids = set(all_entries.keys())
            
        # Apply additional filters
        results = []
        for job_id in candidate_ids:
            entry = await self.jobs_cache.get(job_id)
            if entry:
                job_data = entry.data
                
                # Apply filters
                matches = True
                if status and job_data.get('status') != status:
                    matches = False
                if repository and job_data.get('repository') != repository:
                    matches = False
                    
                for key, value in filters.items():
                    if key in job_data and job_data[key] != value:
                        matches = False
                        break
                        
                if matches:
                    results.append(job_data.copy())
                    
        return results
        
    async def _get_jobs_from_db(self, limit: int, status: str = None,
                               repository: str = None, **filters) -> List[Dict[str, Any]]:
        """Get jobs from database only"""
        try:
            from database import SessionLocal
            from models import JobDB
            
            db = SessionLocal()
            try:
                query = db.query(JobDB)
                
                # Apply filters
                if status:
                    query = query.filter(JobDB.status == status)
                if repository:
                    query = query.filter(JobDB.repository == repository)
                    
                for key, value in filters.items():
                    if hasattr(JobDB, key):
                        query = query.filter(getattr(JobDB, key) == value)
                        
                # Order and limit
                jobs = query.order_by(JobDB.started_at.desc()).limit(limit * 2).all()  # Get more to account for merging
                
                return [self._job_db_to_dict(job) for job in jobs]
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error loading jobs from database: {e}")
            return []
            
    async def _load_job_from_db(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Load single job from database"""
        try:
            from database import SessionLocal
            from models import JobDB
            
            db = SessionLocal()
            try:
                job = db.query(JobDB).filter(JobDB.job_id == job_id).first()
                if job:
                    return self._job_db_to_dict(job)
                return None
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error loading job {job_id} from database: {e}")
            return None
            
    # ============= CACHE-THROUGH OPERATION OPERATIONS =============
    
    async def create_operation(self, operation_data: Dict[str, Any]) -> str:
        """Create operation with immediate cache storage"""
        operation_id = operation_data['operation_id']
        
        # Add to cache immediately
        entry = CacheEntry(data=operation_data.copy())
        await self.operations_cache.put(operation_id, entry)
        await self._update_operation_indexes(operation_id, operation_data)
        
        # Queue for persistence with high priority
        await self.persistence_queue.enqueue_operation('insert', 'operations', operation_data, priority=10)
        
        logger.debug(f"Operation {operation_id} added to robust cache")
        return operation_id
        
    async def update_operation(self, operation_id: str, updates: Dict[str, Any]) -> bool:
        """Update operation with cache-through pattern"""
        # Get current operation
        current_operation = await self.get_operation(operation_id)
        if not current_operation:
            return False
            
        # Apply updates
        updated_operation = current_operation.copy()
        old_status = updated_operation.get('status')
        old_job_id = updated_operation.get('job_id')
        
        updated_operation.update(updates)
        updated_operation['last_updated'] = to_utc_iso(datetime.utcnow())
        
        # Update cache
        entry = CacheEntry(data=updated_operation, dirty=True)
        await self.operations_cache.put(operation_id, entry)
        
        # Update indexes if key fields changed
        if 'status' in updates and updates['status'] != old_status:
            if old_status:
                self.operations_by_status[old_status].discard(operation_id)
            self.operations_by_status[updates['status']].add(operation_id)
            
        if 'job_id' in updates and updates['job_id'] != old_job_id:
            if old_job_id:
                self.operations_by_job[old_job_id].discard(operation_id)
            self.operations_by_job[updates['job_id']].add(operation_id)
            
        # Queue for persistence
        await self.persistence_queue.enqueue_operation('update', 'operations', updated_operation, priority=8)
        
        logger.debug(f"Operation {operation_id} updated in robust cache")
        return True
        
    async def get_operation(self, operation_id: str) -> Optional[Dict[str, Any]]:
        """Get operation with cache-through pattern"""
        # Try cache first
        entry = await self.operations_cache.get(operation_id)
        if entry:
            return entry.data.copy()
            
        # Cache miss - try database
        operation_data = await self._load_operation_from_db(operation_id)
        if operation_data:
            # Add to cache for future requests
            entry = CacheEntry(data=operation_data, dirty=False)
            await self.operations_cache.put(operation_id, entry)
            await self._update_operation_indexes(operation_id, operation_data)
            
        return operation_data
        
    async def get_operations(self, limit: int = 100, job_id: str = None,
                           status: str = None, **filters) -> List[Dict[str, Any]]:
        """Get operations with cache-through pattern"""
        # Get cache results
        cache_results = await self._get_operations_from_cache(limit, job_id, status, **filters)
        cache_operation_ids = {op['operation_id'] for op in cache_results}
        
        # Get database results
        db_results = await self._get_operations_from_db(limit, job_id, status, **filters)
        
        # Merge results
        merged_results = cache_results.copy()
        
        for db_op in db_results:
            if db_op['operation_id'] not in cache_operation_ids:
                merged_results.append(db_op)
                # Add to cache
                entry = CacheEntry(data=db_op, dirty=False)
                await self.operations_cache.put(db_op['operation_id'], entry)
                await self._update_operation_indexes(db_op['operation_id'], db_op)
                
        # Sort and limit
        merged_results.sort(key=lambda x: x.get('started_at', ''), reverse=True)
        return merged_results[:limit]
        
    async def _get_operations_from_cache(self, limit: int, job_id: str = None,
                                       status: str = None, **filters) -> List[Dict[str, Any]]:
        """Get operations from cache only"""
        candidate_ids = set()
        
        if job_id:
            candidate_ids = self.operations_by_job.get(job_id, set())
        elif status:
            candidate_ids = self.operations_by_status.get(status, set())
        else:
            # Get all operation IDs from cache
            async with self.operations_cache._lock:
                candidate_ids = set(self.operations_cache.entries.keys())
                
        results = []
        for operation_id in candidate_ids:
            entry = await self.operations_cache.get(operation_id)
            if entry:
                operation_data = entry.data
                
                # Apply filters
                matches = True
                if job_id and operation_data.get('job_id') != job_id:
                    matches = False
                if status and operation_data.get('status') != status:
                    matches = False
                    
                for key, value in filters.items():
                    if key in operation_data and operation_data[key] != value:
                        matches = False
                        break
                        
                if matches:
                    results.append(operation_data.copy())
                    
        return results
        
    async def _get_operations_from_db(self, limit: int, job_id: str = None,
                                    status: str = None, **filters) -> List[Dict[str, Any]]:
        """Get operations from database only"""
        try:
            from database import SessionLocal
            from models import OperationDB
            
            db = SessionLocal()
            try:
                query = db.query(OperationDB)
                
                if job_id:
                    query = query.filter(OperationDB.job_id == job_id)
                if status:
                    query = query.filter(OperationDB.status == status)
                    
                for key, value in filters.items():
                    if hasattr(OperationDB, key):
                        query = query.filter(getattr(OperationDB, key) == value)
                        
                operations = query.order_by(OperationDB.started_at.desc()).limit(limit * 2).all()
                
                return [self._operation_db_to_dict(op) for op in operations]
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error loading operations from database: {e}")
            return []
            
    async def _load_operation_from_db(self, operation_id: str) -> Optional[Dict[str, Any]]:
        """Load single operation from database"""
        try:
            from database import SessionLocal
            from models import OperationDB
            
            db = SessionLocal()
            try:
                operation = db.query(OperationDB).filter(OperationDB.operation_id == operation_id).first()
                if operation:
                    return self._operation_db_to_dict(operation)
                return None
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error loading operation {operation_id} from database: {e}")
            return None
            
    async def force_sync_operation_to_db(self, operation_id: str) -> bool:
        """Force immediate sync of operation from cache to database"""
        try:
            # Get operation from cache - FIX: Use correct key format
            entry = await self.operations_cache.get(operation_id)
            if not entry:
                logger.warning(f"Operation {operation_id} not found in cache for force sync")
                return False
                
            operation_data = entry.data
            logger.debug(f"Force syncing operation {operation_id} - has AI metrics: {bool(operation_data.get('model_used') or operation_data.get('input_tokens') or operation_data.get('output_tokens'))}")
            
            # Force immediate database update
            from models import OperationDB
            from database import SessionLocal
            
            db = SessionLocal()
            try:
                operation_db = db.query(OperationDB).filter(OperationDB.operation_id == operation_id).first()
                if operation_db:
                    # Update existing operation
                    valid_fields = {
                        'operation_id', 'job_id', 'operation_type', 'command', 'status', 'repo', 
                        'pr_url', 'installation_id', 'sender', 'request_id', 'started_at', 
                        'last_updated', 'completed_at', 'duration', 'error_details', 'response_time',
                        'context_fetch_time', 'ai_processing_time', 'model_used', 'input_tokens',
                        'output_tokens', 'estimated_dev_hours_saved', 'suggestions_count', 
                        'errors_count', 'warnings_count', 'result_data', 'current_step',
                        'ai_models_used', 'total_input_tokens', 'total_output_tokens', 'insights'
                    }
                    
                    for field, value in operation_data.items():
                        if field in valid_fields and field != 'operation_id' and hasattr(operation_db, field):
                            # Convert datetime strings to datetime objects
                            if field in ['started_at', 'completed_at', 'last_updated'] and isinstance(value, str):
                                try:
                                    value = datetime.fromisoformat(value.replace('Z', '+00:00'))
                                except (ValueError, AttributeError):
                                    pass
                            setattr(operation_db, field, value)
                    
                    db.commit()
                    logger.info(f"✅ Force synced operation {operation_id} to database - AI metrics: model={operation_data.get('model_used')}, tokens={operation_data.get('input_tokens')}/{operation_data.get('output_tokens')}, hours={operation_data.get('estimated_dev_hours_saved')}")
                    
                    # Mark as clean in cache
                    entry.dirty = False
                    return True
                else:
                    logger.warning(f"Operation {operation_id} not found in database for force sync")
                    return False
                    
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to force sync operation {operation_id} to database: {e}")
                return False
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error in force_sync_operation_to_db for {operation_id}: {e}")
            return False
            
    # ============= LOGS CACHING =============
    
    async def create_log(self, log_data: Dict[str, Any]) -> int:
        """Create log entry using DB-generated ID, then cache it"""
        from database import SessionLocal
        
        db = SessionLocal()
        try:
            # Persist immediately so PostgreSQL assigns a safe primary key.
            # Log insert helpers live on AsyncPersistenceQueue (shared with queued writes).
            log_id = await self.persistence_queue._handle_log_operation(db, 'insert', log_data, key=None)
            db.commit()
            
            if log_id is None:
                raise RuntimeError("Database did not return a log ID")
            
            cached_log = log_data.copy()
            cached_log['id'] = log_id
            
            # Add to cache with smaller TTL for logs
            entry = CacheEntry(data=cached_log)
            await self.logs_cache.put(str(log_id), entry)
            await self._update_log_indexes(log_id, cached_log)
            
            logger.debug(f"Log {log_id} persisted and cached")
            return log_id
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
        
    async def get_logs(self, limit: int = 1000, level: str = None, job_id: str = None,
                      operation_id: str = None, **filters) -> List[Dict[str, Any]]:
        """Get logs with cache-through pattern"""
        # Get cache results
        cache_results = await self._get_logs_from_cache(limit, level, job_id, operation_id, **filters)
        
        # Get database results to ensure completeness
        db_results = await self._get_logs_from_db(limit, level, job_id, operation_id, **filters)
        
        # Merge and deduplicate by log ID
        cache_log_ids = {log['id'] for log in cache_results}
        merged_results = cache_results.copy()
        
        for db_log in db_results:
            if db_log['id'] not in cache_log_ids:
                merged_results.append(db_log)
                # Only cache recent logs to avoid memory bloat
                if self._is_recent_log(db_log):
                    entry = CacheEntry(data=db_log, dirty=False)
                    await self.logs_cache.put(str(db_log['id']), entry)
                    await self._update_log_indexes(db_log['id'], db_log)
                    
        # Sort by timestamp (newest first) and limit
        merged_results.sort(key=lambda x: x.get('timestamp', ''), reverse=True)
        return merged_results[:limit]
        
    def _is_recent_log(self, log_data: Dict[str, Any]) -> bool:
        """Check if log is recent enough to cache"""
        try:
            if log_data.get('timestamp'):
                log_time = datetime.fromisoformat(log_data['timestamp'].replace('Z', '+00:00'))
                age = datetime.utcnow() - log_time.replace(tzinfo=None)
                return age < timedelta(hours=6)  # Only cache logs from last 6 hours
        except:
            pass
        return False
        
    async def _get_logs_from_cache(self, limit: int, level: str = None, job_id: str = None,
                                 operation_id: str = None, **filters) -> List[Dict[str, Any]]:
        """Get logs from cache only"""
        candidate_ids = set()
        
        if job_id:
            candidate_ids = self.logs_by_job.get(job_id, set())
        elif operation_id:
            candidate_ids = self.logs_by_operation.get(operation_id, set())
        else:
            # Get all log IDs from cache
            async with self.logs_cache._lock:
                candidate_ids = {int(k) for k in self.logs_cache.entries.keys()}
                
        results = []
        for log_id in candidate_ids:
            entry = await self.logs_cache.get(str(log_id))
            if entry:
                log_data = entry.data
                
                # Apply filters
                matches = True
                if level and log_data.get('level') != level:
                    matches = False
                if job_id and log_data.get('job_id') != job_id:
                    matches = False
                if operation_id and log_data.get('operation_id') != operation_id:
                    matches = False
                    
                for key, value in filters.items():
                    if key == "repository" and value is not None:
                        lr = log_data.get("repository") or log_data.get("repo")
                        if lr != value:
                            matches = False
                            break
                    elif key in log_data and log_data[key] != value:
                        matches = False
                        break
                        
                if matches:
                    results.append(log_data.copy())
                    
        return results
        
    async def _get_logs_from_db(self, limit: int, level: str = None, job_id: str = None,
                              operation_id: str = None, **filters) -> List[Dict[str, Any]]:
        """Get logs from database only"""
        try:
            from database import SessionLocal
            from models import LogEntryDB
            
            db = SessionLocal()
            try:
                query = db.query(LogEntryDB)
                
                if level:
                    query = query.filter(LogEntryDB.level == level)
                if job_id:
                    query = query.filter(LogEntryDB.job_id == job_id)
                if operation_id:
                    query = query.filter(LogEntryDB.operation_id == operation_id)
                    
                for key, value in filters.items():
                    # Model column is `repo`; API / filters use `repository`.
                    if key == "repository" and value is not None:
                        query = query.filter(LogEntryDB.repo == value)
                    elif hasattr(LogEntryDB, key):
                        query = query.filter(getattr(LogEntryDB, key) == value)
                        
                logs = query.order_by(LogEntryDB.timestamp.desc()).limit(limit * 2).all()
                
                return [self._log_db_to_dict(log) for log in logs]
                
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error loading logs from database: {e}")
            return []
            
    # ============= BACKGROUND WORKERS =============
    
    async def _cleanup_worker(self):
        """Background worker for cache cleanup and maintenance"""
        while True:
            try:
                await asyncio.sleep(300)  # Run every 5 minutes
                
                # Clean expired entries
                await self._cleanup_expired_entries()
                
                # Log cache statistics
                await self._log_cache_statistics()
                
                # Check memory usage
                await self._check_memory_pressure()
                
            except Exception as e:
                logger.error(f"Error in cache cleanup worker: {e}")
                
    async def _monitoring_worker(self):
        """Background worker for monitoring and circuit breaker"""
        while True:
            try:
                await asyncio.sleep(60)  # Check every minute
                
                # Reset circuit breaker if enough time has passed
                if self.circuit_breaker_open:
                    self.circuit_breaker_failures = max(0, self.circuit_breaker_failures - 1)
                    if self.circuit_breaker_failures == 0:
                        self.circuit_breaker_open = False
                        logger.info("Cache circuit breaker reset")
                        
                # Monitor failed persistence operations
                failed_count = len(self.persistence_queue.failed_operations)
                if failed_count > 10:
                    logger.warning(f"Cache has {failed_count} permanently failed persistence operations")
                    
            except Exception as e:
                logger.error(f"Error in cache monitoring worker: {e}")
                
    async def _cleanup_expired_entries(self):
        """Clean up expired entries from all caches"""
        from timezone_utils import get_cutoff_datetime
        cutoff = get_cutoff_datetime(days=0, hours=0, minutes=int(self.cache_ttl.total_seconds() / 60))
        
        for cache_name in ['jobs_cache', 'operations_cache', 'logs_cache', 'metrics_cache']:
            cache = getattr(self, cache_name)
            expired_keys = []
            
            async with cache._lock:
                from timezone_utils import safe_datetime_compare
                for key, entry in cache.entries.items():
                    if safe_datetime_compare(entry.created_at, cutoff):
                        expired_keys.append(key)
                        
            for key in expired_keys:
                await cache.remove(key)
                # Also remove from indexes
                if cache_name == 'jobs_cache':
                    await self._remove_job_from_indexes(key)
                elif cache_name == 'operations_cache':
                    await self._remove_operation_from_indexes(key)
                elif cache_name == 'logs_cache':
                    await self._remove_log_from_indexes(int(key))
                    
            if expired_keys:
                logger.debug(f"Cleaned {len(expired_keys)} expired entries from {cache_name}")
                
    async def _remove_job_from_indexes(self, job_id: str):
        """Remove job from all indexes"""
        # Find and remove from status/repository indexes
        for status_set in self.jobs_by_status.values():
            status_set.discard(job_id)
        for repo_set in self.jobs_by_repository.values():
            repo_set.discard(job_id)
            
    async def _remove_operation_from_indexes(self, operation_id: str):
        """Remove operation from all indexes"""
        for job_set in self.operations_by_job.values():
            job_set.discard(operation_id)
        for status_set in self.operations_by_status.values():
            status_set.discard(operation_id)
            
    async def _remove_log_from_indexes(self, log_id: int):
        """Remove log from all indexes"""
        for job_set in self.logs_by_job.values():
            job_set.discard(log_id)
        for op_set in self.logs_by_operation.values():
            op_set.discard(log_id)
            
    async def _log_cache_statistics(self):
        """Log cache statistics for monitoring"""
        total_memory = sum([
            self.jobs_cache.stats.memory_usage_bytes,
            self.operations_cache.stats.memory_usage_bytes,
            self.logs_cache.stats.memory_usage_bytes,
            self.metrics_cache.stats.memory_usage_bytes
        ])
        
        total_entries = sum([
            self.jobs_cache.stats.entry_count,
            self.operations_cache.stats.entry_count,
            self.logs_cache.stats.entry_count,
            self.metrics_cache.stats.entry_count
        ])
        
        logger.info(f"Cache stats: {total_entries} entries, {total_memory/1024/1024:.1f}MB, "
                   f"Jobs hit rate: {self.jobs_cache.stats.hit_rate:.1f}%, "
                   f"Operations hit rate: {self.operations_cache.stats.hit_rate:.1f}%")
                   
    async def _check_memory_pressure(self):
        """Check system memory pressure and adjust cache size if needed"""
        try:
            memory = psutil.virtual_memory()
            if memory.percent > 85:  # High memory usage
                logger.warning(f"High system memory usage: {memory.percent:.1f}%")
                # Reduce cache sizes temporarily
                for cache_name in ['jobs_cache', 'operations_cache', 'logs_cache']:
                    cache = getattr(self, cache_name)
                    cache.max_memory_bytes = int(cache.max_memory_bytes * 0.8)
                    await cache._enforce_limits()
                    
        except Exception as e:
            logger.warning(f"Could not check memory pressure: {e}")
            
    # ============= UTILITY METHODS =============
    
    async def get_cache_statistics(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics"""
        return {
            'jobs': {
                'entries': self.jobs_cache.stats.entry_count,
                'memory_mb': self.jobs_cache.stats.memory_usage_mb,
                'hit_rate': self.jobs_cache.stats.hit_rate,
                'hits': self.jobs_cache.stats.hits,
                'misses': self.jobs_cache.stats.misses,
                'evictions': self.jobs_cache.stats.evictions
            },
            'operations': {
                'entries': self.operations_cache.stats.entry_count,
                'memory_mb': self.operations_cache.stats.memory_usage_mb,
                'hit_rate': self.operations_cache.stats.hit_rate,
                'hits': self.operations_cache.stats.hits,
                'misses': self.operations_cache.stats.misses,
                'evictions': self.operations_cache.stats.evictions
            },
            'logs': {
                'entries': self.logs_cache.stats.entry_count,
                'memory_mb': self.logs_cache.stats.memory_usage_mb,
                'hit_rate': self.logs_cache.stats.hit_rate,
                'hits': self.logs_cache.stats.hits,
                'misses': self.logs_cache.stats.misses,
                'evictions': self.logs_cache.stats.evictions
            },
            'persistence': {
                'queue_size': self.persistence_queue.queue.qsize(),
                'retry_queue_size': self.persistence_queue.retry_queue.qsize(),
                'failed_operations': len(self.persistence_queue.failed_operations),
                'circuit_breaker_open': self.circuit_breaker_open
            }
        }
        
    async def clear_all_data(self):
        """Clear all cached data and queue database deletion"""
        await self.jobs_cache.clear()
        await self.operations_cache.clear()
        await self.logs_cache.clear()
        await self.metrics_cache.clear()
        
        # Clear indexes
        self.jobs_by_status.clear()
        self.jobs_by_repository.clear()
        self.operations_by_job.clear()
        self.operations_by_status.clear()
        self.logs_by_job.clear()
        self.logs_by_operation.clear()
        
        # Queue database deletions with high priority
        await self.persistence_queue.enqueue_operation('delete', 'log_entries', {}, priority=10)
        await self.persistence_queue.enqueue_operation('delete', 'operations', {}, priority=10)
        await self.persistence_queue.enqueue_operation('delete', 'jobs', {}, priority=10)
        
        logger.info("All robust cache data cleared")

# Global cache service instance
robust_cache_service: Optional[RobustCacheService] = None

def get_robust_cache_service() -> RobustCacheService:
    """Get the global robust cache service instance"""
    global robust_cache_service
    if robust_cache_service is None:
        from database import DatabaseManager
        database_manager = DatabaseManager()
        robust_cache_service = RobustCacheService(database_manager)
    return robust_cache_service

async def initialize_robust_cache_service():
    """Initialize and start the robust cache service"""
    global robust_cache_service
    robust_cache_service = get_robust_cache_service()
    await robust_cache_service.start()
    return robust_cache_service

async def shutdown_robust_cache_service():
    """Shutdown the robust cache service"""
    global robust_cache_service
    if robust_cache_service:
        await robust_cache_service.stop()
        robust_cache_service = None 