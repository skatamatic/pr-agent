"""
Robust Cached Job Service - Uses the improved RobustCacheService

This service provides the same interface as the original job service
but uses the robust cache with proper memory management, cache-through
patterns, and comprehensive error handling.
"""
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any
from enum import Enum

from .robust_cache_service import get_robust_cache_service

logger = logging.getLogger(__name__)

from models import JobType, JobStatus, OperationStatus

class RobustCachedJobService:
    """Robust job service with comprehensive caching"""
    
    def __init__(self):
        self.cache = get_robust_cache_service()
        
    async def create_job(self, job_type: JobType, source: str, repository: str = None,
                        pr_url: str = None, trigger_user: str = None, 
                        trigger_event: str = None, installation_id: str = None,
                        request_id: str = None, webhook_payload: dict = None) -> str:
        """Create a new job with robust caching"""
        import uuid
        
        job_id = str(uuid.uuid4())
        now = datetime.utcnow()
        
        job_data = {
            'job_id': job_id,
            'job_type': job_type.value,
            'source': source,
            'status': JobStatus.RUNNING.value,
            'repository': repository,
            'pr_url': pr_url,
            'trigger_user': trigger_user,
            'trigger_event': trigger_event,
            'installation_id': installation_id,
            'request_id': request_id,
            'webhook_payload': webhook_payload,
            'started_at': now.isoformat(),
            'last_updated': now.isoformat(),
            'operations_count': 0,
            'completed_operations': 0,
            'failed_operations': 0,
            'total_logs': 0,
            'error_count': 0,
            'warning_count': 0
        }
        
        await self.cache.create_job(job_data)
        
        logger.info(f"Created job {job_id} of type {job_type.value} for {repository}")
        return job_id
        
    async def create_job_with_data(self, job_data: Dict[str, Any]) -> str:
        """Create a job with custom data (used for test data generation)"""
        # Ensure required fields are present
        if 'job_id' not in job_data:
            import uuid
            job_data['job_id'] = str(uuid.uuid4())
            
        if 'last_updated' not in job_data:
            job_data['last_updated'] = datetime.utcnow().isoformat()
            
        # Create job in cache
        await self.cache.create_job(job_data)
        
        logger.debug(f"Created test job {job_data['job_id']} with custom data")
        return job_data['job_id']
        
    async def create_operation_with_data(self, operation_data: Dict[str, Any]) -> str:
        """Create an operation with custom data (used for test data generation)"""
        # Ensure required fields are present
        if 'operation_id' not in operation_data:
            import uuid
            operation_data['operation_id'] = str(uuid.uuid4())
            
        if 'last_updated' not in operation_data:
            operation_data['last_updated'] = datetime.utcnow().isoformat()
            
        # Create operation in cache
        await self.cache.create_operation(operation_data)
        
        logger.debug(f"Created test operation {operation_data['operation_id']} with custom data")
        return operation_data['operation_id']
        
    async def update_job_status(self, job_id: str, status: JobStatus, 
                               error_details: str = None, result_summary: dict = None):
        """Update job status with robust error handling"""
        updates = {
            'status': status.value,
            'last_updated': datetime.utcnow().isoformat()
        }
        
        if status in [JobStatus.COMPLETED, JobStatus.FAILED]:
            updates['completed_at'] = datetime.utcnow().isoformat()
            
        if error_details:
            updates['error_details'] = error_details
            
        if result_summary:
            updates['result_summary'] = result_summary
            
        success = await self.cache.update_job(job_id, updates)
        
        if success:
            logger.info(f"Job {job_id} status updated to {status.value}")
        else:
            logger.warning(f"Failed to update job {job_id} status")
            
        return success
        
    async def create_operation(self, job_id: str, operation_type: str, command: str,
                              repo: str, pr_url: str = None, installation_id: str = None,
                              sender: str = None, request_id: str = None) -> str:
        """Create a new operation with robust caching"""
        import uuid
        
        operation_id = str(uuid.uuid4())
        now = datetime.utcnow()
        
        operation_data = {
            'operation_id': operation_id,
            'job_id': job_id,
            'operation_type': operation_type,
            'command': command,
            'status': OperationStatus.STARTING.value,
            'repo': repo,
            'pr_url': pr_url,
            'installation_id': installation_id,
            'sender': sender,
            'request_id': request_id,
            'started_at': now.isoformat(),
            'last_updated': now.isoformat()
        }
        
        await self.cache.create_operation(operation_data)
        
        # Update job operations count
        await self._update_job_operation_count(job_id, increment=1)
        
        logger.info(f"Created operation {operation_id} for job {job_id}")
        return operation_id
        
    async def update_operation_status(self, operation_id: str, status: OperationStatus,
                                     error_details: str = None, result_data: dict = None):
        """Update operation status with robust caching"""
        updates = {
            'status': status.value,
            'last_updated': datetime.utcnow().isoformat()
        }
        
        if status in [OperationStatus.COMPLETED, OperationStatus.FAILED]:
            updates['completed_at'] = datetime.utcnow().isoformat()
            
            # Calculate duration if we have started_at
            operation = await self.cache.get_operation(operation_id)
            if operation and operation.get('started_at'):
                try:
                    start_time = datetime.fromisoformat(operation['started_at'])
                    duration = (datetime.utcnow() - start_time).total_seconds()
                    updates['duration'] = duration
                except Exception as e:
                    logger.warning(f"Could not calculate duration for operation {operation_id}: {e}")
                    
        if status == OperationStatus.PROCESSING:
            updates['started_at'] = datetime.utcnow().isoformat()
            
        if error_details:
            updates['error_details'] = error_details
            
        if result_data:
            updates['result_data'] = result_data
            
        success = await self.cache.update_operation(operation_id, updates)
        
        if success:
            # Update job counters
            if status == OperationStatus.COMPLETED:
                await self._update_job_completion_count(operation_id, completed=True)
            elif status == OperationStatus.FAILED:
                await self._update_job_completion_count(operation_id, failed=True)
                
            logger.info(f"Operation {operation_id} status updated to {status.value}")
        else:
            logger.warning(f"Failed to update operation {operation_id} status")
            
        return success
        
    async def update_operation_ai_metrics(self, operation_id: str, model_used: str = None,
                                         input_tokens: int = None, output_tokens: int = None,
                                         estimated_dev_hours_saved: float = None):
        """Update operation AI metrics with robust caching and immediate DB sync"""
        updates = {}
        
        if model_used:
            updates['model_used'] = model_used
        if input_tokens is not None:
            updates['input_tokens'] = input_tokens
        if output_tokens is not None:
            updates['output_tokens'] = output_tokens
        if estimated_dev_hours_saved is not None:
            updates['estimated_dev_hours_saved'] = estimated_dev_hours_saved
            
        if updates:
            updates['last_updated'] = datetime.utcnow().isoformat()
            
            # Update cache first (this will NEVER fail with race conditions!)
            success = await self.cache.update_operation(operation_id, updates)
            
            if success:
                # CRITICAL: Force immediate sync to database for metrics operations
                # This ensures metrics aggregates can be updated immediately
                await self.cache.force_sync_operation_to_db(operation_id)
                logger.info(f"Operation {operation_id} AI metrics updated and synced to DB")
            else:
                logger.warning(f"Operation {operation_id} not found for AI metrics update")
                
            return success
            
        return True
        
    async def create_log_entry(self, level: str, message: str, source: str = None,
                              job_id: str = None, operation_id: str = None,
                              repository: str = None, status: str = None,
                              module: str = None, function: str = None,
                              severity: str = None) -> int:
        """Create log entry with robust caching"""
        log_data = {
            'timestamp': datetime.utcnow().isoformat(),
            'level': level,
            'message': message,
            'source': source,
            'job_id': job_id,
            'operation_id': operation_id,
            'repository': repository,
            'status': status,
            'module': module,
            'function': function,
            'severity': severity
        }
        
        log_id = await self.cache.create_log(log_data)
        
        # Update log counts
        if job_id:
            await self._update_job_log_count(job_id, level)
            
        return log_id
        
    async def get_jobs(self, limit: int = 100, include_operations: bool = False,
                      status: str = None, job_type: str = None, repository: str = None,
                      ensure_counts: bool = True) -> List[Dict[str, Any]]:
        """Get jobs with robust cache-through pattern"""
        filters = {}
        if job_type:
            filters['job_type'] = job_type
            
        # This uses cache-through pattern - gets from both cache AND database
        jobs = await self.cache.get_jobs(
            limit=limit,
            status=status,
            repository=repository,
            **filters
        )
        
        # Include operations if requested
        if include_operations:
            for job in jobs:
                job_id = job['job_id']
                operations = await self.cache.get_operations(job_id=job_id)
                job['operations'] = operations
                
        # Ensure operation counts are accurate if requested
        if ensure_counts:
            for job in jobs:
                await self._ensure_job_counts(job)
                
        return jobs
        
    async def get_job(self, job_id: str, include_operations: bool = True) -> Optional[Dict[str, Any]]:
        """Get a single job with robust cache-through pattern"""
        job = await self.cache.get_job(job_id)
        
        if job and include_operations:
            operations = await self.cache.get_operations(job_id=job_id)
            job['operations'] = operations
            await self._ensure_job_counts(job)
            
        return job
        
    async def get_operations(self, limit: int = 100, status: str = None,
                           repo: str = None) -> List[Dict[str, Any]]:
        """Get operations with robust cache-through pattern"""
        filters = {}
        if repo:
            filters['repo'] = repo
            
        return await self.cache.get_operations(
            limit=limit,
            status=status,
            **filters
        )
        
    async def get_operation(self, operation_id: str) -> Optional[Dict[str, Any]]:
        """Get a single operation with robust cache-through pattern"""
        return await self.cache.get_operation(operation_id)
        
    async def get_logs(self, limit: int = 1000, level: str = None, job_id: str = None,
                      operation_id: str = None, repository: str = None) -> List[Dict[str, Any]]:
        """Get logs with robust cache-through pattern"""
        filters = {}
        if repository:
            filters['repository'] = repository
            
        return await self.cache.get_logs(
            limit=limit,
            level=level,
            job_id=job_id,
            operation_id=operation_id,
            **filters
        )
        
    # ============= HELPER METHODS =============
    
    async def _update_job_operation_count(self, job_id: str, increment: int = 0):
        """Update job operation count"""
        job = await self.cache.get_job(job_id)
        if job:
            current_count = job.get('operations_count', 0)
            updates = {'operations_count': current_count + increment}
            await self.cache.update_job(job_id, updates)
            
    async def _update_job_completion_count(self, operation_id: str, completed: bool = False, failed: bool = False):
        """Update job completion counters"""
        operation = await self.cache.get_operation(operation_id)
        if operation and operation.get('job_id'):
            job_id = operation['job_id']
            job = await self.cache.get_job(job_id)
            if job:
                updates = {}
                if completed:
                    current = job.get('completed_operations', 0)
                    updates['completed_operations'] = current + 1
                if failed:
                    current = job.get('failed_operations', 0)
                    updates['failed_operations'] = current + 1
                    
                if updates:
                    await self.cache.update_job(job_id, updates)
                    
    async def _update_job_log_count(self, job_id: str, level: str):
        """Update job log counters"""
        job = await self.cache.get_job(job_id)
        if job:
            updates = {}
            
            # Increment total logs
            current_total = job.get('total_logs', 0)
            updates['total_logs'] = current_total + 1
            
            # Increment error/warning counts
            if level.upper() in ['ERROR', 'CRITICAL']:
                current_errors = job.get('error_count', 0)
                updates['error_count'] = current_errors + 1
            elif level.upper() == 'WARNING':
                current_warnings = job.get('warning_count', 0)
                updates['warning_count'] = current_warnings + 1
                
            await self.cache.update_job(job_id, updates)
            
    async def _ensure_job_counts(self, job: Dict[str, Any]):
        """Ensure job operation counts are accurate"""
        job_id = job['job_id']
        
        # Get actual operations for this job
        operations = await self.cache.get_operations(job_id=job_id, limit=1000)
        
        # Count operations by status
        total_ops = len(operations)
        completed_ops = len([op for op in operations if op.get('status') == 'completed'])
        failed_ops = len([op for op in operations if op.get('status') == 'failed'])
        
        # Update job if counts are wrong
        if (job.get('operations_count', 0) != total_ops or
            job.get('completed_operations', 0) != completed_ops or
            job.get('failed_operations', 0) != failed_ops):
            
            updates = {
                'operations_count': total_ops,
                'completed_operations': completed_ops,
                'failed_operations': failed_ops
            }
            await self.cache.update_job(job_id, updates)
            
            # Update the job dict for the caller
            job.update(updates)
            
    # ============= DEVELOPER TOOLS =============
    
    async def clear_all_data(self):
        """Clear all data from cache and database"""
        try:
            # First clear cache
            await self.cache.clear_all_data()
            
            # Then clear database directly
            from database import SessionLocal
            from models import JobDB, OperationDB, LogEntryDB, NotificationEventDB, HealthCacheDB, MetricsAggregateDB
            
            db = SessionLocal()
            try:
                # Count records before deletion for logging
                jobs_count = db.query(JobDB).count()
                operations_count = db.query(OperationDB).count()  
                logs_count = db.query(LogEntryDB).count()
                notification_events_count = db.query(NotificationEventDB).count()
                health_cache_count = db.query(HealthCacheDB).count()
                metrics_aggregate_count = db.query(MetricsAggregateDB).count()
                
                # Delete in order due to foreign key constraints
                db.query(LogEntryDB).delete()
                db.query(OperationDB).delete()
                db.query(JobDB).delete()
                db.query(NotificationEventDB).delete()
                db.query(HealthCacheDB).delete()
                db.query(MetricsAggregateDB).delete()
                
                db.commit()
                
                total_cleared = jobs_count + operations_count + logs_count + notification_events_count + health_cache_count + metrics_aggregate_count
                
                logger.info(f"All data cleared: {jobs_count} jobs, {operations_count} operations, {logs_count} logs, "
                           f"{notification_events_count} notification events, {health_cache_count} health cache entries, "
                           f"and {metrics_aggregate_count} metrics aggregates ({total_cleared} total records) from both cache and database")
                           
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to clear database: {e}")
                raise
            finally:
                db.close()
                
        except Exception as e:
            logger.error(f"Failed to clear all data: {e}")
            raise
        
    async def delete_test_data(self, repository_pattern: str = "test/%"):
        """Delete test data"""
        # Get all jobs that match the test pattern
        all_jobs = await self.cache.get_jobs(limit=10000)
        test_job_ids = []
        
        for job in all_jobs:
            repo = job.get('repository', '')
            if repo.startswith('test/'):
                test_job_ids.append(job['job_id'])
                
        # Delete operations for test jobs
        for job_id in test_job_ids:
            operations = await self.cache.get_operations(job_id=job_id)
            for operation in operations:
                # Delete operation logs first
                logs = await self.cache.get_logs(operation_id=operation['operation_id'])
                for log in logs:
                    await self.cache.logs_cache.remove(str(log['id']))
                    
                # Delete operation
                await self.cache.operations_cache.remove(operation['operation_id'])
                
            # Delete job logs
            logs = await self.cache.get_logs(job_id=job_id)
            for log in logs:
                await self.cache.logs_cache.remove(str(log['id']))
                
            # Delete job
            await self.cache.jobs_cache.remove(job_id)
            
        logger.info(f"Deleted {len(test_job_ids)} test jobs and associated data")
        
    async def get_cache_statistics(self) -> Dict[str, Any]:
        """Get comprehensive cache statistics"""
        return await self.cache.get_cache_statistics()

# Global instance
robust_cached_job_service: Optional[RobustCachedJobService] = None

def get_robust_cached_job_service() -> RobustCachedJobService:
    """Get the global robust cached job service instance"""
    global robust_cached_job_service
    if robust_cached_job_service is None:
        robust_cached_job_service = RobustCachedJobService()
    return robust_cached_job_service 