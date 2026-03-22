"""
Cached Job Service - Cache-enabled wrapper for job operations

This service provides the same interface as the original job service
but uses the cache layer for immediate consistency while handling
database persistence asynchronously.
"""
import logging
from datetime import datetime
from typing import List, Dict, Any, Optional
from sqlalchemy.orm import Session

from .cache_service import get_cache_service
from models import JobType, JobStatus, OperationType, OperationStatus

logger = logging.getLogger(__name__)

class CachedJobService:
    """Cache-enabled job service"""
    
    def __init__(self, websocket_manager=None):
        self.cache = get_cache_service()
        self.websocket_manager = websocket_manager
        
    async def create_job(self, job_type: JobType, source: str, repository: str = None,
                        pr_url: str = None, trigger_user: str = None, trigger_event: str = None,
                        installation_id: str = None, request_id: str = None,
                        webhook_payload: dict = None, job_id: str = None) -> str:
        """Create a new job in cache"""
        import uuid
        
        if job_id is None:
            job_id = str(uuid.uuid4())
            
        now = datetime.utcnow()
        
        job_data = {
            'job_id': job_id,
            'job_type': job_type.value if isinstance(job_type, JobType) else job_type,
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
            'completed_at': None,
            'last_updated': now.isoformat(),
            'duration': None,
            'operations_count': 0,
            'completed_operations': 0,
            'failed_operations': 0,
            'total_logs': 0,
            'error_count': 0,
            'warning_count': 0,
            'result_summary': None,
            'error_details': None
        }
        
        # Create in cache immediately
        await self.cache.create_job(job_data)
        
        logger.info(f"Job {job_id} created in cache")
        return job_id
        
    async def update_job_status(self, job_id: str, status: JobStatus, 
                               error_details: str = None, result_summary: dict = None):
        """Update job status in cache"""
        now = datetime.utcnow()
        
        updates = {
            'status': status.value if isinstance(status, JobStatus) else status,
            'last_updated': now.isoformat()
        }
        
        if error_details:
            updates['error_details'] = error_details
            
        if result_summary:
            updates['result_summary'] = result_summary
            
        if status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
            # Job is finishing
            job_data = await self.cache.get_job(job_id)
            if job_data and job_data.get('started_at'):
                try:
                    started_at = datetime.fromisoformat(job_data['started_at'])
                    duration = (now - started_at).total_seconds()
                    updates['duration'] = duration
                    updates['completed_at'] = now.isoformat()
                except Exception as e:
                    logger.warning(f"Could not calculate job duration: {e}")
                    
        # Update in cache
        success = await self.cache.update_job(job_id, updates)
        
        if success:
            logger.info(f"Job {job_id} status updated to {status} in cache")
        else:
            logger.warning(f"Failed to update job {job_id} status in cache")
            
        return success
        
    async def create_operation(self, job_id: str, operation_type: OperationType,
                              command: str, repository: str = None, pr_url: str = None,
                              installation_id: str = None, sender: str = None,
                              request_id: str = None, operation_id: str = None) -> str:
        """Create a new operation in cache"""
        import uuid
        
        if operation_id is None:
            operation_id = str(uuid.uuid4())
            
        now = datetime.utcnow()
        
        operation_data = {
            'operation_id': operation_id,
            'job_id': job_id,
            'operation_type': operation_type.value if isinstance(operation_type, OperationType) else operation_type,
            'command': command,
            'status': OperationStatus.STARTING.value,
            'repository': repository,
            'pr_url': pr_url,
            'installation_id': installation_id,
            'sender': sender,
            'request_id': request_id,
            'started_at': now.isoformat(),
            'completed_at': None,
            'last_updated': now.isoformat(),
            'duration': None,
            'error_details': None,
            'result_data': None,
            'model_used': None,
            'input_tokens': None,
            'output_tokens': None,
            'estimated_dev_hours_saved': None
        }
        
        # Create in cache immediately
        await self.cache.create_operation(operation_data)
        
        # Update job's operation count
        await self._increment_job_operations_count(job_id)
        
        logger.info(f"Operation {operation_id} created in cache for job {job_id}")
        return operation_id
        
    async def update_operation_status(self, operation_id: str, status: OperationStatus,
                                     error_details: str = None, result_data: dict = None):
        """Update operation status in cache"""
        now = datetime.utcnow()
        
        updates = {
            'status': status.value if isinstance(status, OperationStatus) else status,
            'last_updated': now.isoformat()
        }
        
        if error_details:
            updates['error_details'] = error_details
            
        if result_data:
            updates['result_data'] = result_data
            
        if status in [OperationStatus.COMPLETED, OperationStatus.FAILED, OperationStatus.CANCELLED]:
            # Operation is finishing
            # Clear current step when operation completes or fails
            updates['current_step'] = None
            
            operation_data = await self.cache.get_operation(operation_id)
            if operation_data and operation_data.get('started_at'):
                try:
                    started_at = datetime.fromisoformat(operation_data['started_at'])
                    duration = (now - started_at).total_seconds()
                    updates['duration'] = duration
                    updates['completed_at'] = now.isoformat()
                except Exception as e:
                    logger.warning(f"Could not calculate operation duration: {e}")
                    
                # Update job operation counts
                job_id = operation_data.get('job_id')
                if job_id:
                    if status == OperationStatus.COMPLETED:
                        await self._increment_job_completed_operations(job_id)
                    elif status == OperationStatus.FAILED:
                        await self._increment_job_failed_operations(job_id)
                        
        # Update in cache
        success = await self.cache.update_operation(operation_id, updates)
        
        if success:
            logger.info(f"Operation {operation_id} status updated to {status} in cache")
        else:
            logger.warning(f"Failed to update operation {operation_id} status in cache")
            
        return success
        
    async def update_operation_ai_metrics(self, operation_id: str, model_used: str = None,
                                         input_tokens: int = None, output_tokens: int = None,
                                         estimated_dev_hours_saved: float = None):
        """Update operation AI metrics in cache"""
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
            
            # Update in cache - this will never fail with race conditions!
            success = await self.cache.update_operation(operation_id, updates)
            
            if success:
                logger.info(f"Operation {operation_id} AI metrics updated in cache")
            else:
                logger.warning(f"Operation {operation_id} not found in cache for AI metrics update")
                
            return success
            
        return True
        
    async def get_jobs(self, limit: int = 100, include_operations: bool = False,
                      status: str = None, job_type: str = None, repository: str = None,
                      ensure_counts: bool = True) -> List[Dict[str, Any]]:
        """Get jobs from cache"""
        filters = {}
        if job_type:
            filters['job_type'] = job_type
            
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
                
        return jobs
        
    async def get_job(self, job_id: str, include_operations: bool = True) -> Optional[Dict[str, Any]]:
        """Get a single job from cache"""
        job = await self.cache.get_job(job_id)
        
        if job and include_operations:
            operations = await self.cache.get_operations(job_id=job_id)
            job['operations'] = operations
            
        return job
        
    async def get_operations(self, limit: int = 100, status: str = None,
                           repository: str = None) -> List[Dict[str, Any]]:
        """Get operations from cache"""
        filters = {}
        if repository:
            filters['repository'] = repository
            
        return await self.cache.get_operations(
            limit=limit,
            status=status,
            **filters
        )
        
    async def get_operation(self, operation_id: str) -> Optional[Dict[str, Any]]:
        """Get a single operation from cache"""
        return await self.cache.get_operation(operation_id)
        
    async def _increment_job_operations_count(self, job_id: str):
        """Increment job's operations count"""
        job_data = await self.cache.get_job(job_id)
        if job_data:
            current_count = job_data.get('operations_count', 0) or 0
            await self.cache.update_job(job_id, {'operations_count': current_count + 1})
            
    async def _increment_job_completed_operations(self, job_id: str):
        """Increment job's completed operations count"""
        job_data = await self.cache.get_job(job_id)
        if job_data:
            current_count = job_data.get('completed_operations', 0) or 0
            await self.cache.update_job(job_id, {'completed_operations': current_count + 1})
            
    async def _increment_job_failed_operations(self, job_id: str):
        """Increment job's failed operations count"""
        job_data = await self.cache.get_job(job_id)
        if job_data:
            current_count = job_data.get('failed_operations', 0) or 0
            await self.cache.update_job(job_id, {'failed_operations': current_count + 1})
            
    # ============= DEVELOPER TOOLS SUPPORT =============
    
    async def clear_all_data(self):
        """Clear all job and operation data (for dev tools)"""
        await self.cache.clear_all_data()
        logger.info("All job and operation data cleared from cache")
        
    async def delete_test_data(self):
        """Delete test data (for dev tools)"""
        await self.cache.delete_test_data()
        logger.info("Test data deleted from cache") 