"""
Job and Operation Context Management for PR-Agent
Provides thread-local context for tracking jobs and operations across the application
"""
import uuid
import threading
import asyncio
from datetime import datetime
from typing import Optional, Dict, Any, ContextManager, List
from contextlib import contextmanager, asynccontextmanager
from enum import Enum

try:
    from loguru import logger
except ImportError:
    logger = None

from pr_agent.config_loader import get_settings

# Import dashboard client for API integration
try:
    from pr_agent.log.dashboard_client import get_dashboard_client
except ImportError:
    get_dashboard_client = None

# Track pending async tasks for proper cleanup
_pending_tasks: List[asyncio.Task] = []
_task_lock = threading.Lock()

def add_pending_task(task: asyncio.Task):
    """Add a task to the pending tasks list"""
    with _task_lock:
        _pending_tasks.append(task)

def get_pending_tasks() -> List[asyncio.Task]:
    """Get all pending tasks and clear the list"""
    with _task_lock:
        tasks = _pending_tasks.copy()
        _pending_tasks.clear()
        return tasks

async def wait_for_pending_tasks(timeout: float = 10.0):
    """Wait for all pending dashboard tasks to complete"""
    tasks = get_pending_tasks()
    if not tasks:
        return
    
    if logger:
        logger.debug(f"Waiting for {len(tasks)} pending dashboard tasks to complete...")
    
    try:
        # Wait for all tasks to complete
        results = await asyncio.wait_for(asyncio.gather(*tasks, return_exceptions=True), timeout=timeout)
        
        # Check results for errors
        errors = []
        successes = 0
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                errors.append(f"Task {i}: {result}")
            else:
                successes += 1
        
        if logger:
            logger.debug(f"Dashboard tasks completed: {successes} successful, {len(errors)} failed")
            for error in errors:
                logger.debug(f"Dashboard task error: {error}")
                
    except asyncio.TimeoutError:
        if logger:
            logger.warning(f"Dashboard tasks timed out after {timeout}s")
        # Cancel remaining tasks
        for task in tasks:
            if not task.done():
                task.cancel()
                if logger:
                    logger.debug(f"Cancelled pending dashboard task: {task}")
    except Exception as e:
        if logger:
            logger.warning(f"Error waiting for dashboard tasks: {e}")
        # Cancel remaining tasks
        for task in tasks:
            if not task.done():
                task.cancel()


def extract_repository_from_url(url: Optional[str]) -> Optional[str]:
    """Extract repository name from PR/issue URL"""
    if not url:
        return None
    
    try:
        # Handle common Git hosting URL patterns
        # GitHub: https://github.com/owner/repo/pull/123
        # GitLab: https://gitlab.com/owner/repo/-/merge_requests/123
        # Azure: https://dev.azure.com/org/project/_git/repo/pullrequest/123
        
        if 'github.com' in url:
            parts = url.split('/')
            if len(parts) >= 5:
                return f"{parts[3]}/{parts[4]}"
        elif 'gitlab.com' in url:
            parts = url.split('/')
            if len(parts) >= 5:
                return f"{parts[3]}/{parts[4]}"
        elif 'dev.azure.com' in url:
            parts = url.split('/')
            if len(parts) >= 7 and '_git' in parts:
                org = parts[3]
                project = parts[4]
                repo = parts[6]
                return f"{org}/{project}/{repo}"
        
        # Fallback: try to extract meaningful parts
        parts = [p for p in url.split('/') if p and p not in ['http:', 'https:', 'www']]
        if len(parts) >= 3:
            return '/'.join(parts[1:3])  # Skip domain, take next two parts
    except Exception as e:
        if logger:
            logger.debug(f"Failed to extract repository from URL {url}: {e}")
    
    return None


class JobType(str, Enum):
    WEBHOOK = "webhook"
    CLI = "cli"
    MANUAL = "manual"
    API = "api"


class OperationType(str, Enum):
    STARTING = "starting"
    FETCHING_CONTEXT = "fetching_context"
    PROCESSING_PR = "processing_pr"
    REVIEW = "review"
    DESCRIBE = "describe"
    IMPROVE = "improve"
    TEST = "test"
    ADD_DOCS = "add_docs"
    UPDATE_CHANGELOG = "update_changelog"
    SIMILAR_ISSUE = "similar_issue"
    SELF_REFLECTING = "self_reflecting"
    PUBLISHING_RESULTS = "publishing_results"
    FINALIZING = "finalizing"
    CLEANUP = "cleanup"


class JobContext:
    """Thread-local context for job and operation tracking"""
    
    _context = threading.local()
    _operation_creation_tasks = {}  # Track operation creation tasks by operation_id
    
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
            # Create a copy of metadata to avoid duplicate keys
            log_metadata = {k: v for k, v in job_metadata.items()}
            logger.bind(
                job_id=job_id,
                **log_metadata
            ).info(f"Job {job_id} started - {job_metadata.get('job_type', 'unknown')} - {job_metadata.get('repository', 'unknown')}")
        
        # Send job creation to dashboard (error resilient)
        if get_dashboard_client:
            try:
                client = get_dashboard_client()
                if client and client._enabled:
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            # If we're in an async context, schedule the coroutine and track it
                            task = asyncio.create_task(client.create_job(
                                job_type=job_metadata.get('job_type', 'manual'),
                                source=job_metadata.get('source', 'unknown'),
                                repository=job_metadata.get('repository'),
                                pr_url=job_metadata.get('pr_url'),
                                trigger_user=job_metadata.get('trigger_user'),
                                trigger_event=job_metadata.get('trigger_event'),
                                installation_id=job_metadata.get('installation_id'),
                                request_id=job_metadata.get('request_id'),
                                webhook_payload=job_metadata.get('webhook_payload'),
                                job_id=job_id
                            ))
                            add_pending_task(task)
                            if logger:
                                logger.debug(f"Dashboard job creation queued for job {job_id}")
                        else:
                            # Event loop exists but not running, use sync fallback
                            raise RuntimeError("Event loop not running")
                    except RuntimeError:
                        # No event loop running, use synchronous fallback
                        try:
                            import requests
                            job_data = {
                                'job_type': job_metadata.get('job_type', 'manual'),
                                'source': job_metadata.get('source', 'unknown'),
                                'repository': job_metadata.get('repository'),
                                'pr_url': job_metadata.get('pr_url'),
                                'trigger_user': job_metadata.get('trigger_user'),
                                'trigger_event': job_metadata.get('trigger_event'),
                                'installation_id': job_metadata.get('installation_id'),
                                'request_id': job_metadata.get('request_id'),
                                'webhook_payload': job_metadata.get('webhook_payload'),
                                'job_id': job_id
                            }
                            # Remove None values
                            job_data = {k: v for k, v in job_data.items() if v is not None}
                            
                            headers = {"Content-Type": "application/json"}
                            if client.api_key:
                                headers["Authorization"] = f"Bearer {client.api_key}"
                            
                            url = f"{client.dashboard_url.rstrip('/')}/api/jobs/create"
                            response = requests.post(url, json=job_data, headers=headers, timeout=10)
                            
                            if response.status_code == 200:
                                if logger:
                                    logger.debug(f"Dashboard job creation successful (sync) for job {job_id}")
                            else:
                                if logger:
                                    logger.debug(f"Dashboard job creation failed (sync): {response.status_code}")
                        except Exception as sync_e:
                            if logger:
                                logger.debug(f"Sync dashboard job creation failed for {job_id}: {sync_e}")
            except Exception as e:
                # Dashboard integration should never break job execution
                if logger:
                    logger.debug(f"Dashboard job creation failed for {job_id}: {e}")
    
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
                **operation_metadata
            ).info(f"Operation {operation_id} started - {operation_metadata.get('operation_type', 'unknown')}")
        
        # Send to dashboard (error resilient)
        if get_dashboard_client:
            try:
                client = get_dashboard_client()
                if client and client._enabled:
                    # Capture job_id BEFORE creating async task to avoid thread-local context issues
                    current_job_id = cls.get_current_job_id()
                    
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            # Create operation creation task and track it
                            task = asyncio.create_task(client.create_operation(
                                operation_id=operation_id,
                                job_id=current_job_id,  # Use captured job_id
                                operation_type=operation_metadata.get('operation_type', 'starting'),
                                command=operation_metadata.get('command'),
                                repo=operation_metadata.get('repo'),
                                pr_url=operation_metadata.get('pr_url'),
                                installation_id=operation_metadata.get('installation_id'),
                                sender=operation_metadata.get('sender'),
                                request_id=operation_metadata.get('request_id')
                            ))
                            add_pending_task(task)
                            # Track this specific operation creation task
                            cls._operation_creation_tasks[operation_id] = task
                            if logger:
                                logger.debug(f"Dashboard operation creation queued for operation {operation_id} with job_id {current_job_id}")
                        else:
                            # Event loop exists but not running, use sync fallback
                            raise RuntimeError("Event loop not running")
                    except RuntimeError:
                        # No event loop running, use synchronous fallback
                        try:
                            import requests
                            operation_data = {
                                'job_id': current_job_id,  # Use captured job_id
                                'operation_type': operation_metadata.get('operation_type', 'starting'),
                                'command': operation_metadata.get('command'),
                                'repo': operation_metadata.get('repo'),
                                'pr_url': operation_metadata.get('pr_url'),
                                'installation_id': operation_metadata.get('installation_id'),
                                'sender': operation_metadata.get('sender'),
                                'request_id': operation_metadata.get('request_id')
                            }
                            # Remove None values
                            operation_data = {k: v for k, v in operation_data.items() if v is not None}
                            
                            headers = {"Content-Type": "application/json"}
                            if client.api_key:
                                headers["Authorization"] = f"Bearer {client.api_key}"
                            
                            url = f"{client.dashboard_url.rstrip('/')}/api/operations/create"
                            response = requests.post(url, json=operation_data, headers=headers, timeout=10)
                            
                            if response.status_code == 200:
                                if logger:
                                    logger.debug(f"Dashboard operation creation successful (sync) for operation {operation_id} with job_id {current_job_id}")
                            else:
                                if logger:
                                    logger.debug(f"Dashboard operation creation failed (sync): {response.status_code}")
                        except Exception as sync_e:
                            if logger:
                                logger.debug(f"Sync dashboard operation creation failed for {operation_id}: {sync_e}")
            except Exception as e:
                # Dashboard integration should never break operation execution
                if logger:
                    logger.debug(f"Dashboard operation creation failed for {operation_id}: {e}")
    
    @classmethod
    def clear_operation_context(cls):
        """Clear the current operation context"""
        operation_id = getattr(cls._context, 'operation_id', None)
        if operation_id and logger:
            logger.bind(
                job_id=cls.get_current_job_id(),
                operation_id=operation_id
            ).info(f"Operation {operation_id} completed")
        
        # Clean up operation creation task tracking
        if operation_id and operation_id in cls._operation_creation_tasks:
            del cls._operation_creation_tasks[operation_id]
        
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

    @classmethod
    async def wait_for_operation_creation(cls, operation_id: str, timeout: float = 5.0):
        """Wait for operation creation to complete before proceeding"""
        if operation_id in cls._operation_creation_tasks:
            try:
                await asyncio.wait_for(cls._operation_creation_tasks[operation_id], timeout=timeout)
                if logger:
                    logger.debug(f"Operation creation completed for {operation_id}")
            except asyncio.TimeoutError:
                if logger:
                    logger.debug(f"Operation creation timeout for {operation_id}")
            except Exception as e:
                if logger:
                    logger.debug(f"Operation creation failed for {operation_id}: {e}")


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


# Convenience functions for status updates
def update_job_status(status: str, error_details: Optional[str] = None, result_summary: Optional[Dict[str, Any]] = None):
    """Update the current job's status (error resilient)"""
    job_id = JobContext.get_current_job_id()
    if not job_id:
        if logger:
            logger.debug("No active job context - skipping job status update")
        return
    
    # Log the status change
    if logger:
        logger.bind(job_id=job_id).info(f"Job {job_id} status updated to: {status}")
    
    # Send to dashboard (error resilient)
    if get_dashboard_client:
        try:
            client = get_dashboard_client()
            if client and client._enabled:
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        task = asyncio.create_task(client.update_job_status(
                            job_id=job_id,
                            status=status,
                            error_details=error_details,
                            result_summary=result_summary
                        ))
                        add_pending_task(task)
                        if logger:
                            logger.debug(f"Dashboard job status update queued for {job_id}: {status}")
                    else:
                        # Event loop exists but not running, use sync fallback
                        raise RuntimeError("Event loop not running")
                except RuntimeError:
                    # No event loop running, use synchronous fallback
                    try:
                        import requests
                        status_data = {
                            'status': status,
                            'error_details': error_details,
                            'result_summary': result_summary
                        }
                        # Remove None values
                        status_data = {k: v for k, v in status_data.items() if v is not None}
                        
                        headers = {"Content-Type": "application/json"}
                        if client.api_key:
                            headers["Authorization"] = f"Bearer {client.api_key}"
                        
                        url = f"{client.dashboard_url.rstrip('/')}/api/jobs/{job_id}/status"
                        response = requests.post(url, json=status_data, headers=headers, timeout=10)
                        
                        if response.status_code == 200:
                            if logger:
                                logger.debug(f"Dashboard job status update successful (sync) for {job_id}: {status}")
                        else:
                            if logger:
                                logger.debug(f"Dashboard job status update failed (sync): {response.status_code}")
                    except Exception as sync_e:
                        if logger:
                            logger.debug(f"Sync dashboard job status update failed for {job_id}: {sync_e}")
        except Exception as e:
            if logger:
                logger.debug(f"Dashboard job status update failed for {job_id}: {e}")


def update_operation_status(status: str, error_details: Optional[str] = None, result_data: Optional[Dict[str, Any]] = None):
    """Update the current operation's status (error resilient)"""
    operation_id = JobContext.get_current_operation_id()
    if not operation_id:
        if logger:
            logger.debug("No active operation context - skipping operation status update")
        return
    
    # Log the status change
    if logger:
        logger.bind(operation_id=operation_id).info(f"Operation {operation_id} status updated to: {status}")
    
    # Send to dashboard (error resilient)
    if get_dashboard_client:
        try:
            client = get_dashboard_client()
            if client and client._enabled:
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        task = asyncio.create_task(client.update_operation_status(
                            operation_id=operation_id,
                            status=status,
                            error_details=error_details,
                            result_data=result_data
                        ))
                        add_pending_task(task)
                        if logger:
                            logger.debug(f"Dashboard operation status update queued for {operation_id}: {status}")
                    else:
                        # Event loop exists but not running, use sync fallback
                        raise RuntimeError("Event loop not running")
                except RuntimeError:
                    # No event loop running, use synchronous fallback
                    try:
                        import requests
                        status_data = {
                            'status': status,
                            'error_details': error_details,
                            'result_data': result_data
                        }
                        # Remove None values
                        status_data = {k: v for k, v in status_data.items() if v is not None}
                        
                        headers = {"Content-Type": "application/json"}
                        if client.api_key:
                            headers["Authorization"] = f"Bearer {client.api_key}"
                        
                        url = f"{client.dashboard_url.rstrip('/')}/api/operations/{operation_id}/status"
                        response = requests.post(url, json=status_data, headers=headers, timeout=10)
                        
                        if response.status_code == 200:
                            if logger:
                                logger.debug(f"Dashboard operation status update successful (sync) for {operation_id}: {status}")
                        else:
                            if logger:
                                logger.debug(f"Dashboard operation status update failed (sync): {response.status_code}")
                    except Exception as sync_e:
                        if logger:
                            logger.debug(f"Sync dashboard operation status update failed for {operation_id}: {sync_e}")
        except Exception as e:
            if logger:
                logger.debug(f"Dashboard operation status update failed for {operation_id}: {e}")


def update_operation_ai_metrics(model_used: Optional[str] = None,
                               input_tokens: Optional[int] = None,
                               output_tokens: Optional[int] = None,
                               estimated_dev_hours_saved: Optional[float] = None):
    """Update the current operation's AI metrics (error resilient)"""
    operation_id = JobContext.get_current_operation_id()
    if not operation_id:
        if logger:
            logger.debug("No active operation context - skipping AI metrics update")
        return
    
    # Skip if no metrics provided
    if not any([model_used, input_tokens, output_tokens, estimated_dev_hours_saved]):
        if logger:
            logger.debug("No AI metrics provided - skipping update")
        return
    
    # Log the metrics
    if logger:
        metrics_info = []
        if model_used:
            metrics_info.append(f"model: {model_used}")
        if input_tokens:
            metrics_info.append(f"input_tokens: {input_tokens}")
        if output_tokens:
            metrics_info.append(f"output_tokens: {output_tokens}")
        if estimated_dev_hours_saved:
            metrics_info.append(f"dev_hours_saved: {estimated_dev_hours_saved}")
        
        if metrics_info:
            logger.bind(
                operation_id=operation_id,
                model_used=model_used,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                estimated_dev_hours_saved=estimated_dev_hours_saved
            ).info(f"Operation {operation_id} AI metrics: {', '.join(metrics_info)}")
    
    # Send to dashboard (error resilient)
    if get_dashboard_client:
        try:
            client = get_dashboard_client()
            if client and client._enabled:
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Create an async task that waits for operation creation first
                        async def send_metrics_after_creation():
                            # Wait for operation creation to complete
                            await JobContext.wait_for_operation_creation(operation_id)
                            # Now send the AI metrics
                            await client.update_operation_ai_metrics(
                                operation_id=operation_id,
                                model_used=model_used,
                                input_tokens=input_tokens,
                                output_tokens=output_tokens,
                                estimated_dev_hours_saved=estimated_dev_hours_saved
                            )
                        
                        task = asyncio.create_task(send_metrics_after_creation())
                        add_pending_task(task)
                        if logger:
                            logger.debug(f"Dashboard AI metrics update queued for {operation_id}")
                    else:
                        # Event loop exists but not running, use sync fallback
                        raise RuntimeError("Event loop not running")
                except RuntimeError:
                    # No event loop running, use synchronous fallback
                    try:
                        import requests
                        metrics_data = {
                            'model_used': model_used,
                            'input_tokens': input_tokens,
                            'output_tokens': output_tokens,
                            'estimated_dev_hours_saved': estimated_dev_hours_saved
                        }
                        # Remove None values
                        metrics_data = {k: v for k, v in metrics_data.items() if v is not None}
                        
                        if not metrics_data:
                            return  # Nothing to update
                        
                        headers = {"Content-Type": "application/json"}
                        if client.api_key:
                            headers["Authorization"] = f"Bearer {client.api_key}"
                        
                        url = f"{client.dashboard_url.rstrip('/')}/api/operations/{operation_id}/ai-metrics"
                        response = requests.post(url, json=metrics_data, headers=headers, timeout=10)
                        
                        if response.status_code == 200:
                            if logger:
                                logger.debug(f"Dashboard AI metrics update successful (sync) for {operation_id}")
                        else:
                            if logger:
                                logger.debug(f"Dashboard AI metrics update failed (sync): {response.status_code}")
                    except Exception as sync_e:
                        if logger:
                            logger.debug(f"Sync dashboard AI metrics update failed for {operation_id}: {sync_e}")
        except Exception as e:
            if logger:
                logger.debug(f"Dashboard AI metrics update failed for {operation_id}: {e}")


# Dashboard Integration Setup
def setup_dashboard_integration() -> bool:
    """Setup complete dashboard integration (sink + client)"""
    try:
        # Setup dashboard sink for automatic log forwarding
        try:
            from pr_agent.log.dashboard_sink import setup_dashboard_sink
            sink = setup_dashboard_sink()
            if logger:
                logger.info("Dashboard sink initialized for log forwarding")
        except ImportError:
            if logger:
                logger.debug("Dashboard sink not available - logs will not be forwarded")
        except Exception as e:
            if logger:
                logger.warning(f"Failed to setup dashboard sink: {e}")
        
        # Setup dashboard client for API communication
        try:
            from pr_agent.log.dashboard_client import setup_dashboard_client
            client = setup_dashboard_client()
            if client and client._enabled:
                if logger:
                    logger.info("Dashboard integration fully enabled")
                return True
            else:
                if logger:
                    logger.info("Dashboard integration disabled - no URL configured")
                return False
        except ImportError:
            if logger:
                logger.debug("Dashboard client not available - API integration disabled")
            return False
        except Exception as e:
            if logger:
                logger.warning(f"Failed to setup dashboard client: {e}")
            return False
    
    except Exception as e:
        if logger:
            logger.warning(f"Dashboard integration setup failed: {e}")
        return False  