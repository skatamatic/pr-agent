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
                try:
                    await task
                except asyncio.CancelledError:
                    pass  # Expected when cancelling
                if logger:
                    logger.debug(f"Cancelled pending dashboard task: {task}")
    except Exception as e:
        if logger:
            logger.warning(f"Error waiting for dashboard tasks: {e}")
        # Cancel remaining tasks
        for task in tasks:
            if not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass  # Expected when cancelling

async def cleanup_all_dashboard_tasks():
    """Clean up all dashboard-related tasks and resources"""
    try:
        # Wait for pending tasks with a reasonable timeout
        await wait_for_pending_tasks(timeout=5.0)
        
        # Clear the pending tasks list
        with _task_lock:
            _pending_tasks.clear()
        
        # Clean up dashboard client (close aiohttp sessions)
        try:
            from pr_agent.log.dashboard_client import get_dashboard_client
            client = get_dashboard_client()
            if client:
                await client.close()
                # Reset the global client instance to prevent reuse of closed session
                import pr_agent.log.dashboard_client as dc_module
                dc_module._dashboard_client = None
                if logger:
                    logger.debug("Dashboard client session closed and reset")
        except ImportError:
            pass  # Dashboard client not available
        except Exception as e:
            if logger:
                logger.debug(f"Dashboard client cleanup error: {e}")
        
        # Clean up dashboard sink
        try:
            from pr_agent.log.dashboard_sink import cleanup_dashboard_sink
            await cleanup_dashboard_sink()
            # Reset the global sink instance
            import pr_agent.log.dashboard_sink as ds_module
            ds_module._dashboard_sink = None
        except ImportError:
            pass  # Dashboard sink not available
        except Exception as e:
            if logger:
                logger.debug(f"Dashboard sink cleanup error: {e}")
            
        if logger:
            logger.debug("Dashboard cleanup completed")
            
    except Exception as e:
        if logger:
            logger.debug(f"Dashboard cleanup error: {e}")

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
        elif 'dev.azure.com' in url or 'azure.com' in url:
            parts = url.split('/')
            # Handle Azure DevOps URL format: https://dev.azure.com/{org}/{project}/_git/{repo}/pullrequest/{pr_id}
            if '_git' in parts:
                git_index = parts.index('_git')
                if git_index >= 2 and git_index + 1 < len(parts):
                    project = parts[git_index - 1]
                    repo = parts[git_index + 1]
                    # Return cleaner format like GitHub: project/repo
                    return f"{project}/{repo}"
        
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
    # PR-Agent commands/tools
    REVIEW = "review"
    DESCRIBE = "describe"
    IMPROVE = "improve"
    TEST = "test"
    ADD_DOCS = "add_docs"
    UPDATE_CHANGELOG = "update_changelog"
    SIMILAR_ISSUE = "similar_issue"
    
    # Process stages
    STARTING = "starting"
    FETCHING_CONTEXT = "fetching_context"
    PROCESSING_PR = "processing_pr"
    SELF_REFLECTING = "self_reflecting"
    PUBLISHING_RESULTS = "publishing_results"
    FINALIZING = "finalizing"
    CLEANUP = "cleanup"
    
    # Generating stages (for detailed operation tracking)
    GENERATING_REVIEW = "generating_review"
    GENERATING_DESCRIPTION = "generating_description"
    GENERATING_SUGGESTIONS = "generating_suggestions"
    GENERATING_QUESTIONS = "generating_questions"
    GENERATING_LABELS = "generating_labels"
    ESTIMATING_DEV_TIME = "estimating_dev_time"


class JobContext:
    """Thread-local context for job and operation tracking"""
    
    _context = threading.local()
    _operation_creation_tasks = {}  # Track operation creation tasks by operation_id
    _current_step = {}  # Track current step by operation_id
    
    @classmethod
    def get_current_job_id(cls) -> Optional[str]:
        """Get the current job ID"""
        return getattr(cls._context, 'job_id', None)
    
    @classmethod
    def get_current_operation_id(cls) -> Optional[str]:
        """Get the current operation ID"""
        return getattr(cls._context, 'operation_id', None)
    
    @classmethod
    def get_current_step(cls) -> Optional[str]:
        """Get the current operation step"""
        operation_id = cls.get_current_operation_id()
        if operation_id:
            return cls._current_step.get(operation_id)
        return None
    
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
        
        # Send job creation to dashboard (error resilient with retries)
        if get_dashboard_client:
            max_retries = 3
            retry_count = 0
            job_created = False
            
            while retry_count < max_retries and not job_created:
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
                                
                                # For async context, we can't easily wait for completion here
                                # So we assume success and let the async task handle retries
                                job_created = True
                                if logger:
                                    logger.debug(f"Dashboard job creation queued for job {job_id} (attempt {retry_count + 1})")
                            else:
                                # Event loop exists but not running, use sync fallback
                                raise RuntimeError("Event loop not running")
                        except RuntimeError:
                            # No event loop running, use synchronous fallback with retries
                            try:
                                import requests
                                import time
                                
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
                                    job_created = True
                                    if logger:
                                        logger.info(f"✅ Dashboard job creation successful (sync) for job {job_id} (attempt {retry_count + 1})")
                                else:
                                    retry_count += 1
                                    if logger:
                                        logger.warning(f"⚠️ Dashboard job creation failed (sync): {response.status_code} - {response.text} (attempt {retry_count}/{max_retries})")
                                    
                                    # Exponential backoff: 0.5s, 1s, 2s
                                    if retry_count < max_retries:
                                        delay = 0.5 * (2 ** (retry_count - 1))
                                        time.sleep(delay)
                                        
                            except Exception as sync_e:
                                retry_count += 1
                                if logger:
                                    logger.warning(f"⚠️ Sync dashboard job creation failed for {job_id}: {sync_e} (attempt {retry_count}/{max_retries})")
                                
                                # Exponential backoff for exceptions too
                                if retry_count < max_retries:
                                    import time
                                    delay = 0.5 * (2 ** (retry_count - 1))
                                    time.sleep(delay)
                except Exception as e:
                    retry_count += 1
                    if logger:
                        logger.warning(f"⚠️ Dashboard job creation failed for {job_id}: {e} (attempt {retry_count}/{max_retries})")
                    
                    # Exponential backoff for outer exceptions too
                    if retry_count < max_retries:
                        import time
                        delay = 0.5 * (2 ** (retry_count - 1))
                        time.sleep(delay)
            
            # If all retries failed, log a BIG ERROR
            if not job_created and retry_count >= max_retries:
                error_msg = f"""
🚨🚨🚨 CRITICAL DASHBOARD ERROR 🚨🚨🚨
❌ FAILED TO CREATE JOB IN DASHBOARD AFTER {max_retries} RETRIES!
❌ Job ID: {job_id}
❌ Repository: {job_metadata.get('repository', 'Unknown')}
❌ Job Type: {job_metadata.get('job_type', 'Unknown')}
❌ This will cause orphaned operations and dashboard inconsistency!
❌ Please check dashboard connectivity and API endpoints!
🚨🚨🚨 CRITICAL DASHBOARD ERROR 🚨🚨🚨
"""
                if logger:
                    logger.error(error_msg)
                else:
                    print(error_msg)  # Fallback if logger is not available
    
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

    @classmethod
    def set_current_step(cls, step: str):
        """Set the current operation step"""
        operation_id = cls.get_current_operation_id()
        if operation_id:
            cls._current_step[operation_id] = step
            # Send step update to dashboard
            cls._send_step_update(operation_id, step)

    @classmethod
    def _send_step_update(cls, operation_id: str, step: str):
        """Send step update to dashboard"""
        if get_dashboard_client:
            try:
                client = get_dashboard_client()
                if client and client._enabled:
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            task = asyncio.create_task(client.update_operation_step(operation_id, step))
                            add_pending_task(task)
                    except RuntimeError:
                        # Sync fallback for step updates
                        try:
                            import requests
                            step_data = {'current_step': step}
                            
                            headers = {"Content-Type": "application/json"}
                            if client.api_key:
                                headers["Authorization"] = f"Bearer {client.api_key}"
                            
                            url = f"{client.dashboard_url.rstrip('/')}/api/operations/{operation_id}/step"
                            response = requests.post(url, json=step_data, headers=headers, timeout=10)
                            
                            if response.status_code == 200:
                                if logger:
                                    logger.debug(f"Dashboard step update successful (sync) for operation {operation_id}: {step}")
                            else:
                                if logger:
                                    logger.debug(f"Dashboard step update failed (sync) for operation {operation_id}: {response.status_code}")
                        except Exception as sync_e:
                            if logger:
                                logger.debug(f"Sync dashboard step update failed for operation {operation_id}: {sync_e}")
            except Exception:
                pass  # Ignore dashboard errors

    @classmethod
    def clear_current_step(cls, operation_id: str):
        """Clear the current step for an operation"""
        if operation_id in cls._current_step:
            del cls._current_step[operation_id]


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
        return logger
    
    context = {}
    
    job_id = JobContext.get_current_job_id()
    if job_id:
        context['job_id'] = job_id
        # Don't include all metadata to avoid duplication
        context.update({
            'repository': JobContext.get_job_metadata().get('repository'),
            'pr_url': JobContext.get_job_metadata().get('pr_url'),
            'command': JobContext.get_job_metadata().get('command')
        })
    
    operation_id = JobContext.get_current_operation_id()
    if operation_id:
        context['operation_id'] = operation_id
        # Don't include all metadata to avoid duplication
        context.update({
            'operation_type': JobContext.get_operation_metadata().get('operation_type')
        })
    
    # Remove None values
    context = {k: v for k, v in context.items() if v is not None}
    
    if context:
        return logger.bind(**context)
    
    return logger


def get_contextual_logger():
    """Get logger with current job/operation context automatically bound"""
    return bind_logger_context()


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
    
    # Clear current step when operation completes or fails
    if status.lower() in ['completed', 'failed']:
        JobContext.clear_current_step(operation_id)
        if logger:
            logger.debug(f"Cleared current step for {status} operation {operation_id}")
    
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


def update_specific_operation_ai_metrics(operation_id: str,
                                        model_used: Optional[str] = None,
                                        input_tokens: Optional[int] = None,
                                        output_tokens: Optional[int] = None,
                                        estimated_dev_hours_saved: Optional[float] = None):
    """Update a specific operation's AI metrics (error resilient)"""
    if not operation_id:
        if logger:
            logger.debug("No operation ID provided - skipping AI metrics update")
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
            ).info(f"Operation {operation_id} AI metrics updated: {', '.join(metrics_info)}")
    
    # Send to dashboard (error resilient)
    if get_dashboard_client:
        try:
            client = get_dashboard_client()
            if client and client._enabled:
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Update the specific operation's AI metrics
                        task = asyncio.create_task(client.update_operation_ai_metrics(
                            operation_id=operation_id,
                            model_used=model_used,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            estimated_dev_hours_saved=estimated_dev_hours_saved
                        ))
                        add_pending_task(task)
                        if logger:
                            logger.debug(f"Dashboard AI metrics update queued for specific operation {operation_id}")
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
                                logger.debug(f"Dashboard AI metrics update successful (sync) for specific operation {operation_id}")
                        else:
                            if logger:
                                logger.debug(f"Dashboard AI metrics update failed (sync) for specific operation {operation_id}: {response.status_code}")
                    except Exception as sync_e:
                        if logger:
                            logger.debug(f"Sync dashboard AI metrics update failed for specific operation {operation_id}: {sync_e}")
        except Exception as e:
            if logger:
                logger.debug(f"Dashboard AI metrics update failed for specific operation {operation_id}: {e}")


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


def set_operation_step(step: str):
    """Set the current operation step (with automatic prefixing)"""
    JobContext.set_current_step(step)
    if logger:
        logger.info(f"[{step}] - Starting operation step")


def update_operation_multi_model_ai_metrics(models_data: Dict[str, Dict[str, int]], 
                                           estimated_dev_hours_saved: Optional[float] = None):
    """
    Update operation AI metrics for multiple models
    
    Args:
        models_data: {"model_name": {"input_tokens": int, "output_tokens": int}, ...}
        estimated_dev_hours_saved: Hours saved estimate
    """
    operation_id = JobContext.get_current_operation_id()
    if not operation_id or not logger:
        return
    
    # Calculate totals
    total_input_tokens = sum(data.get('input_tokens', 0) for data in models_data.values())
    total_output_tokens = sum(data.get('output_tokens', 0) for data in models_data.values())
    
    logger.info(f"AI metrics updated - Models: {list(models_data.keys())}, "
                f"Total Input: {total_input_tokens}, Total Output: {total_output_tokens}, "
                f"Dev Hours: {estimated_dev_hours_saved}")
    
    # Send to dashboard (error resilient)
    if get_dashboard_client:
        try:
            client = get_dashboard_client()
            if client and client._enabled:
                try:
                    loop = asyncio.get_event_loop()
                    if loop.is_running():
                        # Wait for operation creation first
                        async def send_metrics_after_creation():
                            await JobContext.wait_for_operation_creation(operation_id)
                            await client.update_operation_multi_model_ai_metrics(
                                operation_id=operation_id,
                                models_data=models_data,
                                estimated_dev_hours_saved=estimated_dev_hours_saved
                            )
                        
                        task = asyncio.create_task(send_metrics_after_creation())
                        add_pending_task(task)
                        if logger:
                            logger.debug(f"Dashboard multi-model AI metrics update queued for {operation_id}")
                    else:
                        raise RuntimeError("Event loop not running")
                except RuntimeError:
                    # Sync fallback for multi-model metrics
                    try:
                        import requests
                        metrics_data = {
                            'models_data': models_data,
                            'estimated_dev_hours_saved': estimated_dev_hours_saved
                        }
                        # Remove None values
                        metrics_data = {k: v for k, v in metrics_data.items() if v is not None}
                        
                        if not metrics_data:
                            return
                        
                        headers = {"Content-Type": "application/json"}
                        if client.api_key:
                            headers["Authorization"] = f"Bearer {client.api_key}"
                        
                        url = f"{client.dashboard_url.rstrip('/')}/api/operations/{operation_id}/multi-model-ai-metrics"
                        response = requests.post(url, json=metrics_data, headers=headers, timeout=10)
                        
                        if response.status_code == 200:
                            if logger:
                                logger.debug(f"Dashboard multi-model AI metrics update successful (sync) for {operation_id}")
                        else:
                            if logger:
                                logger.debug(f"Dashboard multi-model AI metrics update failed (sync): {response.status_code}")
                    except Exception as sync_e:
                        if logger:
                            logger.debug(f"Sync dashboard multi-model AI metrics update failed for {operation_id}: {sync_e}")
        except ImportError:
            pass  # Dashboard client not available
        except Exception as e:
            if logger:
                logger.debug(f"Dashboard multi-model AI metrics update failed for {operation_id}: {e}")  