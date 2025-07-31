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
from timezone_utils import to_utc_iso

logger = logging.getLogger(__name__)

from models import JobType, JobStatus, OperationStatus

class RobustCachedJobService:
    """Robust job service with comprehensive caching"""
    
    def __init__(self, notification_service=None):
        self.cache = get_robust_cache_service()
        self.notification_service = notification_service
        
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
            'started_at': to_utc_iso(now),
            'last_updated': to_utc_iso(now),
            'operations_count': 0,
            'completed_operations': 0,
            'failed_operations': 0,
            'total_logs': 0,
            'error_count': 0,
            'warning_count': 0
        }
        
        await self.cache.create_job(job_data)
        
        # Trigger new job notification
        self._trigger_job_notification(job_data, None, JobStatus.RUNNING.value)
        
        logger.info(f"Created job {job_id} of type {job_type.value} for {repository}")
        return job_id
        
    async def create_job_with_data(self, job_data: Dict[str, Any]) -> str:
        """Create a job with custom data (used for test data generation)"""
        # Ensure required fields are present
        if 'job_id' not in job_data:
            import uuid
            job_data['job_id'] = str(uuid.uuid4())
            
        if 'last_updated' not in job_data:
            job_data['last_updated'] = to_utc_iso(datetime.utcnow())
            
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
            operation_data['last_updated'] = to_utc_iso(datetime.utcnow())
            
        # Create operation in cache
        await self.cache.create_operation(operation_data)
        
        logger.debug(f"Created test operation {operation_data['operation_id']} with custom data")
        return operation_data['operation_id']
        
    async def update_job_status(self, job_id: str, status: JobStatus, 
                               error_details: str = None, result_summary: dict = None):
        """Update job status with robust error handling"""
        # Get current job data for old status and notification
        old_job_data = await self.cache.get_job(job_id)
        old_status = old_job_data.get('status') if old_job_data else None
        
        updates = {
            'status': status.value,
            'last_updated': to_utc_iso(datetime.utcnow())
        }
        
        if status in [JobStatus.COMPLETED, JobStatus.FAILED]:
            updates['completed_at'] = to_utc_iso(datetime.utcnow())
            
        if error_details:
            updates['error_details'] = error_details
            
        if result_summary:
            updates['result_summary'] = result_summary
            
        success = await self.cache.update_job(job_id, updates)
        
        if success:
            # Get updated job data for notification
            updated_job_data = await self.cache.get_job(job_id)
            if updated_job_data:
                # Trigger notification for status change
                self._trigger_job_notification(updated_job_data, old_status, status.value)
            
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
            'started_at': to_utc_iso(now),
            'last_updated': to_utc_iso(now)
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
            'last_updated': to_utc_iso(datetime.utcnow())
        }
        
        if status in [OperationStatus.COMPLETED, OperationStatus.FAILED]:
            updates['completed_at'] = to_utc_iso(datetime.utcnow())
            # Clear current step when operation completes or fails
            updates['current_step'] = None
            
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
            updates['started_at'] = to_utc_iso(datetime.utcnow())
            
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
            updates['last_updated'] = to_utc_iso(datetime.utcnow())
            
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
        
    async def update_operation_multi_model_ai_metrics(self, operation_id: str, models_data: Dict[str, Dict[str, int]], 
                                                     estimated_dev_hours_saved: Optional[float] = None) -> bool:
        """Update operation with multiple AI model metrics"""
        try:
            operation_data = await self.cache.get_operation(operation_id)
            if not operation_data:
                logger.warning(f"Operation {operation_id} not found in cache for multi-model AI metrics update")
                return False
            
            # Calculate totals
            total_input_tokens = sum(data.get('input_tokens', 0) for data in models_data.values())
            total_output_tokens = sum(data.get('output_tokens', 0) for data in models_data.values())
            
            # Update operation with multi-model metrics
            operation_data['ai_models_used'] = models_data
            operation_data['total_input_tokens'] = total_input_tokens
            operation_data['total_output_tokens'] = total_output_tokens
            
            # Also populate legacy fields for backwards compatibility
            # Use the primary model (first model or highest token count model) for legacy compatibility
            if models_data:
                # Find the model with the highest total token usage
                primary_model = max(models_data.items(), 
                                   key=lambda x: x[1].get('input_tokens', 0) + x[1].get('output_tokens', 0))
                operation_data['model_used'] = primary_model[0]
                
            # Use total tokens for legacy fields to maintain consistency with breakdown calculations
            operation_data['input_tokens'] = total_input_tokens
            operation_data['output_tokens'] = total_output_tokens
            
            if estimated_dev_hours_saved is not None:
                operation_data['estimated_dev_hours_saved'] = estimated_dev_hours_saved
            
            operation_data['last_updated'] = to_utc_iso(datetime.utcnow())
            
            # Update cache
            await self.cache.update_operation(operation_id, operation_data)
            
            logger.debug(f"Updated multi-model AI metrics for operation {operation_id}: {list(models_data.keys())}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update multi-model AI metrics for operation {operation_id}: {e}")
            return False

    async def update_operation_step(self, operation_id: str, current_step: str) -> bool:
        """Update operation current step"""
        try:
            operation_data = await self.cache.get_operation(operation_id)
            if not operation_data:
                logger.warning(f"Operation {operation_id} not found in cache for step update")
                return False
            operation_data['current_step'] = current_step
            operation_data['last_updated'] = to_utc_iso(datetime.utcnow())
            
            # Update cache
            await self.cache.update_operation(operation_id, operation_data)
            
            logger.debug(f"Updated operation step for {operation_id}: {current_step}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update operation step for {operation_id}: {e}")
            return False

    async def force_sync_operation_to_db(self, operation_id: str) -> bool:
        """Force sync operation from cache to database"""
        try:
            return await self.cache.force_sync_operation_to_db(operation_id)
        except Exception as e:
            logger.error(f"Failed to force sync operation {operation_id} to database: {e}")
            return False

    async def update_operation_insights(self, operation_id: str, insights: Dict[str, Any]) -> bool:
        """Update the insights data of an operation"""
        try:
            # Get operation from cache
            operation_data = await self.cache.get_operation(operation_id)
            if not operation_data:
                logger.warning(f"Operation {operation_id} not found in cache for insights update")
                return False
            
            # Update the operation in cache
            operation_data['insights'] = insights
            operation_data['last_updated'] = to_utc_iso(datetime.utcnow())
            
            # Update cache
            await self.cache.update_operation(operation_id, operation_data)
            
            logger.info(f"Operation {operation_id} insights updated with {len(insights)} categories")
            
            # Force sync to database for persistence
            await self.force_sync_operation_to_db(operation_id)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to update operation insights for {operation_id}: {e}")
            return False
        
    async def create_log_entry(self, level: str, message: str, source: str = None,
                              job_id: str = None, operation_id: str = None,
                              repository: str = None, status: str = None,
                              module: str = None, function: str = None,
                              severity: str = None, artifacts: dict = None) -> int:
        """Create log entry with robust caching"""
        log_data = {
            'timestamp': to_utc_iso(datetime.utcnow()),
            'level': level,
            'message': message,
            'source': source,
            'job_id': job_id,
            'operation_id': operation_id,
            'repository': repository,
            'status': status,
            'module': module,
            'function': function,
            'severity': severity,
            'artifacts': artifacts
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
                           repo: str = None, job_id: str = None) -> List[Dict[str, Any]]:
        """Get operations with robust cache-through pattern"""
        filters = {}
        if repo:
            filters['repo'] = repo
            
        return await self.cache.get_operations(
            limit=limit,
            job_id=job_id,
            status=status,
            **filters
        )
        
    async def get_operation(self, operation_id: str) -> Optional[Dict[str, Any]]:
        """Get a single operation with robust cache-through pattern"""
        return await self.cache.get_operation(operation_id)
        
    async def get_logs(self, limit: int = 10000, level: str = None, job_id: str = None,
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

    def _trigger_job_notification(self, job_data: Dict[str, Any], old_status: Optional[str], new_status: str):
        """Trigger notification for job status changes"""
        # Skip notifications if notification service is not available
        if not self.notification_service:
            return
            
        try:
            import asyncio
            from models import JobStatus
            
            # Convert string status to JobStatus enum for comparison
            try:
                new_status_enum = JobStatus(new_status)
            except ValueError:
                return  # Invalid status, skip notification
            
            # Determine event type based on status change
            event_type = None
            if old_status is None and new_status_enum == JobStatus.RUNNING:
                event_type = 'NEW_JOB'
            elif new_status_enum == JobStatus.FAILED:
                event_type = 'JOB_FAILURE'
            elif new_status_enum == JobStatus.COMPLETED:
                event_type = 'JOB_SUCCESS'
            
            if event_type:
                # Create event data
                event_data = {
                    'title': f'Job {event_type.replace("_", " ").title()}',
                    'message': f'Job {job_data["job_id"]} ({job_data.get("job_type", "unknown")}) has {new_status.lower()}',
                    'job_id': job_data['job_id'],
                    'job_type': job_data.get('job_type'),
                    'repository': job_data.get('repository'),
                    'pr_url': job_data.get('pr_url'),
                    'status': new_status,
                    'trigger_user': job_data.get('trigger_user'),
                    'started_at': job_data.get('started_at'),
                    'completed_at': job_data.get('completed_at'),
                    'duration': job_data.get('duration'),
                    'error_details': job_data.get('error_details')
                }
                
                repositories = [job_data['repository']] if job_data.get('repository') else []
                
                # Send notifications asynchronously
                async def send_notifications():
                    await self.notification_service.send_notification(event_type, event_data, repositories)
                
                # Run async notification sending
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # If we're already in an async context, schedule the task
                        asyncio.create_task(send_notifications())
                    else:
                        # If not in async context, run it
                        asyncio.run(send_notifications())
                except RuntimeError:
                    # Fallback: schedule for later execution
                    asyncio.create_task(send_notifications())
                    
        except Exception as e:
            # Don't let notification errors break the job processing
            logger.warning(f"Failed to trigger notification for job {job_data.get('job_id', 'unknown')}: {e}")

# Global instance
robust_cached_job_service: Optional[RobustCachedJobService] = None

def get_robust_cached_job_service(notification_service=None) -> RobustCachedJobService:
    """Get the global robust cached job service instance"""
    global robust_cached_job_service
    if robust_cached_job_service is None:
        robust_cached_job_service = RobustCachedJobService(notification_service)
    elif notification_service and not robust_cached_job_service.notification_service:
        # Update notification service if not already set
        robust_cached_job_service.notification_service = notification_service
    return robust_cached_job_service 