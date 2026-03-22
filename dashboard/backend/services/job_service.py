"""
Job Service - Responsible for managing Jobs and their Operations
Follows Single Responsibility Principle
"""
import uuid
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import desc, and_, or_, func

from database import get_db
from models import JobDB, OperationDB, LogEntryDB, Job, Operation, JobType, JobStatus, OperationType, OperationStatus
from timezone_utils import to_utc_iso


class JobService:
    """Service for managing Jobs and Operations"""
    
    def __init__(self, database_manager=None, notification_service=None):
        """Initialize JobService with optional dependencies"""
        self.database_manager = database_manager
        self.notification_service = notification_service
    
    def create_job(self, 
                   job_type: JobType, 
                   source: str,
                   repository: Optional[str] = None,
                   pr_url: Optional[str] = None,
                   trigger_user: Optional[str] = None,
                   trigger_event: Optional[str] = None,
                   installation_id: Optional[str] = None,
                   request_id: Optional[str] = None,
                   webhook_payload: Optional[Dict[str, Any]] = None,
                   job_id: Optional[str] = None) -> str:
        """Create a new job and return its job_id"""
        job_id = job_id or str(uuid.uuid4())
        
        with next(get_db()) as db:
            job = JobDB(
                job_id=job_id,
                job_type=job_type.value,
                source=source,
                status=JobStatus.RUNNING.value,
                repository=repository,
                pr_url=pr_url,
                trigger_user=trigger_user,
                trigger_event=trigger_event,
                installation_id=installation_id,
                request_id=request_id,
                webhook_payload=webhook_payload,
                started_at=datetime.utcnow()
            )
            db.add(job)
            db.commit()
            
            # Trigger new job notification
            self._trigger_job_notification(job, None, JobStatus.RUNNING)
            
        return job_id
    
    def create_operation(self,
                        job_id: str,
                        operation_type: OperationType,
                        command: Optional[str] = None,
                        repository: Optional[str] = None,
                        pr_url: Optional[str] = None,
                        installation_id: Optional[str] = None,
                        sender: Optional[str] = None,
                        request_id: Optional[str] = None,
                        operation_id: Optional[str] = None) -> str:
        """Create a new operation within a job"""
        operation_id = operation_id or str(uuid.uuid4())
        
        with next(get_db()) as db:
            operation = OperationDB(
                operation_id=operation_id,
                job_id=job_id,
                operation_type=operation_type.value,
                command=command,
                status=OperationStatus.STARTING.value,
                repository=repository,
                pr_url=pr_url,
                installation_id=installation_id,
                sender=sender,
                request_id=request_id,
                started_at=datetime.utcnow()
            )
            db.add(operation)
            
            # Update job's operation count
            job = db.query(JobDB).filter(JobDB.job_id == job_id).first()
            if job:
                job.operations_count = (job.operations_count or 0) + 1
                job.last_updated = datetime.utcnow()
            
            db.commit()
            
        return operation_id
    
    def update_job_status(self, job_id: str, status: JobStatus, error_details: Optional[str] = None, result_summary: Optional[Dict[str, Any]] = None):
        """Update job status and completion details"""
        with next(get_db()) as db:
            job = db.query(JobDB).filter(JobDB.job_id == job_id).first()
            if job:
                old_status = job.status
                job.status = status.value
                job.last_updated = datetime.utcnow()
                
                if status in [JobStatus.COMPLETED, JobStatus.FAILED, JobStatus.CANCELLED]:
                    job.completed_at = datetime.utcnow()
                    if job.started_at:
                        job.duration = (job.completed_at - job.started_at).total_seconds()
                
                if error_details:
                    job.error_details = error_details
                if result_summary:
                    job.result_summary = result_summary
                
                db.commit()
                
                # Trigger notifications for status changes
                self._trigger_job_notification(job, old_status, status)
    
    def update_operation_status(self, operation_id: str, status: OperationStatus, error_details: Optional[str] = None, result_data: Optional[Dict[str, Any]] = None):
        """Update operation status and completion details"""
        with next(get_db()) as db:
            operation = db.query(OperationDB).filter(OperationDB.operation_id == operation_id).first()
            if operation:
                operation.status = status.value
                operation.last_updated = datetime.utcnow()
                
                if status in [OperationStatus.COMPLETED, OperationStatus.FAILED, OperationStatus.SKIPPED]:
                    operation.completed_at = datetime.utcnow()
                    # Clear current step when operation completes or fails
                    operation.current_step = None
                    if operation.started_at:
                        operation.duration = (operation.completed_at - operation.started_at).total_seconds()
                
                if error_details:
                    operation.error_details = error_details
                if result_data:
                    operation.result_data = result_data
                
                # Update job's operation counts
                if operation.job_id:
                    job = db.query(JobDB).filter(JobDB.job_id == operation.job_id).first()
                    if job:
                        if status == OperationStatus.COMPLETED:
                            job.completed_operations = (job.completed_operations or 0) + 1
                        elif status == OperationStatus.FAILED:
                            job.failed_operations = (job.failed_operations or 0) + 1
                        job.last_updated = datetime.utcnow()
                
                db.commit()
    
    def get_jobs(self, limit: int = 50, offset: int = 0, include_operations: bool = False, ensure_counts: bool = True) -> List[Job]:
        """Get jobs with optional operations"""
        with next(get_db()) as db:
            query = db.query(JobDB).order_by(desc(JobDB.started_at))
            
            if include_operations:
                query = query.options(joinedload(JobDB.operations))
            
            jobs_db = query.offset(offset).limit(limit).all()
            
            # Ensure accurate counts for the fetched jobs if requested
            if ensure_counts:
                for job_db in jobs_db:
                    # Check if counts look suspicious (zero when they might have data)
                    if (job_db.operations_count == 0 or job_db.total_logs == 0 or 
                        job_db.operations_count is None or job_db.total_logs is None):
                        
                        # Quick check if there's actually data
                        has_ops = db.query(OperationDB).filter(OperationDB.job_id == job_db.job_id).count() > 0
                        has_logs = db.query(LogEntryDB).filter(LogEntryDB.job_id == job_db.job_id).count() > 0
                        
                        if has_ops or has_logs:
                            self.refresh_job_counts(job_db.job_id)
                            # Refresh the job object from DB after update
                            db.refresh(job_db)
            
            jobs = []
            for job_db in jobs_db:
                job_dict = {
                    'id': job_db.id,
                    'job_id': job_db.job_id,
                    'job_type': job_db.job_type,
                    'source': job_db.source,
                    'status': job_db.status,
                    'repository': job_db.repository,
                    'pr_url': job_db.pr_url,
                    'trigger_user': job_db.trigger_user,
                    'trigger_event': job_db.trigger_event,
                    'installation_id': job_db.installation_id,
                    'request_id': job_db.request_id,
                    'webhook_payload': job_db.webhook_payload,
                    'started_at': to_utc_iso(job_db.started_at),
                    'completed_at': to_utc_iso(job_db.completed_at),
                    'last_updated': to_utc_iso(job_db.last_updated),
                    'duration': job_db.duration,
                    'operations_count': job_db.operations_count or 0,
                    'completed_operations': job_db.completed_operations or 0,
                    'failed_operations': job_db.failed_operations or 0,
                    'total_logs': job_db.total_logs or 0,
                    'error_count': job_db.error_count or 0,
                    'warning_count': job_db.warning_count or 0,
                    'result_summary': job_db.result_summary,
                    'error_details': job_db.error_details
                }
                
                if include_operations:
                    operations = []
                    for op_db in job_db.operations:
                        operations.append({
                            'id': op_db.id,
                            'operation_id': op_db.operation_id,
                            'job_id': op_db.job_id,
                            'operation_type': op_db.operation_type,
                            'command': op_db.command,
                            'status': op_db.status,
                            'repository': op_db.repository,
                            'pr_url': op_db.pr_url,
                            'installation_id': op_db.installation_id,
                            'sender': op_db.sender,
                            'request_id': op_db.request_id,
                            'started_at': to_utc_iso(op_db.started_at),
                            'last_updated': to_utc_iso(op_db.last_updated),
                            'completed_at': to_utc_iso(op_db.completed_at),
                            'duration': op_db.duration,
                            'error_details': op_db.error_details,
                            'response_time': op_db.response_time,
                            'context_fetch_time': op_db.context_fetch_time,
                            'ai_processing_time': op_db.ai_processing_time,
                            'suggestions_count': op_db.suggestions_count,
                            'errors_count': op_db.errors_count,
                            'warnings_count': op_db.warnings_count,
                            'result_data': op_db.result_data,
                            # AI/LLM Metrics
                            'model_used': op_db.model_used,
                            'input_tokens': op_db.input_tokens,
                            'output_tokens': op_db.output_tokens,
                            'estimated_dev_hours_saved': op_db.estimated_dev_hours_saved
                        })
                    job_dict['operations'] = operations
                
                jobs.append(Job(**job_dict))
            
            return jobs
    
    def get_job_by_id(self, job_id: str, include_operations: bool = True) -> Optional[Job]:
        """Get a specific job by ID"""
        with next(get_db()) as db:
            query = db.query(JobDB).filter(JobDB.job_id == job_id)
            
            if include_operations:
                query = query.options(joinedload(JobDB.operations))
            
            job_db = query.first()
            if not job_db:
                return None
            
            job_dict = {
                'id': job_db.id,
                'job_id': job_db.job_id,
                'job_type': job_db.job_type,
                'source': job_db.source,
                'status': job_db.status,
                'repository': job_db.repository,
                'pr_url': job_db.pr_url,
                'trigger_user': job_db.trigger_user,
                'trigger_event': job_db.trigger_event,
                'installation_id': job_db.installation_id,
                'request_id': job_db.request_id,
                'webhook_payload': job_db.webhook_payload,
                'started_at': to_utc_iso(job_db.started_at),
                'completed_at': to_utc_iso(job_db.completed_at),
                'last_updated': to_utc_iso(job_db.last_updated),
                'duration': job_db.duration,
                'operations_count': job_db.operations_count or 0,
                'completed_operations': job_db.completed_operations or 0,
                'failed_operations': job_db.failed_operations or 0,
                'total_logs': job_db.total_logs or 0,
                'error_count': job_db.error_count or 0,
                'warning_count': job_db.warning_count or 0,
                'result_summary': job_db.result_summary,
                'error_details': job_db.error_details
            }
            
            if include_operations:
                operations = []
                for op_db in job_db.operations:
                    operations.append({
                        'id': op_db.id,
                        'operation_id': op_db.operation_id,
                        'job_id': op_db.job_id,
                        'operation_type': op_db.operation_type,
                        'command': op_db.command,
                        'status': op_db.status,
                        'repository': op_db.repository,
                        'pr_url': op_db.pr_url,
                        'installation_id': op_db.installation_id,
                        'sender': op_db.sender,
                        'request_id': op_db.request_id,
                        'started_at': to_utc_iso(op_db.started_at),
                        'last_updated': to_utc_iso(op_db.last_updated),
                        'completed_at': to_utc_iso(op_db.completed_at),
                        'duration': op_db.duration,
                        'error_details': op_db.error_details,
                        'response_time': op_db.response_time,
                        'context_fetch_time': op_db.context_fetch_time,
                        'ai_processing_time': op_db.ai_processing_time,
                        'suggestions_count': op_db.suggestions_count,
                        'errors_count': op_db.errors_count,
                        'warnings_count': op_db.warnings_count,
                        'result_data': op_db.result_data,
                        # AI/LLM Metrics
                        'model_used': op_db.model_used,
                        'input_tokens': op_db.input_tokens,
                        'output_tokens': op_db.output_tokens,
                        'estimated_dev_hours_saved': op_db.estimated_dev_hours_saved
                    })
                job_dict['operations'] = operations
            
            return Job(**job_dict)
    
    def get_operations_by_job(self, job_id: str) -> List[Operation]:
        """Get all operations for a specific job"""
        with next(get_db()) as db:
            operations_db = db.query(OperationDB).filter(
                OperationDB.job_id == job_id
            ).order_by(OperationDB.started_at).all()
            
            operations = []
            for op_db in operations_db:
                operations.append(Operation(
                    id=op_db.id,
                    operation_id=op_db.operation_id,
                    job_id=op_db.job_id,
                    operation_type=op_db.operation_type,
                    command=op_db.command,
                    status=op_db.status,
                    repository=op_db.repository,
                    pr_url=op_db.pr_url,
                    installation_id=op_db.installation_id,
                    sender=op_db.sender,
                    request_id=op_db.request_id,
                    started_at=to_utc_iso(op_db.started_at),
                    last_updated=to_utc_iso(op_db.last_updated),
                    completed_at=to_utc_iso(op_db.completed_at),
                    duration=op_db.duration,
                    error_details=op_db.error_details,
                    response_time=op_db.response_time,
                    context_fetch_time=op_db.context_fetch_time,
                    ai_processing_time=op_db.ai_processing_time,
                    suggestions_count=op_db.suggestions_count,
                    errors_count=op_db.errors_count,
                    warnings_count=op_db.warnings_count,
                    result_data=op_db.result_data,
                    # AI/LLM Metrics
                    model_used=op_db.model_used,
                    input_tokens=op_db.input_tokens,
                    output_tokens=op_db.output_tokens,
                    estimated_dev_hours_saved=op_db.estimated_dev_hours_saved
                ))
            
            return operations
    
    def update_job_log_counts(self, job_id: str):
        """Update job's log counts based on actual log entries"""
        with next(get_db()) as db:
            # Count logs by level
            log_counts = db.query(
                LogEntryDB.level,
                func.count(LogEntryDB.id).label('count')
            ).filter(
                LogEntryDB.job_id == job_id
            ).group_by(LogEntryDB.level).all()
            
            total_logs = sum(count for _, count in log_counts)
            error_count = sum(count for level, count in log_counts if level in ['ERROR', 'CRITICAL'])
            warning_count = sum(count for level, count in log_counts if level == 'WARNING')
            
            # Update job
            job = db.query(JobDB).filter(JobDB.job_id == job_id).first()
            if job:
                job.total_logs = total_logs
                job.error_count = error_count
                job.warning_count = warning_count
                job.last_updated = datetime.utcnow()
                db.commit()

    def refresh_job_counts(self, job_id: str):
        """Refresh all counts for a job by querying related data"""
        with next(get_db()) as db:
            job = db.query(JobDB).filter(JobDB.job_id == job_id).first()
            if not job:
                return
            
            # Count operations
            operations_count = db.query(OperationDB).filter(OperationDB.job_id == job_id).count()
            completed_operations = db.query(OperationDB).filter(
                OperationDB.job_id == job_id,
                OperationDB.status == "completed"
            ).count()
            failed_operations = db.query(OperationDB).filter(
                OperationDB.job_id == job_id,
                OperationDB.status == "failed"
            ).count()
            
            # Count logs
            total_logs = db.query(LogEntryDB).filter(LogEntryDB.job_id == job_id).count()
            error_count = db.query(LogEntryDB).filter(
                LogEntryDB.job_id == job_id,
                LogEntryDB.level.in_(['ERROR', 'CRITICAL'])
            ).count()
            warning_count = db.query(LogEntryDB).filter(
                LogEntryDB.job_id == job_id,
                LogEntryDB.level == 'WARNING'
            ).count()
            
            # Update job with calculated counts
            job.operations_count = operations_count
            job.completed_operations = completed_operations
            job.failed_operations = failed_operations
            job.total_logs = total_logs
            job.error_count = error_count
            job.warning_count = warning_count
            job.last_updated = datetime.utcnow()
            
            db.commit()

    def ensure_accurate_counts(self, force_refresh: bool = False) -> int:
        """Ensure all jobs have accurate counts - returns number of jobs updated"""
        updated_count = 0
        
        with next(get_db()) as db:
            # Get all jobs, but especially focus on ones with suspicious zero counts
            jobs_query = db.query(JobDB)
            
            if not force_refresh:
                # Only update jobs that have zero counts but might have operations/logs
                jobs_query = jobs_query.filter(
                    or_(
                        JobDB.operations_count == 0,
                        JobDB.total_logs == 0,
                        JobDB.operations_count.is_(None),
                        JobDB.total_logs.is_(None)
                    )
                )
            
            jobs_to_update = jobs_query.all()
            
            for job in jobs_to_update:
                # Check if this job actually has operations or logs
                has_operations = db.query(OperationDB).filter(OperationDB.job_id == job.job_id).count() > 0
                has_logs = db.query(LogEntryDB).filter(LogEntryDB.job_id == job.job_id).count() > 0
                
                if has_operations or has_logs or force_refresh:
                    self.refresh_job_counts(job.job_id)
                    updated_count += 1
            
        return updated_count

    def _trigger_job_notification(self, job: JobDB, old_status: Optional[str], new_status: JobStatus):
        """Trigger notification for job status changes"""
        # Skip notifications if notification service is not available
        if not self.notification_service:
            return
            
        try:
            import asyncio
            
            # Determine event type based on status change
            event_type = None
            if old_status is None and new_status == JobStatus.RUNNING:
                event_type = 'NEW_JOB'
            elif new_status == JobStatus.FAILED:
                event_type = 'JOB_FAILURE'
            elif new_status == JobStatus.COMPLETED:
                event_type = 'JOB_SUCCESS'
            
            if event_type:
                # Create event data
                event_data = {
                    'title': f'Job {event_type.replace("_", " ").title()}',
                    'message': f'Job {job.job_id} ({job.job_type}) has {new_status.value.lower()}',
                    'job_id': job.job_id,
                    'job_type': job.job_type,
                    'repository': job.repository,
                    'pr_url': job.pr_url,
                    'status': new_status.value,
                    'trigger_user': job.trigger_user,
                    'started_at': to_utc_iso(job.started_at),
                    'completed_at': to_utc_iso(job.completed_at),
                    'duration': job.duration,
                    'error_details': job.error_details
                }
                
                repositories = [job.repository] if job.repository else []
                
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
            print(f"Warning: Failed to trigger notification for job {job.job_id}: {e}") 