"""
Cache Service - Transparent caching layer for dashboard data

Provides immediate data consistency by maintaining an in-memory cache
while handling database persistence asynchronously in the background.
"""
import asyncio
import threading
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Callable
from dataclasses import dataclass, field
from collections import defaultdict
import uuid

logger = logging.getLogger(__name__)

@dataclass
class CacheEntry:
    """Single cache entry with metadata"""
    data: Any
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
    dirty: bool = field(default=True)  # Needs to be persisted to DB
    
    def mark_dirty(self):
        self.dirty = True
        self.updated_at = datetime.utcnow()

class AsyncPersistenceQueue:
    """Handles async database persistence"""
    
    def __init__(self, database_manager):
        self.database = database_manager
        self.queue = asyncio.Queue()
        self.running = False
        self.worker_task = None
        
    async def start(self):
        """Start the async persistence worker"""
        if not self.running:
            self.running = True
            self.worker_task = asyncio.create_task(self._persistence_worker())
            logger.info("Cache persistence worker started")
            
    async def stop(self):
        """Stop the async persistence worker"""
        if self.running:
            self.running = False
            if self.worker_task:
                self.worker_task.cancel()
                try:
                    await self.worker_task
                except asyncio.CancelledError:
                    pass
            logger.info("Cache persistence worker stopped")
            
    async def enqueue_operation(self, operation_type: str, table: str, data: Dict[str, Any], key: str = None):
        """Enqueue a database operation"""
        operation = {
            'type': operation_type,  # 'insert', 'update', 'delete'
            'table': table,
            'data': data,
            'key': key,
            'timestamp': datetime.utcnow()
        }
        await self.queue.put(operation)
        
    async def _persistence_worker(self):
        """Background worker that processes database operations"""
        while self.running:
            try:
                # Process operations in batches for efficiency
                operations = []
                try:
                    # Get first operation (blocking)
                    operation = await asyncio.wait_for(self.queue.get(), timeout=1.0)
                    operations.append(operation)
                    
                    # Get additional operations (non-blocking)
                    while len(operations) < 10:  # Batch size limit
                        try:
                            operation = self.queue.get_nowait()
                            operations.append(operation)
                        except asyncio.QueueEmpty:
                            break
                            
                except asyncio.TimeoutError:
                    continue  # No operations to process
                
                if operations:
                    await self._process_operations_batch(operations)
                    
            except Exception as e:
                logger.error(f"Error in persistence worker: {e}")
                await asyncio.sleep(1)  # Brief pause on error
                
    async def _process_operations_batch(self, operations: List[Dict]):
        """Process a batch of database operations"""
        try:
            # Group operations by table for efficient processing
            by_table = defaultdict(list)
            for op in operations:
                by_table[op['table']].append(op)
            
            # Process each table's operations
            for table, table_ops in by_table.items():
                await self._process_table_operations(table, table_ops)
                
            logger.debug(f"Processed {len(operations)} cache persistence operations")
            
        except Exception as e:
            logger.error(f"Error processing operations batch: {e}")
            
    async def _process_table_operations(self, table: str, operations: List[Dict]):
        """Process operations for a specific table"""
        try:
            # Import database session
            from database import SessionLocal
            
            db = SessionLocal()
            try:
                for op in operations:
                    await self._execute_database_operation(db, op)
                db.commit()
            except Exception as e:
                db.rollback()
                logger.error(f"Database operation failed for table {table}: {e}")
                raise
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error processing table {table} operations: {e}")
            
    async def _execute_database_operation(self, db, operation: Dict):
        """Execute a single database operation"""
        try:
            table = operation['table']
            op_type = operation['type']
            data = operation['data']
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
                logger.warning(f"Unknown table for cache persistence: {table}")
                
        except Exception as e:
            logger.error(f"Error executing database operation: {e}")
            raise
            
    async def _handle_job_operation(self, db, op_type: str, data: Dict, key: str = None):
        """Handle job table operations"""
        from models import JobDB
        
        if op_type == 'insert':
            job = JobDB(**data)
            db.add(job)
        elif op_type == 'update':
            job = db.query(JobDB).filter(JobDB.job_id == data['job_id']).first()
            if job:
                for field, value in data.items():
                    if hasattr(job, field):
                        setattr(job, field, value)
        elif op_type == 'delete':
            if key:
                db.query(JobDB).filter(JobDB.job_id == key).delete()
            else:
                # Delete all matching criteria
                query = db.query(JobDB)
                for field, value in data.items():
                    if hasattr(JobDB, field):
                        query = query.filter(getattr(JobDB, field) == value)
                query.delete()
                
    async def _handle_operation_operation(self, db, op_type: str, data: Dict, key: str = None):
        """Handle operation table operations"""
        from models import OperationDB
        
        if op_type == 'insert':
            operation = OperationDB(**data)
            db.add(operation)
        elif op_type == 'update':
            operation = db.query(OperationDB).filter(OperationDB.operation_id == data['operation_id']).first()
            if operation:
                for field, value in data.items():
                    if hasattr(operation, field):
                        setattr(operation, field, value)
        elif op_type == 'delete':
            if key:
                db.query(OperationDB).filter(OperationDB.operation_id == key).delete()
            else:
                query = db.query(OperationDB)
                for field, value in data.items():
                    if hasattr(OperationDB, field):
                        query = query.filter(getattr(OperationDB, field) == value)
                query.delete()
                
    async def _handle_log_operation(self, db, op_type: str, data: Dict, key: str = None):
        """Handle log entry table operations"""
        from models import LogEntryDB
        
        if op_type == 'insert':
            log_entry = LogEntryDB(**data)
            db.add(log_entry)
        elif op_type == 'delete':
            if key:
                db.query(LogEntryDB).filter(LogEntryDB.id == key).delete()
            else:
                query = db.query(LogEntryDB)
                for field, value in data.items():
                    if hasattr(LogEntryDB, field):
                        query = query.filter(getattr(LogEntryDB, field) == value)
                query.delete()
                
    async def _handle_metrics_operation(self, db, op_type: str, data: Dict, key: str = None):
        """Handle metrics aggregate table operations"""
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

class CacheService:
    """Main cache service providing transparent caching layer"""
    
    def __init__(self, database_manager):
        self.database = database_manager
        self.persistence_queue = AsyncPersistenceQueue(database_manager)
        
        # In-memory caches
        self.jobs_cache: Dict[str, CacheEntry] = {}  # job_id -> CacheEntry
        self.operations_cache: Dict[str, CacheEntry] = {}  # operation_id -> CacheEntry  
        self.logs_cache: Dict[int, CacheEntry] = {}  # log_id -> CacheEntry
        self.metrics_cache: Dict[str, CacheEntry] = {}  # key -> CacheEntry
        
        # Cache indexes for efficient querying
        self.jobs_by_status: Dict[str, set] = defaultdict(set)
        self.jobs_by_repository: Dict[str, set] = defaultdict(set)
        self.operations_by_job: Dict[str, set] = defaultdict(set)
        self.operations_by_status: Dict[str, set] = defaultdict(set)
        self.logs_by_job: Dict[str, set] = defaultdict(set)
        self.logs_by_operation: Dict[str, set] = defaultdict(set)
        
        # Cache configuration
        self.cache_ttl = timedelta(hours=24)  # Cache entries expire after 24 hours
        self.max_cache_size = 10000  # Maximum entries per cache
        
        # Threading lock for cache operations
        self._lock = threading.RLock()
        
    async def start(self):
        """Start the cache service"""
        await self.persistence_queue.start()
        logger.info("Cache service started")
        
    async def stop(self):
        """Stop the cache service"""
        await self.persistence_queue.stop()
        logger.info("Cache service stopped")
        
    def _cleanup_expired_entries(self):
        """Remove expired cache entries"""
        cutoff = datetime.utcnow() - self.cache_ttl
        
        with self._lock:
            # Clean jobs cache
            expired_jobs = [job_id for job_id, entry in self.jobs_cache.items() 
                           if entry.created_at < cutoff]
            for job_id in expired_jobs:
                self._remove_job_from_cache(job_id)
                
            # Clean operations cache  
            expired_ops = [op_id for op_id, entry in self.operations_cache.items()
                          if entry.created_at < cutoff]
            for op_id in expired_ops:
                self._remove_operation_from_cache(op_id)
                
            # Clean logs cache
            expired_logs = [log_id for log_id, entry in self.logs_cache.items()
                           if entry.created_at < cutoff]
            for log_id in expired_logs:
                self._remove_log_from_cache(log_id)
                
    def _limit_cache_size(self):
        """Ensure cache doesn't exceed size limits"""
        with self._lock:
            if len(self.jobs_cache) > self.max_cache_size:
                # Remove oldest entries
                sorted_jobs = sorted(self.jobs_cache.items(), 
                                   key=lambda x: x[1].created_at)
                to_remove = len(self.jobs_cache) - self.max_cache_size + 100
                for job_id, _ in sorted_jobs[:to_remove]:
                    self._remove_job_from_cache(job_id)
                    
    # ============= JOB OPERATIONS =============
    
    async def create_job(self, job_data: Dict[str, Any]) -> str:
        """Create a new job in cache and queue for persistence"""
        job_id = job_data['job_id']
        
        with self._lock:
            # Add to cache immediately
            entry = CacheEntry(data=job_data.copy())
            self.jobs_cache[job_id] = entry
            
            # Update indexes
            if 'status' in job_data:
                self.jobs_by_status[job_data['status']].add(job_id)
            if 'repository' in job_data:
                self.jobs_by_repository[job_data['repository']].add(job_id)
                
        # Queue for async persistence
        await self.persistence_queue.enqueue_operation('insert', 'jobs', job_data)
        
        logger.debug(f"Job {job_id} added to cache")
        return job_id
        
    async def update_job(self, job_id: str, updates: Dict[str, Any]) -> bool:
        """Update a job in cache and queue for persistence"""
        with self._lock:
            if job_id not in self.jobs_cache:
                # Job not in cache, try to load from database
                await self._load_job_from_db(job_id)
                
            if job_id in self.jobs_cache:
                entry = self.jobs_cache[job_id]
                old_data = entry.data.copy()
                
                # Update cache
                entry.data.update(updates)
                entry.mark_dirty()
                
                # Update indexes if status or repository changed
                if 'status' in updates and 'status' in old_data:
                    self.jobs_by_status[old_data['status']].discard(job_id)
                    self.jobs_by_status[updates['status']].add(job_id)
                    
                if 'repository' in updates and 'repository' in old_data:
                    self.jobs_by_repository[old_data['repository']].discard(job_id)
                    self.jobs_by_repository[updates['repository']].add(job_id)
                    
                # Queue for persistence
                persistence_data = entry.data.copy()
                await self.persistence_queue.enqueue_operation('update', 'jobs', persistence_data)
                
                logger.debug(f"Job {job_id} updated in cache")
                return True
                
        return False
        
    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get a job from cache or database"""
        with self._lock:
            if job_id in self.jobs_cache:
                return self.jobs_cache[job_id].data.copy()
                
        # Not in cache, try database
        await self._load_job_from_db(job_id)
        
        with self._lock:
            if job_id in self.jobs_cache:
                return self.jobs_cache[job_id].data.copy()
                
        return None
        
    async def get_jobs(self, limit: int = 100, status: str = None, 
                      repository: str = None, **filters) -> List[Dict[str, Any]]:
        """Get jobs from cache with filtering"""
        with self._lock:
            # Start with all jobs
            candidate_ids = set(self.jobs_cache.keys())
            
            # Apply filters using indexes
            if status:
                candidate_ids &= self.jobs_by_status.get(status, set())
            if repository:
                candidate_ids &= self.jobs_by_repository.get(repository, set())
                
            # Apply additional filters
            results = []
            for job_id in candidate_ids:
                job_data = self.jobs_cache[job_id].data
                
                # Check additional filters
                matches = True
                for key, value in filters.items():
                    if key in job_data and job_data[key] != value:
                        matches = False
                        break
                        
                if matches:
                    results.append(job_data.copy())
                    
            # Sort by creation time (oldest first)
            results.sort(key=lambda x: x.get('started_at', ''), reverse=False)
            
            return results[:limit]
            
    async def delete_job(self, job_id: str) -> bool:
        """Delete a job from cache and queue for persistence"""
        with self._lock:
            if job_id in self.jobs_cache:
                self._remove_job_from_cache(job_id)
                
        # Queue for persistence
        await self.persistence_queue.enqueue_operation('delete', 'jobs', {}, job_id)
        
        logger.debug(f"Job {job_id} deleted from cache")
        return True
        
    def _remove_job_from_cache(self, job_id: str):
        """Remove job from cache and all indexes"""
        if job_id in self.jobs_cache:
            job_data = self.jobs_cache[job_id].data
            
            # Remove from indexes
            if 'status' in job_data:
                self.jobs_by_status[job_data['status']].discard(job_id)
            if 'repository' in job_data:
                self.jobs_by_repository[job_data['repository']].discard(job_id)
                
            # Remove from cache
            del self.jobs_cache[job_id]
            
    async def _load_job_from_db(self, job_id: str):
        """Load a job from database into cache"""
        try:
            from database import SessionLocal
            from models import JobDB
            
            db = SessionLocal()
            try:
                job = db.query(JobDB).filter(JobDB.job_id == job_id).first()
                if job:
                    job_data = {
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
                        'started_at': job.started_at.isoformat() if job.started_at else None,
                        'completed_at': job.completed_at.isoformat() if job.completed_at else None,
                        'last_updated': job.last_updated.isoformat() if job.last_updated else None,
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
                    
                    with self._lock:
                        entry = CacheEntry(data=job_data, dirty=False)
                        self.jobs_cache[job_id] = entry
                        
                        # Update indexes
                        if job_data.get('status'):
                            self.jobs_by_status[job_data['status']].add(job_id)
                        if job_data.get('repository'):
                            self.jobs_by_repository[job_data['repository']].add(job_id)
                            
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error loading job {job_id} from database: {e}")
            
    # ============= OPERATION OPERATIONS =============
    
    async def create_operation(self, operation_data: Dict[str, Any]) -> str:
        """Create a new operation in cache and queue for persistence"""
        operation_id = operation_data['operation_id']
        
        with self._lock:
            # Add to cache immediately
            entry = CacheEntry(data=operation_data.copy())
            self.operations_cache[operation_id] = entry
            
            # Update indexes
            if 'job_id' in operation_data:
                self.operations_by_job[operation_data['job_id']].add(operation_id)
            if 'status' in operation_data:
                self.operations_by_status[operation_data['status']].add(operation_id)
                
        # Queue for async persistence
        await self.persistence_queue.enqueue_operation('insert', 'operations', operation_data)
        
        logger.debug(f"Operation {operation_id} added to cache")
        return operation_id
        
    async def update_operation(self, operation_id: str, updates: Dict[str, Any]) -> bool:
        """Update an operation in cache and queue for persistence"""
        with self._lock:
            if operation_id not in self.operations_cache:
                # Operation not in cache, try to load from database
                await self._load_operation_from_db(operation_id)
                
            if operation_id in self.operations_cache:
                entry = self.operations_cache[operation_id]
                old_data = entry.data.copy()
                
                # Update cache
                entry.data.update(updates)
                entry.mark_dirty()
                
                # Update indexes if status changed
                if 'status' in updates and 'status' in old_data:
                    self.operations_by_status[old_data['status']].discard(operation_id)
                    self.operations_by_status[updates['status']].add(operation_id)
                    
                # Queue for persistence
                persistence_data = entry.data.copy()
                await self.persistence_queue.enqueue_operation('update', 'operations', persistence_data)
                
                logger.debug(f"Operation {operation_id} updated in cache")
                return True
                
        return False
        
    async def get_operation(self, operation_id: str) -> Optional[Dict[str, Any]]:
        """Get an operation from cache or database"""
        with self._lock:
            if operation_id in self.operations_cache:
                return self.operations_cache[operation_id].data.copy()
                
        # Not in cache, try database
        await self._load_operation_from_db(operation_id)
        
        with self._lock:
            if operation_id in self.operations_cache:
                return self.operations_cache[operation_id].data.copy()
                
        return None
        
    async def get_operations(self, limit: int = 100, job_id: str = None,
                           status: str = None, **filters) -> List[Dict[str, Any]]:
        """Get operations from cache with filtering"""
        with self._lock:
            # Start with all operations
            candidate_ids = set(self.operations_cache.keys())
            
            # Apply filters using indexes
            if job_id:
                candidate_ids &= self.operations_by_job.get(job_id, set())
            if status:
                candidate_ids &= self.operations_by_status.get(status, set())
                
            # Apply additional filters
            results = []
            for operation_id in candidate_ids:
                operation_data = self.operations_cache[operation_id].data
                
                # Check additional filters
                matches = True
                for key, value in filters.items():
                    if key in operation_data and operation_data[key] != value:
                        matches = False
                        break
                        
                if matches:
                    results.append(operation_data.copy())
                    
            # Sort by creation time (oldest first)
            results.sort(key=lambda x: x.get('started_at', ''), reverse=False)
            
            return results[:limit]
            
    async def _load_operation_from_db(self, operation_id: str):
        """Load an operation from database into cache"""
        try:
            from database import SessionLocal
            from models import OperationDB
            
            db = SessionLocal()
            try:
                operation = db.query(OperationDB).filter(OperationDB.operation_id == operation_id).first()
                if operation:
                    operation_data = {
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
                        'started_at': operation.started_at.isoformat() if operation.started_at else None,
                        'completed_at': operation.completed_at.isoformat() if operation.completed_at else None,
                        'last_updated': operation.last_updated.isoformat() if operation.last_updated else None,
                        'duration': operation.duration,
                        'error_details': operation.error_details,
                        'result_data': operation.result_data,
                        'model_used': operation.model_used,
                        'input_tokens': operation.input_tokens,
                        'output_tokens': operation.output_tokens,
                        'estimated_dev_hours_saved': operation.estimated_dev_hours_saved
                    }
                    
                    with self._lock:
                        entry = CacheEntry(data=operation_data, dirty=False)
                        self.operations_cache[operation_id] = entry
                        
                        # Update indexes
                        if operation_data.get('job_id'):
                            self.operations_by_job[operation_data['job_id']].add(operation_id)
                        if operation_data.get('status'):
                            self.operations_by_status[operation_data['status']].add(operation_id)
                            
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Error loading operation {operation_id} from database: {e}")
            
    # ============= BULK OPERATIONS FOR DEV TOOLS =============
    
    async def clear_all_data(self):
        """Clear all cached data and queue database deletion"""
        with self._lock:
            # Clear all caches
            self.jobs_cache.clear()
            self.operations_cache.clear() 
            self.logs_cache.clear()
            self.metrics_cache.clear()
            
            # Clear all indexes
            self.jobs_by_status.clear()
            self.jobs_by_repository.clear()
            self.operations_by_job.clear()
            self.operations_by_status.clear()
            self.logs_by_job.clear()
            self.logs_by_operation.clear()
            
        # Queue database deletions
        await self.persistence_queue.enqueue_operation('delete', 'log_entries', {})
        await self.persistence_queue.enqueue_operation('delete', 'operations', {})
        await self.persistence_queue.enqueue_operation('delete', 'jobs', {})
        
        logger.info("All cache data cleared")
        
    async def delete_test_data(self, repository_pattern: str = "test/%"):
        """Delete test data from cache and database"""
        with self._lock:
            # Find test jobs to delete
            test_job_ids = []
            for job_id, entry in list(self.jobs_cache.items()):
                repo = entry.data.get('repository', '')
                if repo.startswith('test/'):
                    test_job_ids.append(job_id)
                    self._remove_job_from_cache(job_id)
                    
            # Find test operations to delete
            test_op_ids = []
            for op_id, entry in list(self.operations_cache.items()):
                repo = entry.data.get('repo', '')
                if repo.startswith('test/') or entry.data.get('job_id') in test_job_ids:
                    test_op_ids.append(op_id)
                    self._remove_operation_from_cache(op_id)
                    
        # Queue database deletions
        for job_id in test_job_ids:
            await self.persistence_queue.enqueue_operation('delete', 'jobs', {}, job_id)
        for op_id in test_op_ids:
            await self.persistence_queue.enqueue_operation('delete', 'operations', {}, op_id)
            
        logger.info(f"Deleted {len(test_job_ids)} test jobs and {len(test_op_ids)} test operations from cache")
        
    def _remove_operation_from_cache(self, operation_id: str):
        """Remove operation from cache and all indexes"""
        if operation_id in self.operations_cache:
            operation_data = self.operations_cache[operation_id].data
            
            # Remove from indexes
            if 'job_id' in operation_data:
                self.operations_by_job[operation_data['job_id']].discard(operation_id)
            if 'status' in operation_data:
                self.operations_by_status[operation_data['status']].discard(operation_id)
                
            # Remove from cache
            del self.operations_cache[operation_id]

# Global cache service instance
cache_service: Optional[CacheService] = None

def get_cache_service() -> CacheService:
    """Get the global cache service instance"""
    global cache_service
    if cache_service is None:
        from database import DatabaseManager
        database_manager = DatabaseManager()
        cache_service = CacheService(database_manager)
    return cache_service

async def initialize_cache_service():
    """Initialize and start the cache service"""
    global cache_service
    cache_service = get_cache_service()
    await cache_service.start()
    return cache_service

async def shutdown_cache_service():
    """Shutdown the cache service"""
    global cache_service
    if cache_service:
        await cache_service.stop()
        cache_service = None 