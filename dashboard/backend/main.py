from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from pathlib import Path
import asyncio
import logging
from datetime import datetime, timedelta

# Import configuration and database
from config import settings
from models import get_db, APIResponse, ConfigUpdate, Repository, RepositoryCreate, RepositoryUpdate, RepositoryDB, OperationDB, UserDB, User, UserLogin, ChangePassword
from websocket_manager import WebSocketManager

# Import services (Dependency Inversion Principle)
from services.health_service import HealthService
from services.metrics_service import MetricsService
from services.operation_service import OperationService, LogService
from services.config_service import ConfigService
from services.repository_service import RepositoryService
from services.job_service import JobService
from services.robust_cached_job_service import get_robust_cached_job_service
from services.auth_service import AuthService
from database import DatabaseManager, SessionLocal
from services.notification_service import NotificationService
from services.retention_service import RetentionService
from services.robust_cache_service import initialize_robust_cache_service, shutdown_robust_cache_service

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format=settings.log_format
)
logger = logging.getLogger(__name__)


class DashboardApplication:
    """Main application class following Single Responsibility Principle"""
    
    def __init__(self):
        try:
            # Setup lifespan first
            self._setup_background_tasks_lifespan()
            
            self.app = FastAPI(
                title=settings.app_name,
                description="API for monitoring PR Agent operations and logs",
                version="1.0.0",
                debug=settings.debug,
                lifespan=self.lifespan_handler
            )
            
            # Initialize services (Dependency Injection)
            self.database_manager = DatabaseManager()
            self.config_service = ConfigService(self.database_manager)
            self.notification_service = NotificationService(self.database_manager)
            
            # Pass config_service to health service as third parameter
            self.websocket_manager = WebSocketManager()
            
            # Pass config_service to health service as third parameter
            self.health_service = HealthService(
                self.database_manager, 
                self.notification_service, 
                self.config_service
            )
            
            self.metrics_service = MetricsService(self.websocket_manager)
            self.operation_service = OperationService()
            self.log_service = LogService()
            self.repository_service = RepositoryService()
            self.job_service = get_robust_cached_job_service()  # Use robust cached job service
            self.cached_job_service = self.job_service  # Keep alias for backward compatibility
            self.retention_service = RetentionService(self.database_manager)
            self.auth_service = AuthService()
            self.security = HTTPBearer(auto_error=False)
            
            # Setup application
            self._setup_middleware()
            self._initialize_auth()
            self._setup_routes()
            
        except Exception as e:
            logger.error(f"Failed to initialize dashboard application: {e}")
            # Create minimal app to prevent complete failure
            self.app = FastAPI(title="Dashboard Error", description="Dashboard failed to initialize")
            raise
    
    def _setup_middleware(self):
        """Configure CORS and other middleware"""
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
            # WebSocket specific headers
            expose_headers=["*"],
        )

    def _initialize_auth(self):
        """Initialize authentication and create default admin user"""
        try:
            with SessionLocal() as db:
                self.auth_service.create_default_admin(db)
                logger.info("Authentication initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize authentication: {e}")

    def get_current_user_dependency(self):
        """Create a dependency function for getting current user"""
        async def get_current_user(
            credentials: HTTPAuthorizationCredentials = Depends(self.security),
            db: Session = Depends(get_db)
        ) -> Optional[UserDB]:
            if not credentials:
                return None
            
            payload = self.auth_service.verify_token(credentials.credentials)
            if not payload:
                return None
                
            user = self.auth_service.get_user_by_id(db, payload.get("user_id"))
            if not user or not user.is_active:
                return None
                
            return user
        return get_current_user

    def require_auth_dependency(self):
        """Create a dependency function that requires authentication"""
        get_current_user = self.get_current_user_dependency()
        
        async def require_auth(current_user: UserDB = Depends(get_current_user)):
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required",
                    headers={"WWW-Authenticate": "Bearer"},
                )
            return current_user
        return require_auth
    
    def _setup_routes(self):
        """Setup all API routes using service methods"""
        
        # Create dependency functions
        get_current_user = self.get_current_user_dependency()
        require_auth = self.require_auth_dependency()
        
        # Authentication endpoints (no auth required)
        @self.app.post("/api/auth/login")
        async def login(user_credentials: UserLogin, db: Session = Depends(get_db)):
            user = self.auth_service.authenticate_user(db, user_credentials.username, user_credentials.password)
            if not user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid username or password"
                )
            
            token = self.auth_service.create_access_token(user.id, user.username)
            user_data = User(
                id=user.id,
                username=user.username,
                is_active=user.is_active,
                created_at=user.created_at,
                last_login=user.last_login
            )
            
            return APIResponse(data={"token": token, "user": user_data}, message="Login successful")

        @self.app.get("/api/auth/verify")
        async def verify_token(current_user: UserDB = Depends(get_current_user)):
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Invalid or expired token"
                )
            
            user_data = User(
                id=current_user.id,
                username=current_user.username,
                is_active=current_user.is_active,
                created_at=current_user.created_at,
                last_login=current_user.last_login
            )
            
            return APIResponse(data={"user": user_data}, message="Token valid")

        @self.app.post("/api/auth/change-password")
        async def change_password(
            password_data: ChangePassword, 
            current_user: UserDB = Depends(get_current_user),
            db: Session = Depends(get_db)
        ):
            if not current_user:
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Authentication required"
                )
            
            success = self.auth_service.change_password(
                db, current_user.id, 
                password_data.current_password, 
                password_data.new_password
            )
            
            if not success:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Current password is incorrect"
                )
            
            return APIResponse(data={}, message="Password changed successfully")
        
        # Health endpoints
        @self.app.get("/api/health")
        async def health_check():
            return await self.health_service.get_system_health()
        
        @self.app.get("/api/health/database")
        async def health_check_database():
            try:
                # Test database connectivity directly
                test_query = self.database_manager.get_notification_configs()
                return {"service": "database", "health": {"status": "connected", "message": "Database is accessible and responding"}}
            except Exception as e:
                return {"service": "database", "health": {"status": "error", "message": f"Database error: {str(e)}"}}
        
        @self.app.get("/api/health/config")
        async def health_check_config():
            # For config health, only check if config file is accessible and valid TOML
            try:
                config = await self.config_service.get_config()
                
                # Just verify we got a valid config object - API keys can come from env or repo-specific configs
                if isinstance(config, dict) and len(config) > 0:
                    return {"service": "pr_agent_config", "health": {"status": "connected", "message": "Configuration file accessible and valid"}}
                else:
                    return {"service": "pr_agent_config", "health": {"status": "misconfigured", "message": "Configuration file is empty or invalid"}}
                    
            except Exception as e:
                return {"service": "pr_agent_config", "health": {"status": "error", "message": f"Configuration error: {str(e)}"}}
        
        @self.app.get("/api/health/context")
        async def health_check_context():
            health_status = await self.health_service.get_system_health(use_cache=False)  # Force fresh check
            context_health = health_status.get('context_service', {'status': 'unknown', 'message': 'Context service health unavailable'})
            return {"service": "context_service", "health": context_health}
        
        @self.app.get("/api/status")
        async def get_status():
            return await self.health_service.get_simple_status()
        
        @self.app.get("/api/developer-mode")
        async def get_developer_mode():
            return {"enabled": settings.developer_mode}
        
        @self.app.get("/api/debug/paths")
        async def debug_paths():
            """Debug endpoint to check path resolution"""
            import os
            from pathlib import Path
            return {
                "cwd": os.getcwd(),
                "config_path": str(getattr(settings, 'pr_agent_config_path', 'Not found')),
                "config_exists": getattr(settings, 'pr_agent_config_path', Path()).exists(),
                "backup_path": str(getattr(settings, 'pr_agent_backup_path', 'Not found')),
                "dashboard_dir": str(Path(__file__).parent)
            }
        
        # Operations endpoints (protected)
        @self.app.get("/api/operations")
        async def get_operations(
            limit: int = 100,
            status: Optional[str] = None,
            repo: Optional[str] = None,
            db: Session = Depends(get_db),
            current_user: UserDB = Depends(require_auth)
        ):
            return await self.operation_service.get_operations(db, limit, status, repo)
        
        @self.app.get("/api/operations/{operation_id}")
        async def get_operation(operation_id: str, db: Session = Depends(get_db)):
            operation = await self.operation_service.get_operation(db, operation_id)
            if not operation:
                raise HTTPException(status_code=404, detail="Operation not found")
            return APIResponse(data=operation)
        
        # Jobs endpoints
        @self.app.get("/api/jobs")
        async def get_jobs(
            limit: int = 50,
            include_operations: bool = False,
            status: Optional[str] = None,
            job_type: Optional[str] = None,
            repository: Optional[str] = None,
            ensure_counts: bool = True
        ):
            jobs = await self.cached_job_service.get_jobs(
                limit=limit, 
                include_operations=include_operations,
                status=status,
                job_type=job_type,
                repository=repository,
                ensure_counts=ensure_counts
            )
            return APIResponse(data=jobs, total=len(jobs))
        
        @self.app.get("/api/jobs/{job_id}")
        async def get_job(job_id: str, include_operations: bool = True):
            job = await self.cached_job_service.get_job(job_id, include_operations=include_operations)
            if not job:
                raise HTTPException(status_code=404, detail="Job not found")
            return APIResponse(data=job)
        
        @self.app.get("/api/jobs/{job_id}/operations")
        async def get_job_operations(job_id: str):
            """Get operations for a specific job"""
            operations = await self.cached_job_service.get_operations(job_id=job_id)
            return APIResponse(data={"operations": operations})

        # NEW: Job and Operation Management API Endpoints for PR-Agent Integration
        @self.app.post("/api/jobs/create")
        async def create_job(job_data: dict):
            """Create a new job from PR-Agent"""
            try:
                from models import JobType, JobStatus
                from datetime import datetime
                
                # If job_id is provided, use create_job_with_data
                if job_data.get('job_id'):
                    # Prepare data for create_job_with_data
                    now = datetime.utcnow()
                    job_dict = {
                        'job_id': job_data.get('job_id'),
                        'job_type': job_data.get('job_type', 'manual'),
                        'source': job_data.get('source', 'unknown'),
                        'status': JobStatus.RUNNING.value,
                        'repository': job_data.get('repository'),
                        'pr_url': job_data.get('pr_url'),
                        'trigger_user': job_data.get('trigger_user'),
                        'trigger_event': job_data.get('trigger_event'),
                        'installation_id': job_data.get('installation_id'),
                        'request_id': job_data.get('request_id'),
                        'webhook_payload': job_data.get('webhook_payload'),
                        'started_at': job_data.get('started_at', now.isoformat()),
                        'last_updated': now.isoformat(),
                        'operations_count': 0,
                        'completed_operations': 0,
                        'failed_operations': 0,
                        'total_logs': 0,
                        'error_count': 0,
                        'warning_count': 0,
                        'pr_number': job_data.get('pr_number'),
                        'pr_title': job_data.get('pr_title')
                    }
                    job_id = await self.cached_job_service.create_job_with_data(job_dict)
                else:
                    # Use regular create_job method
                    job_type = JobType(job_data.get('job_type', 'manual'))
                    job_id = await self.cached_job_service.create_job(
                        job_type=job_type,
                        source=job_data.get('source', 'unknown'),
                        repository=job_data.get('repository'),
                        pr_url=job_data.get('pr_url'),
                        trigger_user=job_data.get('trigger_user'),
                        trigger_event=job_data.get('trigger_event'),
                        installation_id=job_data.get('installation_id'),
                        request_id=job_data.get('request_id'),
                        webhook_payload=job_data.get('webhook_payload')
                    )
                
                # Broadcast new job via WebSocket
                try:
                    broadcast_job_data = {
                        "job_id": job_id,
                        "job_type": job_data.get('job_type', 'manual'),
                        "repository": job_data.get('repository'),
                        "pr_url": job_data.get('pr_url'),
                        "trigger_user": job_data.get('trigger_user'),
                        "status": "running",
                        "started_at": job_data.get('started_at'),
                        "pr_number": job_data.get('pr_number'),
                        "pr_title": job_data.get('pr_title')
                    }
                    await self.websocket_manager.broadcast({
                        "type": "job_update",
                        "data": broadcast_job_data
                    })
                except Exception as ws_error:
                    logger.warning(f"Failed to broadcast new job: {ws_error}")
                
                return APIResponse(data={"job_id": job_id}, message="Job created successfully")
            except Exception as e:
                logger.error(f"Failed to create job: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to create job: {str(e)}")

        @self.app.post("/api/jobs/{job_id}/status")
        async def update_job_status(job_id: str, status_data: dict):
            """Update job status from PR-Agent"""
            try:
                from models import JobStatus
                
                # COMPREHENSIVE mapping of ALL possible incoming status strings to valid JobStatus enum values
                status_mapping = {
                    # Direct enum mappings (exact matches)
                    'running': JobStatus.RUNNING,
                    'completed': JobStatus.COMPLETED,
                    'failed': JobStatus.FAILED,
                    'cancelled': JobStatus.CANCELLED,
                    
                    # Common variations and aliases
                    'canceled': JobStatus.CANCELLED,           # US spelling
                    'cancelling': JobStatus.CANCELLED,         # cancelling -> cancelled
                    'canceling': JobStatus.CANCELLED,          # US spelling
                    'pending': JobStatus.RUNNING,              # pending -> running
                    'queued': JobStatus.RUNNING,               # queued -> running
                    'starting': JobStatus.RUNNING,             # starting -> running
                    'processing': JobStatus.RUNNING,           # processing -> running
                    'in_progress': JobStatus.RUNNING,          # in_progress -> running
                    'active': JobStatus.RUNNING,               # active -> running
                    'success': JobStatus.COMPLETED,            # success -> completed
                    'successful': JobStatus.COMPLETED,         # successful -> completed
                    'done': JobStatus.COMPLETED,               # done -> completed
                    'finished': JobStatus.COMPLETED,           # finished -> completed
                    'complete': JobStatus.COMPLETED,           # complete -> completed
                    'error': JobStatus.FAILED,                 # error -> failed
                    'errored': JobStatus.FAILED,               # errored -> failed
                    'failure': JobStatus.FAILED,               # failure -> failed
                    'aborted': JobStatus.FAILED,               # aborted -> failed
                    'terminated': JobStatus.FAILED,            # terminated -> failed
                    'interrupted': JobStatus.FAILED,           # interrupted -> failed
                    'timeout': JobStatus.FAILED,               # timeout -> failed
                    'timed_out': JobStatus.FAILED,             # timed_out -> failed
                    'stopped': JobStatus.CANCELLED,            # stopped -> cancelled
                    'stop': JobStatus.CANCELLED,               # stop -> cancelled
                    'abort': JobStatus.CANCELLED,              # abort -> cancelled
                }
                
                incoming_status = status_data.get('status', '').lower()
                status = status_mapping.get(incoming_status, JobStatus.RUNNING)
                
                await self.cached_job_service.update_job_status(
                    job_id=job_id,
                    status=status,
                    error_details=status_data.get('error_details'),
                    result_summary=status_data.get('result_summary')
                )
                
                # Broadcast job update via WebSocket
                try:
                    job_data = {
                        "job_id": job_id,
                        "status": status_data.get('status'),
                        "error_details": status_data.get('error_details'),
                        "result_summary": status_data.get('result_summary'),
                        "completed_at": status_data.get('completed_at'),
                        "duration": status_data.get('duration')
                    }
                    await self.websocket_manager.broadcast({
                        "type": "job_update",
                        "data": job_data
                    })
                except Exception as ws_error:
                    logger.warning(f"Failed to broadcast job update: {ws_error}")
                
                return APIResponse(data={"status": "updated"}, message="Job status updated successfully")
            except Exception as e:
                logger.error(f"Failed to update job status: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to update job status: {str(e)}")

        @self.app.post("/api/operations/create")
        async def create_operation(operation_data: dict):
            """Create a new operation from PR-Agent"""
            try:
                from models import OperationStatus
                from datetime import datetime
                
                # If operation_id is provided, use create_operation_with_data
                if operation_data.get('operation_id'):
                    # Prepare data for create_operation_with_data
                    now = datetime.utcnow()
                    operation_dict = {
                        'operation_id': operation_data.get('operation_id'),
                        'job_id': operation_data.get('job_id'),
                        'operation_type': operation_data.get('operation_type', 'starting'),
                        'command': operation_data.get('command'),
                        'status': OperationStatus.STARTING.value,
                        'repo': operation_data.get('repo'),
                        'pr_url': operation_data.get('pr_url'),
                        'installation_id': operation_data.get('installation_id'),
                        'sender': operation_data.get('sender'),
                        'request_id': operation_data.get('request_id'),
                        'started_at': operation_data.get('started_at', now.isoformat()),
                        'last_updated': now.isoformat()
                    }
                    operation_id = await self.cached_job_service.create_operation_with_data(operation_dict)
                else:
                    # Use regular create_operation method
                    operation_id = await self.cached_job_service.create_operation(
                        job_id=operation_data.get('job_id'),
                        operation_type=operation_data.get('operation_type', 'starting'),
                        command=operation_data.get('command'),
                        repo=operation_data.get('repo'),
                        pr_url=operation_data.get('pr_url'),
                        installation_id=operation_data.get('installation_id'),
                        sender=operation_data.get('sender'),
                        request_id=operation_data.get('request_id')
                    )
                
                # Broadcast new operation via WebSocket
                try:
                    broadcast_operation_data = {
                        "operation_id": operation_id,
                        "job_id": operation_data.get('job_id'),
                        "operation_type": operation_data.get('operation_type', 'starting'),
                        "command": operation_data.get('command'),
                        "repo": operation_data.get('repo'),
                        "status": "starting",
                        "started_at": operation_data.get('started_at')
                    }
                    await self.websocket_manager.broadcast({
                        "type": "operation_update",
                        "data": broadcast_operation_data
                    })
                except Exception as ws_error:
                    logger.warning(f"Failed to broadcast new operation: {ws_error}")
                
                return APIResponse(data={"operation_id": operation_id}, message="Operation created successfully")
            except Exception as e:
                logger.error(f"Failed to create operation: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to create operation: {str(e)}")

        @self.app.post("/api/operations/{operation_id}/status")
        async def update_operation_status(operation_id: str, status_data: dict):
            """Update operation status from PR-Agent"""
            try:
                from models import OperationStatus
                
                # COMPREHENSIVE mapping of ALL possible incoming status strings to valid OperationStatus enum values
                status_mapping = {
                    # Direct enum mappings (exact matches)
                    'starting': OperationStatus.STARTING,
                    'processing': OperationStatus.PROCESSING,
                    'fetching_context': OperationStatus.FETCHING_CONTEXT,
                    'context_completed': OperationStatus.CONTEXT_COMPLETED,
                    'context_disabled': OperationStatus.CONTEXT_DISABLED,
                    'context_failed': OperationStatus.CONTEXT_FAILED,
                    'preparing': OperationStatus.PREPARING,
                    'self_reflecting': OperationStatus.SELF_REFLECTING,
                    'publishing': OperationStatus.PUBLISHING,
                    'completed': OperationStatus.COMPLETED,
                    'failed': OperationStatus.FAILED,
                    'skipped': OperationStatus.SKIPPED,
                    
                    # Common variations and aliases
                    'running': OperationStatus.PROCESSING,          # running -> processing
                    'cancelled': OperationStatus.FAILED,           # cancelled -> failed (no cancelled state for operations)
                    'canceled': OperationStatus.FAILED,            # US spelling
                    'cancelling': OperationStatus.FAILED,          # cancelling -> failed
                    'canceling': OperationStatus.FAILED,           # US spelling
                    'pending': OperationStatus.STARTING,           # pending -> starting
                    'queued': OperationStatus.STARTING,            # queued -> starting 
                    'in_progress': OperationStatus.PROCESSING,     # in_progress -> processing
                    'success': OperationStatus.COMPLETED,          # success -> completed
                    'successful': OperationStatus.COMPLETED,       # successful -> completed
                    'done': OperationStatus.COMPLETED,             # done -> completed
                    'finished': OperationStatus.COMPLETED,         # finished -> completed
                    'error': OperationStatus.FAILED,               # error -> failed
                    'errored': OperationStatus.FAILED,             # errored -> failed
                    'aborted': OperationStatus.FAILED,             # aborted -> failed
                    'terminated': OperationStatus.FAILED,          # terminated -> failed
                    'interrupted': OperationStatus.FAILED,         # interrupted -> failed
                    'timeout': OperationStatus.FAILED,             # timeout -> failed
                    'timed_out': OperationStatus.FAILED,           # timed_out -> failed
                    
                    # Context-specific mappings
                    'fetching': OperationStatus.FETCHING_CONTEXT,  # fetching -> fetching_context
                    'context': OperationStatus.FETCHING_CONTEXT,   # context -> fetching_context
                    'analyzing': OperationStatus.PROCESSING,       # analyzing -> processing
                    'generating': OperationStatus.PROCESSING,      # generating -> processing
                    'reviewing': OperationStatus.PROCESSING,       # reviewing -> processing
                    'improving': OperationStatus.PROCESSING,       # improving -> processing
                    'describing': OperationStatus.PROCESSING,      # describing -> processing
                }
                
                incoming_status = status_data.get('status', '').lower()
                status = status_mapping.get(incoming_status, OperationStatus.PROCESSING)
                
                await self.cached_job_service.update_operation_status(
                    operation_id=operation_id,
                    status=status,
                    error_details=status_data.get('error_details'),
                    result_data=status_data.get('result_data')
                )
                
                # Broadcast operation update via WebSocket
                try:
                    operation_data = {
                        "operation_id": operation_id,
                        "status": status_data.get('status'),
                        "error_details": status_data.get('error_details'),
                        "result_data": status_data.get('result_data'),
                        "completed_at": status_data.get('completed_at'),
                        "duration": status_data.get('duration')
                    }
                    await self.websocket_manager.broadcast({
                        "type": "operation_update", 
                        "data": operation_data
                    })
                except Exception as ws_error:
                    logger.warning(f"Failed to broadcast operation update: {ws_error}")
                
                return APIResponse(data={"status": "updated"}, message="Operation status updated successfully")
            except Exception as e:
                logger.error(f"Failed to update operation status: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to update operation status: {str(e)}")

        @self.app.post("/api/operations/{operation_id}/ai-metrics")
        async def update_operation_ai_metrics(operation_id: str, metrics_data: dict, db: Session = Depends(get_db)):
            """Update operation AI metrics from PR-Agent"""
            
            try:
                # Use cached service - no race conditions!
                success = await self.cached_job_service.update_operation_ai_metrics(
                    operation_id=operation_id,
                    model_used=metrics_data.get('model_used'),
                    input_tokens=metrics_data.get('input_tokens'),
                    output_tokens=metrics_data.get('output_tokens'),
                    estimated_dev_hours_saved=metrics_data.get('estimated_dev_hours_saved')
                )
                
                if success:
                    logger.info(f"Operation {operation_id} AI metrics updated successfully in cache")
                    
                    # CRITICAL: Auto-recalculate all metrics from scratch for accuracy
                    try:
                        # Instead of incremental updates (which can get out of sync), 
                        # just recalculate everything from scratch - it's more reliable!
                        await self.metrics_service.recalculate_metrics_from_operations(db)
                        logger.info(f"DEBUG: Metrics recalculated from all operations after {operation_id}")
                    except Exception as e:
                        logger.error(f"Failed to recalculate metrics after operation {operation_id}: {e}")
                        import traceback
                        logger.error(f"Traceback: {traceback.format_exc()}")
                    
                    # Note: WebSocket broadcast is handled by recalculate_metrics_from_operations()
                    # No need to broadcast again here to avoid duplicate/conflicting messages
                    
                    return APIResponse(data={"status": "updated"}, message="AI metrics updated successfully")
                else:
                    logger.warning(f"Operation {operation_id} not found in cache")
                    raise HTTPException(status_code=404, detail="Operation not found")
                    
            except HTTPException:
                # Re-raise HTTP exceptions as-is
                raise
            except Exception as e:
                logger.error(f"Failed to update AI metrics: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to update AI metrics: {str(e)}")
        
        # Logs endpoints
        @self.app.get("/api/logs")
        async def get_logs(
            limit: int = 1000,
            level: Optional[str] = None,
            search: Optional[str] = None,
            repo: Optional[str] = None,
            job_id: Optional[str] = None,
            operation_id: Optional[str] = None,
            db: Session = Depends(get_db)
        ):
            logs = await self.job_service.get_logs(
                limit=limit,
                level=level,
                job_id=job_id,
                operation_id=operation_id,
                repository=repo
            )
            return APIResponse(data={"logs": logs}, message=f"Retrieved {len(logs)} logs")
        
        @self.app.get("/api/logs/job/{job_id}")
        async def get_logs_by_job(job_id: str, db: Session = Depends(get_db)):
            logs = await self.job_service.get_logs(job_id=job_id, limit=10000)
            return APIResponse(data={"logs": logs}, message=f"Retrieved {len(logs)} logs for job {job_id}")
        
        @self.app.get("/api/logs/operation/{operation_id}")
        async def get_logs_by_operation(operation_id: str, db: Session = Depends(get_db)):
            logs = await self.job_service.get_logs(operation_id=operation_id, limit=10000)
            return APIResponse(data={"logs": logs}, message=f"Retrieved {len(logs)} logs for operation {operation_id}")
        
        # Log ingestion endpoints
        @self.app.post("/logs/immediate")
        async def receive_immediate_log(log_data: dict, db: Session = Depends(get_db)):
            try:
                # Use robust cached job service for logs too
                log_id = await self.job_service.create_log_entry(
                    level=log_data.get('level', 'INFO'),
                    message=log_data.get('message', ''),
                    source=log_data.get('source') or log_data.get('module', 'unknown'),
                    job_id=log_data.get('job_id'),
                    operation_id=log_data.get('operation_id'),
                    repository=log_data.get('repository') or log_data.get('repo'),
                    status=log_data.get('status'),
                    module=log_data.get('module'),
                    function=log_data.get('function'),
                    severity="high" if log_data.get('level') in ["ERROR", "CRITICAL"] else "normal"
                )
                
                # Update operation status if needed
                if log_data.get('status'):
                    await self.operation_service.update_operation_status(db, log_data)
                
                # Extract and update metrics if present
                if any(key in log_data for key in ['model_used', 'input_tokens', 'output_tokens', 'estimated_dev_hours_saved']):
                    await self.metrics_service.update_metrics_from_operation(db, log_data)
                
                # Broadcast to WebSocket clients
                await self.websocket_manager.broadcast({
                    "type": "log",
                    "data": {
                        "id": log_id,
                        "timestamp": log_data.get('timestamp'),
                        "level": log_data.get('level'),
                        "message": log_data.get('message'),
                        "status": log_data.get('status'),
                        "source": log_data.get('source'),
                        "job_id": log_data.get('job_id'),
                        "operation_id": log_data.get('operation_id'),
                        "repository": log_data.get('repository'),
                        "repo": log_data.get('repo'),
                        "command": log_data.get('command'),
                        "pr_url": log_data.get('pr_url'),
                        "module": log_data.get('module'),
                        "function": log_data.get('function'),
                        "severity": "high" if log_data.get('level') in ["ERROR", "CRITICAL"] else "normal"
                    }
                })
                
                return {"status": "received", "id": log_id}
                
            except Exception as e:
                logger.error(f"Failed to process immediate log: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to process log: {str(e)}")
        
        @self.app.post("/logs/batch")
        async def receive_batch_logs(batch_data: dict, db: Session = Depends(get_db)):
            try:
                logs = batch_data.get('logs', [])
                received_log_ids = []
                broadcast_logs = []
                
                # Process each log using robust cached job service
                for log_data in logs:
                    log_id = await self.job_service.create_log_entry(
                        level=log_data.get('level', 'INFO'),
                        message=log_data.get('message', ''),
                        source=log_data.get('source') or log_data.get('module', 'unknown'),
                        job_id=log_data.get('job_id'),
                        operation_id=log_data.get('operation_id'),
                        repository=log_data.get('repository') or log_data.get('repo'),
                        status=log_data.get('status'),
                        module=log_data.get('module'),
                        function=log_data.get('function'),
                        severity="high" if log_data.get('level') in ["ERROR", "CRITICAL"] else "normal"
                    )
                    received_log_ids.append({'id': log_id, 'message': log_data.get('message', '')})
                    
                    # Build full log data for broadcast
                    broadcast_logs.append({
                        "id": log_id,
                        "timestamp": log_data.get('timestamp'),
                        "level": log_data.get('level'),
                        "message": log_data.get('message'),
                        "status": log_data.get('status'),
                        "source": log_data.get('source'),
                        "job_id": log_data.get('job_id'),
                        "operation_id": log_data.get('operation_id'),
                        "repository": log_data.get('repository'),
                        "repo": log_data.get('repo'),
                        "command": log_data.get('command'),
                        "pr_url": log_data.get('pr_url'),
                        "module": log_data.get('module'),
                        "function": log_data.get('function'),
                        "severity": "high" if log_data.get('level') in ["ERROR", "CRITICAL"] else "normal"
                    })
                
                # Update operations for logs with status
                for log_data in logs:
                    if log_data.get('status'):
                        await self.operation_service.update_operation_status(db, log_data)
                    
                    # Extract and update metrics if present
                    if any(key in log_data for key in ['model_used', 'input_tokens', 'output_tokens', 'estimated_dev_hours_saved']):
                        await self.metrics_service.update_metrics_from_operation(db, log_data)
                
                # Broadcast FULL log data to WebSocket clients
                for log_broadcast in broadcast_logs:
                    await self.websocket_manager.broadcast({
                        "type": "log",
                        "data": log_broadcast
                    })
                
                return {"status": "received", "count": len(received_log_ids)}
                
            except Exception as e:
                logger.error(f"Failed to process batch logs: {e}")
                raise HTTPException(status_code=500, detail="Failed to process logs")
        
        # System status endpoints
        @self.app.get("/api/status/realtime")
        async def get_realtime_status(db: Session = Depends(get_db)):
            """Get real-time system status"""
            try:
                # Get system health status
                health_status = await self.health_service.get_system_health(use_cache=True)
                
                # Get basic operation counts
                from models import OperationDB, JobDB
                total_ops = db.query(OperationDB).count()
                active_ops = db.query(OperationDB).filter(
                    OperationDB.status.in_(["processing", "fetching_context", "preparing", "self_reflecting", "publishing"])
                ).count()
                completed_ops = db.query(OperationDB).filter(OperationDB.status == "completed").count()
                failed_ops = db.query(OperationDB).filter(OperationDB.status == "failed").count()
                
                # Get recent operations for activity feed
                recent_ops = db.query(OperationDB).order_by(OperationDB.started_at.desc()).limit(5).all()
                recent_operations = []
                for op in recent_ops:
                    recent_operations.append({
                        "id": op.operation_id,
                        "command": op.command,
                        "repo": op.repo,
                        "status": op.status,
                        "started_at": op.started_at.isoformat() if op.started_at else None,
                        "duration": op.duration
                    })
                
                # Calculate success rate
                success_rate = 0
                if total_ops > 0:
                    success_rate = (completed_ops / total_ops) * 100
                
                # Determine overall system health
                overall_health = health_status.get('overall', {}).get('status', 'unknown')
                
                return APIResponse(data={
                    "timestamp": datetime.utcnow().isoformat(),
                    "system_health": overall_health,
                    "health_details": health_status,
                    "operations": {
                        "total": total_ops,
                        "active": active_ops,
                        "completed": completed_ops,
                        "failed": failed_ops,
                        "success_rate": round(success_rate, 1)
                    },
                    "recent_operations": recent_operations
                }, message="Real-time status retrieved")
                
            except Exception as e:
                logger.error(f"Error getting realtime status: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/system/alerts")
        async def get_system_alerts(db: Session = Depends(get_db)):
            """Get system alerts and warnings"""
            try:
                alerts = []
                
                # Check for stuck operations
                from datetime import timedelta
                stuck_cutoff = datetime.utcnow() - timedelta(minutes=30)
                stuck_ops = db.query(OperationDB).filter(
                    OperationDB.status.in_(["processing", "fetching_context", "preparing"]),
                    OperationDB.started_at < stuck_cutoff
                ).count()
                
                if stuck_ops > 0:
                    alerts.append({
                        "type": "warning",
                        "message": f"{stuck_ops} operations may be stuck (running > 30 minutes)",
                        "severity": "medium",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                
                # Check health status for errors
                health_status = await self.health_service.get_system_health(use_cache=True)
                for service_name, service_health in health_status.items():
                    if service_name != 'overall' and isinstance(service_health, dict):
                        status = service_health.get('status', 'unknown')
                        if status in ['error', 'unreachable']:
                            alerts.append({
                                "type": "error",
                                "message": f"{service_name.title()} service is {status}: {service_health.get('message', 'No details')}",
                                "severity": "high",
                                "timestamp": datetime.utcnow().isoformat()
                            })
                
                return APIResponse(data={"alerts": alerts, "total": len(alerts)}, message="System alerts retrieved")
                
            except Exception as e:
                logger.error(f"Error getting system alerts: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/system/performance")
        async def get_system_performance(db: Session = Depends(get_db)):
            """Get system performance metrics"""
            try:
                from datetime import timedelta
                
                # Get performance data for last 24 hours
                day_ago = datetime.utcnow() - timedelta(hours=24)
                recent_ops = db.query(OperationDB).filter(OperationDB.started_at >= day_ago).all()
                
                # Calculate performance metrics
                total_ops = len(recent_ops)
                completed_ops = len([op for op in recent_ops if op.status == "completed"])
                failed_ops = len([op for op in recent_ops if op.status == "failed"])
                
                # Calculate average response time
                completed_with_duration = [op for op in recent_ops if op.status == "completed" and op.duration]
                avg_response_time = 0
                if completed_with_duration:
                    avg_response_time = sum(op.duration for op in completed_with_duration) / len(completed_with_duration)
                
                # Calculate success rate
                success_rate = (completed_ops / total_ops * 100) if total_ops > 0 else 0
                
                return APIResponse(data={
                    "summary": {
                        "total_operations": total_ops,
                        "completed_operations": completed_ops,
                        "failed_operations": failed_ops,
                        "success_rate": round(success_rate, 1),
                        "avg_response_time": round(avg_response_time, 2)
                    },
                    "period": "24h",
                    "timestamp": datetime.utcnow().isoformat()
                }, message="System performance metrics retrieved")
                
            except Exception as e:
                logger.error(f"Error getting system performance: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        # Configuration endpoints
        @self.app.get("/api/config")
        async def get_config():
            config = await self.config_service.get_config()
            return APIResponse(data=config)
        
        @self.app.post("/api/config")
        async def update_config(config_update: ConfigUpdate):
            result = await self.config_service.update_config(config_update.config)
            return result


        
        # Repository endpoints
        @self.app.get("/api/repositories")
        async def get_repositories(
            limit: int = 100,
            provider: Optional[str] = None,
            active_only: bool = False,
            db: Session = Depends(get_db)
        ):
            return await self.repository_service.get_repositories(db, limit, provider, active_only)
        
        @self.app.post("/api/repositories")
        async def create_repository(repo_data: RepositoryCreate, db: Session = Depends(get_db)):
            try:
                repository = await self.repository_service.create_repository(db, repo_data)
                return APIResponse(data=repository, message="Repository created successfully")
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
        
        @self.app.get("/api/repositories/names")
        async def get_repository_names(active_only: bool = True, db: Session = Depends(get_db)):
            names = await self.repository_service.get_repository_names(db, active_only)
            return APIResponse(data=names, message=f"Found {len(names)} repository names")
        
        @self.app.get("/api/repositories/health")
        async def get_repositories_health(db: Session = Depends(get_db)):
            """Get health status of all repositories"""
            try:
                # Get basic repository counts
                repositories = db.query(RepositoryDB).filter(RepositoryDB.is_active == True).all()
                
                total = len(repositories)
                healthy = len([r for r in repositories if r.runner_status == "running"])
                unhealthy = total - healthy
                
                # Build response matching expected format
                response_data = {
                    "data": {
                        "total_repos": total,
                        "healthy_repos": healthy,
                        "unhealthy_repos": unhealthy,
                        "overall_status": "running" if unhealthy == 0 else "error",
                        "last_updated": datetime.utcnow().isoformat()
                    },
                    "message": "Repository health retrieved successfully"
                }
                
                return response_data
                    
            except Exception as e:
                logger.error(f"Error getting repository health: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/repositories/update-configs")
        async def update_all_repository_configs(db: Session = Depends(get_db)):
            """Update configuration status for all repositories"""
            try:
                from services.runner_health_service import RunnerHealthService
                
                runner_service = RunnerHealthService()
                try:
                    results = await runner_service.update_all_repository_configs(db)
                    return APIResponse(data=results, message="Repository configurations updated")
                finally:
                    await runner_service.close_session()
                    
            except Exception as e:
                logger.error(f"Error updating repository configs: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/repositories/token-permissions")
        async def get_token_permission_requirements():
            """Get information about required GitHub token permissions"""
            return APIResponse(data={
                "github": {
                    "fine_grained_token_permissions": {
                        "required": [
                            {
                                "permission": "Metadata",
                                "access": "Read",
                                "description": "Required for basic repository access and information"
                            }
                        ],
                        "optional": [
                            {
                                "permission": "Actions", 
                                "access": "Read",
                                "description": "Required for monitoring self-hosted runners (optional)"
                            },
                            {
                                "permission": "Contents",
                                "access": "Read", 
                                "description": "Required for reading .pr_agent.toml configuration files"
                            }
                        ]
                    },
                    "classic_token_scopes": [
                        "repo (full repository access)"
                    ],
                    "setup_instructions": {
                        "fine_grained_token": [
                            "1. Go to GitHub Settings > Developer settings > Personal access tokens > Fine-grained tokens",
                            "2. Click 'Generate new token'",
                            "3. Select your repository or organization",
                            "4. Under 'Repository permissions', set:",
                            "   - Metadata: Read (required)",
                            "   - Actions: Read (optional, for runner monitoring)",
                            "   - Contents: Read (optional, for config file reading)",
                            "5. Generate and copy the token"
                        ],
                        "classic_token": [
                            "1. Go to GitHub Settings > Developer settings > Personal access tokens > Tokens (classic)",
                            "2. Click 'Generate new token (classic)'",
                            "3. Select 'repo' scope",
                            "4. Generate and copy the token"
                        ]
                    }
                }
            }, message="Token permission requirements retrieved")
        
        # Parameterized routes come after specific routes
        @self.app.get("/api/repositories/{repo_id}")
        async def get_repository(repo_id: int, db: Session = Depends(get_db)):
            repository = await self.repository_service.get_repository(db, repo_id)
            if not repository:
                raise HTTPException(status_code=404, detail="Repository not found")
            return APIResponse(data=repository)
        
        @self.app.put("/api/repositories/{repo_id}")
        async def update_repository(repo_id: int, repo_update: RepositoryUpdate, db: Session = Depends(get_db)):
            try:
                # Check if tokens are being updated
                token_updated = hasattr(repo_update, 'github_token') and repo_update.github_token is not None
                token_updated = token_updated or (hasattr(repo_update, 'azure_pat') and repo_update.azure_pat is not None)
                
                repository = await self.repository_service.update_repository(db, repo_id, repo_update)
                if not repository:
                    raise HTTPException(status_code=404, detail="Repository not found")
                
                # If token was updated, validate it by performing basic health check
                if token_updated:
                    try:
                        from services.runner_health_service import RunnerHealthService
                        from models import RepositoryDB
                        
                        # Get the updated repository from database
                        repo = db.query(RepositoryDB).filter(RepositoryDB.id == repo_id).first()
                        if repo:
                            runner_service = RunnerHealthService()
                            try:
                                # Validate token by checking repository access
                                validation_result = await runner_service.validate_repository_token(db, repo)
                                
                                if not validation_result.get("valid", False):
                                    # Token validation failed - update status and raise error
                                    repo.runner_status = "error"
                                    repo.runner_error = validation_result.get("error", "Token validation failed")
                                    db.commit()
                                    raise HTTPException(status_code=400, detail=f"Token validation failed: {validation_result.get('error', 'Invalid token')}")
                                
                                # Token is valid, update health status
                                repo.runner_status = validation_result.get("status", "healthy")
                                repo.runner_error = None
                                if validation_result.get("last_seen"):
                                    repo.runner_last_seen = validation_result["last_seen"]
                                db.commit()
                                
                            finally:
                                await runner_service.close_session()
                    except HTTPException:
                        raise  # Re-raise HTTP exceptions
                    except Exception as e:
                        logger.warning(f"Token validation failed for repository {repo_id}: {e}")
                        # Don't fail the update, but mark token as potentially invalid
                        repo = db.query(RepositoryDB).filter(RepositoryDB.id == repo_id).first()
                        if repo:
                            repo.runner_status = "warning" 
                            repo.runner_error = f"Token validation inconclusive: {str(e)}"
                            db.commit()
                
                return APIResponse(data=repository, message="Repository updated successfully")
            except HTTPException:
                raise  # Re-raise HTTP exceptions
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
        
        @self.app.delete("/api/repositories/{repo_id}")
        async def delete_repository(repo_id: int, db: Session = Depends(get_db)):
            try:
                deleted = await self.repository_service.delete_repository(db, repo_id)
                if not deleted:
                    raise HTTPException(status_code=404, detail="Repository not found")
                return APIResponse(data={"deleted": True}, message="Repository deleted successfully")
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
        
        @self.app.post("/api/repositories/{repo_id}/check-health")
        async def check_repository_health(repo_id: int, db: Session = Depends(get_db)):
            """Trigger health check for a specific repository"""
            try:
                from services.runner_health_service import RunnerHealthService
                from models import RepositoryDB
                
                # Get repository
                repo = db.query(RepositoryDB).filter(RepositoryDB.id == repo_id).first()
                if not repo:
                    raise HTTPException(status_code=404, detail="Repository not found")
                
                runner_service = RunnerHealthService()
                try:
                    result = await runner_service.check_repository_runner_health(db, repo)
                    
                    # Update repository with results
                    repo.runner_status = result["status"]
                    repo.runner_error = result["error"]
                    if result["last_seen"]:
                        repo.runner_last_seen = result["last_seen"]
                    db.commit()
                    
                    return APIResponse(data=result, message="Health check completed")
                finally:
                    await runner_service.close_session()
                    
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error checking repository health: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/repositories/{repo_id}/check-config")
        async def check_repository_config(repo_id: int, db: Session = Depends(get_db)):
            """Check repository configuration and update effective config"""
            try:
                from services.runner_health_service import RunnerHealthService
                from models import RepositoryDB
                from datetime import datetime
                
                # Get repository
                repo = db.query(RepositoryDB).filter(RepositoryDB.id == repo_id).first()
                if not repo:
                    raise HTTPException(status_code=404, detail="Repository not found")
                
                runner_service = RunnerHealthService()
                try:
                    config_result = await runner_service.check_repository_config(db, repo)
                    
                    # Update repository with config status
                    repo.has_pr_agent_config = config_result.get("has_pr_agent_toml", False)
                    repo.has_workflow_config = config_result.get("has_workflow_config", False)
                    repo.config_last_checked = datetime.utcnow()
                    repo.effective_config = config_result.get("effective_config")
                    db.commit()
                    
                    return APIResponse(data={
                        "repository": repo.name,
                        "has_config": config_result["has_config"],
                        "config_last_checked": repo.config_last_checked,
                        "error": config_result.get("error"),
                        "effective_config": config_result.get("effective_config"),
                        "repo_config": config_result.get("repo_config")
                    }, message="Configuration check completed")
                finally:
                    await runner_service.close_session()
                    
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error checking repository config: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/repositories/{repo_id}/effective-config")
        async def get_repository_effective_config(repo_id: int, db: Session = Depends(get_db)):
            """Get the comprehensive effective configuration for a repository"""
            try:
                from services.runner_health_service import RunnerHealthService
                from models import RepositoryDB
                from datetime import datetime
                import toml
                import os
                
                # Get repository
                repo = db.query(RepositoryDB).filter(RepositoryDB.id == repo_id).first()
                if not repo:
                    raise HTTPException(status_code=404, detail="Repository not found")
                
                # Always trigger a fresh check to get the most comprehensive data
                runner_service = RunnerHealthService()
                try:
                    config_result = await runner_service.check_repository_config(db, repo)
                    
                    # Update repository with config status
                    repo.has_pr_agent_config = config_result.get("has_pr_agent_toml", False)
                    repo.has_workflow_config = config_result.get("has_workflow_config", False)
                    repo.config_last_checked = datetime.utcnow()
                    repo.effective_config = config_result.get("effective_config", {})
                    db.commit()
                    
                    # Load system default configuration
                    system_config = {}
                    try:
                        # Try to load the system configuration file
                        config_path = os.path.join(os.path.dirname(__file__), '..', '..', 'pr_agent', 'settings', 'configuration.toml')
                        if os.path.exists(config_path):
                            with open(config_path, 'r') as f:
                                system_config = toml.load(f)
                    except Exception as e:
                        logger.warning(f"Could not load system configuration: {e}")
                    
                    # Build comprehensive response (only show overridden values)
                    response_data = {
                        "repository": repo.name,
                        "has_config": config_result.get("has_config", False),
                        "has_pr_agent_config": config_result.get("has_pr_agent_toml", False),
                        "has_workflow_config": config_result.get("has_workflow_config", False),
                        "config_last_checked": repo.config_last_checked,
                        "error": config_result.get("error"),
                        
                        # Priority order: System Default -> Repository Config -> Workflow Env
                        # Only show overridden values, not system defaults
                        
                        # Repository configuration (priority 2 - overrides system defaults)
                        "repository_config": None,
                        
                        # Workflow configuration (priority 3 - highest, overrides everything)
                        "workflow_config": None,
                        
                        # Override keys for easy display
                        "override_keys": []
                    }
                    
                    # Extract workflow configuration details
                    config_details = config_result.get("config_details", {})
                    if config_details and config_details.get("workflow_config"):
                        workflow_info = config_details["workflow_config"]
                        
                        # Extract runner configuration
                        runner_config = {}
                        if workflow_info.get("found_workflows"):
                            for workflow in workflow_info["found_workflows"]:
                                analysis = workflow.get("analysis", {})
                                if analysis.get("runner_config"):
                                    runner_config = analysis["runner_config"]
                                    break
                        
                        response_data["workflow_config"] = {
                            "configuration_overrides": workflow_info.get("configuration_overrides", {}),
                            "env_variables": workflow_info.get("env_variables", {}),
                            "secrets_used": workflow_info.get("secrets_used", []),
                            "found_workflows": workflow_info.get("found_workflows", []),
                            "runner_config": runner_config
                        }
                    
                    # Extract repository configuration details
                    if config_details and config_details.get("pr_agent_toml"):
                        try:
                            repo_config = toml.loads(config_details["pr_agent_toml"])
                            response_data["repository_config"] = repo_config
                            
                            # Extract override keys (flatten the config structure to show what's being overridden)
                            def extract_keys(d, prefix=""):
                                keys = []
                                for k, v in d.items():
                                    key_path = f"{prefix}.{k}" if prefix else k
                                    if isinstance(v, dict):
                                        keys.extend(extract_keys(v, key_path))
                                    else:
                                        keys.append(key_path)
                                return keys
                            
                            response_data["override_keys"] = extract_keys(repo_config)
                        except Exception as e:
                            logger.warning(f"Failed to parse repository TOML config: {e}")
                    
                    # No final effective configuration needed - we only show overrides
                    
                    return APIResponse(data=response_data, message="Configuration overrides retrieved")
                    
                finally:
                    await runner_service.close_session()
                        
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error getting repository effective config: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        # Notification endpoints
        @self.app.get("/api/notifications/configs")
        async def get_notification_configs():
            """Get all notification configurations"""
            try:
                from database import database_manager
                configs = database_manager.get_notification_configs()
                return APIResponse(data=configs, message="Notification configurations retrieved")
            except Exception as e:
                logger.error(f"Failed to get notification configs: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/notifications/configs")
        async def create_notification_config(config_data: dict):
            """Create new notification configuration"""
            try:
                from database import database_manager
                config = database_manager.save_notification_config(config_data)
                return APIResponse(data=config, message="Notification configuration created")
            except Exception as e:
                logger.error(f"Failed to create notification config: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.put("/api/notifications/configs/{config_id}")
        async def update_notification_config(config_id: int, config_data: dict):
            """Update notification configuration"""
            try:
                config_data['id'] = config_id
                from database import database_manager
                config = database_manager.save_notification_config(config_data)
                return APIResponse(data=config, message="Notification configuration updated")
            except Exception as e:
                logger.error(f"Failed to update notification config: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.delete("/api/notifications/configs/{config_id}")
        async def delete_notification_config(config_id: int):
            """Delete notification configuration"""
            try:
                from database import database_manager
                success = database_manager.delete_notification_config(config_id)
                if success:
                    return APIResponse(data={}, message="Notification configuration deleted")
                else:
                    raise HTTPException(status_code=404, detail="Configuration not found")
            except Exception as e:
                logger.error(f"Failed to delete notification config: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/notifications/test/{config_id}")
        async def test_notification_config(config_id: int, test_data: dict = {}):
            """Test notification configuration"""
            try:
                from database import database_manager
                from services.notification_service import NotificationService
                
                logger.info(f"Testing notification config {config_id}")
                
                # Get config
                configs = database_manager.get_notification_configs()
                config = next((c for c in configs if c['id'] == config_id), None)
                if not config:
                    logger.error(f"Configuration {config_id} not found")
                    raise HTTPException(status_code=404, detail="Configuration not found")
                
                logger.info(f"Found config: {config['name']} ({config['service_type']})")
                
                # Debug: Test the notification service creation
                try:
                    notification_service = NotificationService(database_manager)
                    logger.info(f"NotificationService created successfully")
                    logger.info(f"Enabled services: {list(notification_service.enabled_services.keys())}")
                    
                    # Check if our config is in enabled services
                    if config['service_type'] in notification_service.enabled_services:
                        logger.info(f"Config {config['service_type']} found in enabled services")
                    else:
                        logger.warning(f"Config {config['service_type']} NOT found in enabled services")
                        logger.info(f"Available services: {notification_service.enabled_services}")
                        
                except Exception as e:
                    logger.error(f"Failed to create NotificationService: {e}")
                    import traceback
                    logger.error(f"Traceback: {traceback.format_exc()}")
                    raise
                
                # Create test notification
                test_event = test_data if test_data else {
                    'title': 'Test Notification',
                    'message': 'This is a test notification from PR Agent Dashboard',
                    'job_id': 'test-job-123',
                    'repository': 'test/repository',
                    'status': 'success'
                }
                
                logger.info(f"Sending test notification with event: {test_event}")
                
                # Send test notification using the config's test method
                try:
                    # The test_notification_config method is now async
                    success = await notification_service.test_notification_config(config)
                    logger.info(f"Test notification result: {success}")
                except Exception as e:
                    logger.error(f"Failed to send test notification: {e}")
                    import traceback
                    logger.error(f"Test notification traceback: {traceback.format_exc()}")
                    raise
                
                # Update test status
                status = 'success' if success else 'failed'
                database_manager.update_notification_test_status(config_id, status)
                
                if success:
                    return APIResponse(data={}, message="Test notification sent successfully")
                else:
                    raise HTTPException(status_code=500, detail="Failed to send test notification")
                    
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Failed to test notification config: {e}")
                import traceback
                logger.error(f"Full traceback: {traceback.format_exc()}")
                # Update test status as failed
                try:
                    from database import database_manager
                    database_manager.update_notification_test_status(config_id, 'failed')
                except:
                    pass
                raise HTTPException(status_code=500, detail=f"Internal error: {str(e)}")
        
        @self.app.get("/api/notifications/events")
        async def get_notification_events(
            limit: int = 100, 
            offset: int = 0,
            event_type: str = None,
            repository: str = None
        ):
            """Get notification events with pagination"""
            try:
                from database import database_manager
                events = database_manager.get_notification_events(
                    limit=limit, 
                    offset=offset,
                    event_type=event_type,
                    repository=repository
                )
                
                # Get total count for pagination
                total_count = database_manager.get_notification_events_count(
                    event_type=event_type,
                    repository=repository
                )
                
                return APIResponse(
                    data=events, 
                    total=total_count,
                    page=offset // limit + 1,
                    per_page=limit,
                    message="Notification events retrieved"
                )
            except Exception as e:
                logger.error(f"Failed to get notification events: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        # Metrics endpoints
        @self.app.get("/api/metrics/summary")
        async def get_metrics_summary(db: Session = Depends(get_db)):
            """Get complete metrics summary with cost calculations"""
            try:
                summary = await self.metrics_service.get_metrics_summary(db)
                return APIResponse(data=summary, message="Metrics summary retrieved")
            except Exception as e:
                logger.error(f"Error getting metrics summary: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/metrics/config")
        async def get_metrics_config(db: Session = Depends(get_db)):
            """Get metrics configuration"""
            try:
                config = await self.metrics_service.get_or_create_config(db)
                return APIResponse(data=config, message="Metrics configuration retrieved")
            except Exception as e:
                logger.error(f"Error getting metrics config: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/metrics/config")
        async def update_metrics_config(config_data: dict, db: Session = Depends(get_db)):
            """Update metrics configuration"""
            try:
                config = await self.metrics_service.update_config(db, config_data)
                return APIResponse(data=config, message="Metrics configuration updated")
            except Exception as e:
                logger.error(f"Error updating metrics config: {e}")
                raise HTTPException(status_code=400, detail=str(e))
        
        @self.app.post("/api/metrics/recalculate")
        async def recalculate_metrics(db: Session = Depends(get_db)):
            """Recalculate metrics from existing operations"""
            try:
                await self.metrics_service.recalculate_metrics_from_operations(db)
                summary = await self.metrics_service.get_metrics_summary(db)
                return APIResponse(data=summary, message="Metrics recalculated successfully")
            except Exception as e:
                logger.error(f"Error recalculating metrics: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/metrics/operations")
        async def get_operation_breakdown(db: Session = Depends(get_db)):
            """Get operation breakdown with cost calculations"""
            try:
                breakdown = await self.metrics_service.get_operation_breakdown(db)
                return APIResponse(data=breakdown, message="Operation breakdown retrieved")
            except Exception as e:
                logger.error(f"Error getting operation breakdown: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/metrics/repositories")
        async def get_repository_breakdown(db: Session = Depends(get_db)):
            """Get repository breakdown with cost calculations"""
            try:
                breakdown = await self.metrics_service.get_repository_breakdown(db)
                return APIResponse(data=breakdown, message="Repository breakdown retrieved")
            except Exception as e:
                logger.error(f"Error getting repository breakdown: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        # Admin endpoints
        @self.app.get("/api/admin/retention/config")
        async def get_retention_config():
            """Get retention configuration"""
            try:
                config = self.retention_service.get_retention_config()
                return APIResponse(data=config, message="Retention configuration retrieved")
            except Exception as e:
                logger.error(f"Failed to get retention config: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/admin/retention/config")
        async def update_retention_config(config_data: dict):
            """Update retention configuration"""
            try:
                success = self.retention_service.update_retention_config(config_data)
                if success:
                    return APIResponse(data={}, message="Retention configuration updated")
                else:
                    raise HTTPException(status_code=400, detail="Failed to update retention configuration")
            except Exception as e:
                logger.error(f"Failed to update retention config: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/admin/database/stats")
        async def get_database_stats():
            """Get database statistics"""
            try:
                stats = self.retention_service.get_database_stats()
                return APIResponse(data=stats, message="Database statistics retrieved")
            except Exception as e:
                logger.error(f"Failed to get database stats: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/admin/database/cleanup")
        async def perform_cleanup(dry_run: bool = True):
            """Perform database cleanup"""
            try:
                results = self.retention_service.perform_cleanup(dry_run=dry_run)
                action = "simulated" if dry_run else "performed"
                return APIResponse(data=results, message=f"Database cleanup {action}")
            except Exception as e:
                logger.error(f"Failed to perform cleanup: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/admin/database/backup")
        async def create_backup(compressed: bool = True):
            """Create database backup"""
            try:
                result = self.retention_service.create_backup(include_compression=compressed)
                if result["success"]:
                    return APIResponse(data=result, message="Database backup created")
                else:
                    raise HTTPException(status_code=500, detail=result["error"])
            except Exception as e:
                logger.error(f"Failed to create backup: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/admin/database/backups")
        async def get_backup_list():
            """Get list of available backups"""
            try:
                backups = self.retention_service.get_backup_list()
                return APIResponse(data=backups, message="Backup list retrieved")
            except Exception as e:
                logger.error(f"Failed to get backup list: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/admin/backup/directory")
        async def get_backup_directory():
            """Get current backup directory"""
            try:
                backup_dir = self.retention_service.backup_dir
                return APIResponse(data={"backup_directory": str(backup_dir)}, message="Backup directory retrieved")
            except Exception as e:
                logger.error(f"Failed to get backup directory: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/admin/backup/directory")
        async def set_backup_directory(directory_data: dict):
            """Set backup directory"""
            try:
                new_directory = directory_data.get("backup_directory")
                if not new_directory:
                    raise HTTPException(status_code=400, detail="backup_directory is required")
                
                # Save to database
                success = self.database_manager.set_system_setting("backup_directory", new_directory)
                if success:
                    # Update the retention service
                    self.retention_service.backup_dir = Path(new_directory)
                    self.retention_service.backup_dir.mkdir(exist_ok=True)
                    return APIResponse(data={}, message="Backup directory updated")
                else:
                    raise HTTPException(status_code=500, detail="Failed to save backup directory")
            except Exception as e:
                logger.error(f"Failed to set backup directory: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.post("/api/admin/database/export")
        async def export_data(request_data: dict):
            """Export database data for download"""
            try:
                format_type = request_data.get("format", "json")
                tables = request_data.get("tables")
                result = self.retention_service.export_data(format=format_type, table_filter=tables)
                if result["success"]:
                    # Return the content for download
                    from fastapi.responses import Response
                    return Response(
                        content=result["content"], 
                        media_type=result["content_type"],
                        headers={
                            "Content-Disposition": f"attachment; filename={result['filename']}",
                            "Content-Length": str(result["size_bytes"])
                        }
                    )
                else:
                    raise HTTPException(status_code=500, detail=result["error"])
            except Exception as e:
                logger.error(f"Failed to export data: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.delete("/api/admin/database/backups/{filename}")
        async def delete_backup(filename: str):
            """Delete a specific backup file"""
            try:
                result = self.retention_service.delete_backup(filename)
                if result["success"]:
                    return APIResponse(data=result, message=result["message"])
                else:
                    raise HTTPException(status_code=400, detail=result["error"])
            except Exception as e:
                logger.error(f"Failed to delete backup: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.delete("/api/admin/database/backups")
        async def delete_all_backups():
            """Delete all backup files"""
            try:
                result = self.retention_service.delete_all_backups()
                if result["success"]:
                    return APIResponse(data=result, message=result["message"])
                else:
                    raise HTTPException(status_code=400, detail=result["error"])
            except Exception as e:
                logger.error(f"Failed to delete all backups: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/api/admin/database/backups/{filename}/restore")
        async def restore_backup(filename: str):
            """Restore database from a backup file"""
            try:
                result = self.retention_service.restore_backup(filename)
                if result["success"]:
                    return APIResponse(data=result, message=result["message"])
                else:
                    raise HTTPException(status_code=400, detail=result["error"])
            except Exception as e:
                logger.error(f"Failed to restore backup: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/repositories/{repo_id}/detailed-status")
        async def get_repository_detailed_status(repo_id: int, db: Session = Depends(get_db)):
            """Get detailed repository status including runner info and workflow analysis"""
            try:
                repo = db.query(RepositoryDB).filter(RepositoryDB.id == repo_id).first()
                if not repo:
                    raise HTTPException(status_code=404, detail="Repository not found")
                
                from services.runner_health_service import RunnerHealthService
                
                runner_service = RunnerHealthService()
                try:
                    # Get detailed runner health including runner info
                    runner_health = await runner_service.check_repository_runner_health(db, repo)
                    
                    # Get detailed configuration analysis
                    config_analysis = await runner_service.check_repository_config(db, repo)
                    
                    detailed_status = {
                        "repository": {
                            "id": repo.id,
                            "name": repo.name,
                            "provider": repo.provider,
                            "url": repo.url
                        },
                        "runner_health": runner_health,
                        "config_analysis": config_analysis,
                        "last_updated": datetime.utcnow().isoformat()
                    }
                    
                    return APIResponse(data=detailed_status, message="Detailed repository status retrieved")
                finally:
                    await runner_service.close_session()
                    
            except Exception as e:
                logger.error(f"Error getting detailed status for repository {repo_id}: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/repositories/permissions-guide")
        async def get_permissions_guide():
            """Get guidance on required GitHub token permissions for fine-grained tokens"""
            return APIResponse(data={
                "fine_grained_permissions": {
                    "required": [
                        {
                            "permission": "Metadata",
                            "access": "Read",
                            "description": "Required for basic repository access and information"
                        },
                        {
                            "permission": "Actions", 
                            "access": "Read",
                            "description": "Required to check self-hosted runners status"
                        }
                    ],
                    "optional": [
                        {
                            "permission": "Contents",
                            "access": "Read", 
                            "description": "Required to read .pr_agent.toml and workflow files for configuration analysis"
                        },
                        {
                            "permission": "Pull requests",
                            "access": "Write",
                            "description": "Required if using PR-Agent for pull request automation"
                        }
                    ]
                },
                "classic_permissions": [
                    "repo (Full control of private repositories)",
                    "read:org (Read org and team membership, read org projects)"
                ]
            }, message="GitHub token permissions guide")

        # Developer endpoints (Open/Closed Principle - easily extensible)
        if settings.developer_mode:
            self._setup_developer_routes()
        
        # WebSocket endpoint
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            client_info = f"{websocket.client.host}:{websocket.client.port}" if websocket.client else "unknown"
            logger.info(f"WebSocket connection attempt from {client_info}")
            logger.debug(f"WebSocket headers: {dict(websocket.headers)}")
            
            try:
                await self.websocket_manager.connect(websocket)
                logger.info(f"WebSocket connected successfully: {client_info}")
                
                # Keep connection alive
                while True:
                    await asyncio.sleep(30)
                    # Check if connection is still active before sending ping
                    if websocket.client_state.value == 1:  # CONNECTED state
                        try:
                            await websocket.send_json({
                                "type": "ping", 
                                "timestamp": datetime.now().isoformat()
                            })
                        except Exception as ping_error:
                            logger.debug(f"Failed to send ping, connection likely closed: {ping_error}")
                            break
                    else:
                        logger.debug("WebSocket connection not in connected state, ending ping loop")
                        break
            except WebSocketDisconnect as e:
                logger.info(f"WebSocket disconnected normally: {client_info} (code: {e.code})")
            except Exception as e:
                logger.error(f"WebSocket error for {client_info}: {e}", exc_info=True)
            finally:
                self.websocket_manager.disconnect(websocket)
                logger.info(f"WebSocket cleanup completed for {client_info}")
    
    def _setup_developer_routes(self):
        """Setup developer-only routes (Interface Segregation Principle)"""
        
        @self.app.post("/api/dev/generate-test-data")
        async def generate_test_data(db: Session = Depends(get_db)):
            from test_data import generate_test_data
            result = await generate_test_data()
            
            if result["status"] == "success":
                # Recalculate metrics from the new test data
                try:
                    await self.metrics_service.recalculate_metrics_from_operations(db)
                    return APIResponse(data=result["data"], message=result["message"] + " (with metrics)")
                except Exception as e:
                    logger.warning(f"Failed to recalculate metrics after test data generation: {e}")
                    return APIResponse(data=result["data"], message=result["message"] + " (metrics calculation failed)")
            else:
                raise HTTPException(status_code=500, detail=result["message"])
        
        @self.app.post("/api/dev/simulate-activity")
        async def simulate_activity():
            from test_data import simulate_live_activity
            result = await simulate_live_activity()
            
            if result["status"] == "success":
                return APIResponse(data={"operation_id": result.get("operation_id")}, message=result["message"])
            else:
                raise HTTPException(status_code=500, detail=result["message"])
        
        @self.app.post("/api/dev/fail-activity")
        async def fail_activity(request_data: dict):
            from test_data import fail_live_activity
            operation_id = request_data.get("operation_id")
            if not operation_id:
                raise HTTPException(status_code=400, detail="operation_id is required")
            
            result = await fail_live_activity(operation_id)
            
            if result["status"] == "success":
                return APIResponse(data={"operation_id": operation_id}, message=result["message"])
            else:
                raise HTTPException(status_code=500, detail=result["message"])
        
        @self.app.post("/api/dev/succeed-activity")
        async def succeed_activity(request_data: dict):
            from test_data import succeed_live_activity
            operation_id = request_data.get("operation_id")
            if not operation_id:
                raise HTTPException(status_code=400, detail="operation_id is required")
            
            result = await succeed_live_activity(operation_id)
            
            if result["status"] == "success":
                return APIResponse(data={"operation_id": operation_id}, message=result["message"])
            else:
                raise HTTPException(status_code=500, detail=result["message"])
        
        @self.app.post("/api/dev/trigger-error")
        async def trigger_error():
            from test_data import trigger_test_error
            result = await trigger_test_error()
            
            if result["status"] == "success":
                return APIResponse(data={"operation_id": result.get("operation_id")}, message=result["message"])
            else:
                raise HTTPException(status_code=500, detail=result["message"])
        
        @self.app.post("/api/dev/clear-data")
        async def clear_data():
            # Clear cache data first
            await self.cached_job_service.clear_all_data()
            
            # Also clear from the test_data module for compatibility
            from test_data import clear_all_data
            result = await clear_all_data()
            
            if result["status"] == "success":
                return APIResponse(data={}, message=result["message"] + " (cache and database cleared)")
            else:
                raise HTTPException(status_code=500, detail=result["message"])
        
        @self.app.post("/api/dev/refresh-job-counts")
        async def refresh_job_counts():
            """Refresh job operation counts"""
            result = await self.job_service.refresh_job_counts()
            return APIResponse(data=result, message="Job counts refreshed")
        
        @self.app.post("/api/dev/test-system-logs")
        async def test_system_logs():
            """Test system logging functionality for debugging"""
            try:
                # Test retention system logging
                self.retention_service._log_to_system('INFO', 
                    "Test retention system log - Manual test trigger",
                    {'system_event': 'test_retention_log', 'test': True}
                )
                
                # Test health system logging  
                self.health_service._log_to_system('INFO',
                    "Test health system log - Manual test trigger", 
                    {'system_event': 'test_health_log', 'test': True}
                )
                
                # Test backend system logging
                self._log_system_event('INFO',
                    "Test backend system log - Manual test trigger",
                    {'system_event': 'test_backend_log', 'test': True}
                )
                
                return APIResponse(data={"success": True}, message="System log tests triggered")
            except Exception as e:
                logger.error(f"Failed to trigger system log tests: {e}")
                return APIResponse(data={"success": False, "error": str(e)}, message="System log tests failed")
        
        @self.app.post("/api/dev/generate-ai-metrics")
        async def generate_ai_metrics():
            """Generate sample AI metrics data for testing"""
            try:
                from test_data import generate_ai_metrics_data
                result = await generate_ai_metrics_data()
                
                # Trigger metrics recalculation after generating data
                if result.get("status") == "success":
                    try:
                        await self.metrics_service.recalculate_metrics_from_operations(SessionLocal())
                    except Exception as e:
                        logger.warning(f"Failed to recalculate metrics after generating data: {e}")
                
                return APIResponse(data=result, message=result.get("message", "AI metrics generation completed"))
            except Exception as e:
                logger.error(f"Failed to generate AI metrics data: {e}")
                return APIResponse(data={"status": "error", "error": str(e)}, message="AI metrics generation failed")
    
    def _setup_background_tasks_lifespan(self):
        """Setup background monitoring tasks using modern lifespan events"""
        from contextlib import asynccontextmanager
        
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # Startup
            
            # Initialize robust cache service first
            try:
                await initialize_robust_cache_service()
                logger.info("Robust cache service initialized successfully")
            except Exception as e:
                logger.error(f"Robust cache service initialization failed: {e}")
                raise
            
            try:
                startup_config = await self._get_startup_config_summary()
                
                self._log_system_event('INFO', 
                    f"Dashboard backend starting - Version {settings.app_name} (Developer mode: {'enabled' if settings.developer_mode else 'disabled'})",
                    {
                        'system_event': 'backend_startup',
                        'config': startup_config,
                        'developer_mode': settings.developer_mode,
                        'api_host': settings.api_host,
                        'api_port': settings.api_port
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to log startup event: {e}")
            
            logger.info(f"{settings.app_name} started")
            if settings.developer_mode:
                logger.info("Developer mode enabled")
                
            # Initialize database with schema updates
            try:
                from database import initialize_database
                initialize_database()
                logger.info("Database initialized successfully")
                
                try:
                    self._log_system_event('INFO', 
                        "Database system initialized - Schema validation completed",
                        {
                            'system_event': 'database_initialized',
                            'database_type': 'SQLite',
                            'schema_version': 'latest'
                        }
                    )
                except Exception as e:
                    logger.warning(f"Failed to log database init event: {e}")
            except Exception as e:
                logger.error(f"Database initialization failed: {e}")
                try:
                    self._log_system_event('ERROR', 
                        f"Database initialization failed: {e}",
                        {
                            'system_event': 'database_init_failed',
                            'error': str(e)
                        }
                    )
                except Exception:
                    pass  # Don't let logging errors cascade
                # Continue anyway, the fallback in models.py should handle it
            
            # Start background monitoring tasks
            cleanup_task = asyncio.create_task(self._cleanup_old_data())
            backup_task = asyncio.create_task(self._backup_scheduler())
            health_task = asyncio.create_task(self._monitor_system_health())
            
            # Start health service background monitoring
            try:
                await self.health_service.start_background_monitoring()
            except Exception as e:
                logger.error(f"Failed to start health monitoring: {e}")
            
            # Create a task to log system startup after server is fully ready
            startup_logging_task = asyncio.create_task(self._log_system_startup_after_delay())
            
            yield
            
            # Cancel startup logging task during shutdown
            startup_logging_task.cancel()
            
            # Shutdown
            try:
                self._log_system_event('INFO', 
                    f"Dashboard backend shutting down - Stopping background services",
                    {
                        'system_event': 'backend_shutdown',
                        'uptime_seconds': getattr(self, '_startup_time', None) and (asyncio.get_event_loop().time() - self._startup_time) or None
                    }
                )
            except Exception as e:
                logger.warning(f"Failed to log shutdown event: {e}")
            
            # Shutdown robust cache service
            try:
                await shutdown_robust_cache_service()
                logger.info("Robust cache service shutdown successfully")
            except Exception as e:
                logger.error(f"Failed to shutdown robust cache service: {e}")
            
            logger.info(f"{settings.app_name} stopped")
            cleanup_task.cancel()
            backup_task.cancel()
            health_task.cancel()
            try:
                await self.health_service.stop_background_monitoring()
            except Exception as e:
                logger.error(f"Failed to stop health monitoring: {e}")
        
        # Store lifespan handler for FastAPI constructor
        self.lifespan_handler = lifespan
        try:
            self._startup_time = asyncio.get_event_loop().time()
        except RuntimeError:
            # No event loop running yet
            self._startup_time = None
        except Exception:
            self._startup_time = None
    
    async def _get_startup_config_summary(self) -> Dict[str, Any]:
        """Get configuration summary for startup logging"""
        try:
            # Now we can properly await the async config call
            config = await self.config_service.get_config() if self.config_service else {}
            retention_config = self.retention_service.get_retention_config() if self.retention_service else {}
            
            return {
                'api': {
                    'host': settings.api_host,
                    'port': settings.api_port,
                    'debug': settings.debug
                },
                'database': {
                    'type': 'SQLite',
                    'max_logs_storage': settings.max_logs_storage,
                    'max_operations_storage': settings.max_operations_storage
                },
                'backup': {
                    'enabled': retention_config.get('auto_backup_enabled', False),
                    'interval_hours': retention_config.get('backup_schedule_hours', 168),
                    'compression': retention_config.get('backup_compression', True)
                },
                'health_monitoring': {
                    'enabled': True,
                    'interval': '5 minutes'
                },
                'pr_agent': {
                    'configured': bool(config.get('pr_agent_url')),
                    'url': config.get('pr_agent_url', 'not_configured')
                },
                'context_service': {
                    'enabled': bool(config.get('context_service', {}).get('enabled')),
                    'url': config.get('context_service', {}).get('url', 'not_configured')
                }
            }
        except Exception as e:
            return {
                'error': f"Failed to get config summary: {e}",
                'basic_config': {
                    'api_host': settings.api_host,
                    'api_port': settings.api_port
                }
            }
    
    def _log_system_event(self, level: str, message: str, context: dict = None):
        """Log system events to the dashboard logging system"""
        try:
            import requests
            from datetime import datetime
            
            # Create a system log entry
            log_data = {
                'timestamp': datetime.utcnow().isoformat(),
                'level': level,
                'message': f"[SYSTEM] {message}",
                'source': 'dashboard_backend',
                'job_id': None,
                'operation_id': None,
                'repository': None,
                'status': None
            }
            
            # Add context to log data
            if context:
                log_data.update(context)
            
            # Send directly to dashboard backend (self-logging)
            try:
                requests.post('http://localhost:8000/logs/immediate', json=log_data, timeout=1)
            except Exception:
                # If dashboard is not available yet, just use standard logging
                try:
                    getattr(logger, level.lower(), logger.info)(message)
                except Exception:
                    pass  # Don't cascade logging errors
                
        except Exception:
            # Completely ignore logging errors to prevent startup issues
            pass
    
    async def _cleanup_old_data(self):
        """Background task to cleanup old data using RetentionService"""
        from services.retention_service import RetentionService
        
        # Initialize retention service
        retention_service = RetentionService(self.database_manager)
        
        while True:
            try:
                # Get retention configuration
                config = retention_service.get_retention_config()
                
                # Check if auto cleanup is enabled
                if not config.get("auto_cleanup_enabled", True):
                    await asyncio.sleep(3600)  # Check again in 1 hour
                    continue
                
                # Calculate sleep time based on schedule
                schedule_hours = config.get("cleanup_schedule_hours", 24)
                sleep_seconds = schedule_hours * 3600
                
                # Check if it's time for cleanup
                stats = retention_service.get_database_stats()
                last_cleanup = stats.get("last_cleanup")
                
                should_cleanup = True
                if last_cleanup:
                    try:
                        last_cleanup_dt = datetime.fromisoformat(last_cleanup.replace('Z', '+00:00'))
                        next_cleanup_dt = last_cleanup_dt + timedelta(hours=schedule_hours)
                        should_cleanup = datetime.utcnow() >= next_cleanup_dt.replace(tzinfo=None)
                    except Exception as e:
                        logger.warning(f"Could not parse last cleanup time: {e}")
                
                if should_cleanup:
                    logger.info("Starting scheduled database cleanup...")
                    result = retention_service.perform_cleanup(dry_run=False)
                    
                    if result["errors"]:
                        logger.error(f"Cleanup completed with errors: {result['errors']}")
                    else:
                        logger.info(f"Cleanup completed successfully. Deleted {result['total_deleted']} records, reclaimed {result['space_reclaimed_mb']} MB")
                
                # Sleep until next check
                await asyncio.sleep(min(sleep_seconds, 3600))  # Check at least every hour
                    
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
                await asyncio.sleep(3600)  # Wait 1 hour before retrying
    
    async def _backup_scheduler(self):
        """Background task to perform automatic backups"""
        while True:
            try:
                await asyncio.sleep(3600)  # Check every hour
                
                # Log backup scheduler check
                self._log_system_event('DEBUG', 
                    "Backup scheduler checking for due automatic backups",
                    {'system_event': 'backup_scheduler_check'}
                )
                
                # Perform backup if due
                result = self.retention_service.perform_automatic_backup()
                
                if result.get("success"):
                    # Successful backup was logged by retention service
                    pass
                elif result.get("reason") == "Auto backup disabled":
                    # Only log this once per startup, not every hour
                    if not hasattr(self, '_backup_disabled_logged'):
                        self._log_system_event('INFO', 
                            "Automatic backups disabled - Manual backups only",
                            {
                                'system_event': 'backup_scheduler_disabled',
                                'reason': 'auto_backup_disabled'
                            }
                        )
                        self._backup_disabled_logged = True
                elif "not due" in result.get("reason", ""):
                    # Don't log "not due" messages as they're too frequent
                    pass
                else:
                    # Log other reasons (like errors)
                    self._log_system_event('WARNING', 
                        f"Automatic backup check result: {result.get('reason', 'Unknown reason')}",
                        {
                            'system_event': 'backup_scheduler_result',
                            'result': result
                        }
                    )
                    
            except Exception as e:
                logger.error(f"Error in backup scheduler: {e}")
                self._log_system_event('ERROR', 
                    f"Backup scheduler error: {e}",
                    {
                        'system_event': 'backup_scheduler_error',
                        'error': str(e)
                    }
                )
    
    async def _monitor_system_health(self):
        """Background task to monitor system health"""
        while True:
            try:
                await asyncio.sleep(300)  # Check every 5 minutes
                
                # Get health status
                health = await self.health_service.get_system_health()
                
                # Log any issues
                if health["status"] != "healthy":
                    logger.warning(f"System health degraded: {health['status']}")
                    
                    for service_name, service_health in health["services"].items():
                        if service_health["status"] not in ["healthy", "disabled", "configured"]:
                            logger.warning(f"Service {service_name} status: {service_health['status']}")
                
            except Exception as e:
                logger.error(f"Error in health monitoring: {e}")
    
    async def _log_system_startup_after_delay(self):
        """Log system startup events after server is fully ready to handle requests"""
        try:
            # Wait a short time for server to be fully ready
            await asyncio.sleep(2)
            
            # Log retention service startup
            try:
                self.retention_service._log_system_startup()
                logger.info("Logged retention service startup")
            except Exception as e:
                logger.warning(f"Failed to log retention service startup: {e}")
            
            # Log health service startup
            try:
                self.health_service._log_health_service_startup()
                logger.info("Logged health service startup")
            except Exception as e:
                logger.warning(f"Failed to log health service startup: {e}")
            
            # Log background services startup
            try:
                self._log_system_event('INFO', 
                    "Background services started - Cleanup, backup, and health monitoring active",
                    {
                        'system_event': 'background_services_started',
                        'services': ['cleanup_scheduler', 'backup_scheduler', 'health_monitor']
                    }
                )
                logger.info("Logged background services startup")
            except Exception as e:
                logger.warning(f"Failed to log background services start: {e}")
                
        except asyncio.CancelledError:
            logger.info("System startup logging task cancelled")
        except Exception as e:
            logger.error(f"Error in system startup logging: {e}")
    
    def get_app(self):
        """Get the FastAPI application instance"""
        return self.app


# Create application instance
dashboard_app = DashboardApplication()
app = dashboard_app.get_app()

# For uvicorn
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.debug,
        log_level=settings.log_level.lower()
    ) 