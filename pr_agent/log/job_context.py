"""
Job and Operation Context Management for PR-Agent
Provides thread-local context for tracking jobs and operations across the application
"""
import uuid
import threading
from datetime import datetime
from typing import Optional, Dict, Any, ContextManager
from contextlib import contextmanager
from enum import Enum

try:
    from loguru import logger
except ImportError:
    logger = None

from pr_agent.config_loader import get_settings


class JobType(str, Enum):
    WEBHOOK = "webhook"
    CLI = "cli"
    MANUAL = "manual"
    API = "api"


class OperationType(str, Enum):
    STARTING = "starting"
    FETCHING_CONTEXT = "fetching_context"
    PROCESSING_PR = "processing_pr"
    GENERATING_REVIEW = "generating_review"
    GENERATING_DESCRIPTION = "generating_description"
    GENERATING_SUGGESTIONS = "generating_suggestions"
    SELF_REFLECTING = "self_reflecting"
    PUBLISHING_RESULTS = "publishing_results"
    FINALIZING = "finalizing"
    CLEANUP = "cleanup"


class JobContext:
    """Thread-local context for job and operation tracking"""
    
    _context = threading.local()
    
    @classmethod
    def get_current_job_id(cls) -> Optional[str]:
        """Get the current job ID"""
        return getattr(cls._context, 'job_id', None)
    
    @classmethod
    def get_current_operation_id(cls) -> Optional[str]:
        """Get the current operation ID"""
        return getattr(cls._context, 'operation_id', None)
    
    @classmethod
    def get_job_metadata(cls) -> Dict[str, Any]:
        """Get current job metadata"""
        return getattr(cls._context, 'job_metadata', {})
    
    @classmethod
    def get_operation_metadata(cls) -> Dict[str, Any]:
        """Get current operation metadata"""
        return getattr(cls._context, 'operation_metadata', {})
    
    @classmethod
    def set_job_context(cls, job_id: str, job_metadata: Dict[str, Any]):
        """Set the current job context"""
        cls._context.job_id = job_id
        cls._context.job_metadata = job_metadata
        
        # Log the job creation
        if logger:
            logger.bind(
                job_id=job_id,
                job_type=job_metadata.get('job_type'),
                repository=job_metadata.get('repository'),
                pr_url=job_metadata.get('pr_url'),
                trigger_user=job_metadata.get('trigger_user'),
                **job_metadata
            ).info(f"Job {job_id} started - {job_metadata.get('job_type', 'unknown')} - {job_metadata.get('repository', 'unknown')}")
    
    @classmethod
    def set_operation_context(cls, operation_id: str, operation_metadata: Dict[str, Any]):
        """Set the current operation context"""
        cls._context.operation_id = operation_id
        cls._context.operation_metadata = operation_metadata
        
        # Log the operation start
        if logger:
            logger.bind(
                job_id=cls.get_current_job_id(),
                operation_id=operation_id,
                operation_type=operation_metadata.get('operation_type'),
                **operation_metadata
            ).info(f"Operation {operation_id} started - {operation_metadata.get('operation_type', 'unknown')}")
    
    @classmethod
    def clear_operation_context(cls):
        """Clear the current operation context"""
        operation_id = getattr(cls._context, 'operation_id', None)
        if operation_id and logger:
            logger.bind(
                job_id=cls.get_current_job_id(),
                operation_id=operation_id
            ).info(f"Operation {operation_id} completed")
        
        cls._context.operation_id = None
        cls._context.operation_metadata = {}
    
    @classmethod
    def clear_job_context(cls):
        """Clear the current job context"""
        job_id = getattr(cls._context, 'job_id', None)
        if job_id and logger:
            logger.bind(job_id=job_id).info(f"Job {job_id} completed")
        
        cls._context.job_id = None
        cls._context.job_metadata = {}
        cls._context.operation_id = None
        cls._context.operation_metadata = {}


def create_job(job_type: JobType,
               source: str,
               repository: Optional[str] = None,
               pr_url: Optional[str] = None,
               trigger_user: Optional[str] = None,
               trigger_event: Optional[str] = None,
               installation_id: Optional[str] = None,
               request_id: Optional[str] = None,
               webhook_payload: Optional[Dict[str, Any]] = None) -> str:
    """Create a new job and set it as the current context"""
    job_id = str(uuid.uuid4())
    
    job_metadata = {
        'job_type': job_type.value,
        'source': source,
        'repository': repository,
        'pr_url': pr_url,
        'trigger_user': trigger_user,
        'trigger_event': trigger_event,
        'installation_id': installation_id,
        'request_id': request_id,
        'webhook_payload': webhook_payload,
        'started_at': datetime.utcnow().isoformat()
    }
    
    # Remove None values
    job_metadata = {k: v for k, v in job_metadata.items() if v is not None}
    
    JobContext.set_job_context(job_id, job_metadata)
    return job_id


@contextmanager
def job_context(job_type: JobType,
                source: str,
                repository: Optional[str] = None,
                pr_url: Optional[str] = None,
                trigger_user: Optional[str] = None,
                trigger_event: Optional[str] = None,
                installation_id: Optional[str] = None,
                request_id: Optional[str] = None,
                webhook_payload: Optional[Dict[str, Any]] = None) -> ContextManager[str]:
    """Context manager for job execution"""
    job_id = create_job(
        job_type=job_type,
        source=source,
        repository=repository,
        pr_url=pr_url,
        trigger_user=trigger_user,
        trigger_event=trigger_event,
        installation_id=installation_id,
        request_id=request_id,
        webhook_payload=webhook_payload
    )
    
    try:
        yield job_id
    finally:
        JobContext.clear_job_context()


@contextmanager
def operation_context(operation_type: OperationType,
                     command: Optional[str] = None,
                     repo: Optional[str] = None,
                     pr_url: Optional[str] = None,
                     installation_id: Optional[str] = None,
                     sender: Optional[str] = None,
                     request_id: Optional[str] = None) -> ContextManager[str]:
    """Context manager for operation execution"""
    operation_id = str(uuid.uuid4())
    
    operation_metadata = {
        'operation_type': operation_type.value,
        'command': command,
        'repo': repo,
        'pr_url': pr_url,
        'installation_id': installation_id,
        'sender': sender,
        'request_id': request_id,
        'started_at': datetime.utcnow().isoformat()
    }
    
    # Remove None values
    operation_metadata = {k: v for k, v in operation_metadata.items() if v is not None}
    
    JobContext.set_operation_context(operation_id, operation_metadata)
    
    try:
        yield operation_id
    finally:
        JobContext.clear_operation_context()


def get_current_context() -> Dict[str, Any]:
    """Get all current context information"""
    return {
        'job_id': JobContext.get_current_job_id(),
        'operation_id': JobContext.get_current_operation_id(),
        'job_metadata': JobContext.get_job_metadata(),
        'operation_metadata': JobContext.get_operation_metadata()
    }


def bind_logger_context():
    """Bind current job/operation context to logger for automatic inclusion in logs"""
    if not logger:
        return
    
    context = {}
    
    job_id = JobContext.get_current_job_id()
    if job_id:
        context['job_id'] = job_id
        context.update(JobContext.get_job_metadata())
    
    operation_id = JobContext.get_current_operation_id()
    if operation_id:
        context['operation_id'] = operation_id
        context.update(JobContext.get_operation_metadata())
    
    if context:
        return logger.bind(**context)
    
    return logger 