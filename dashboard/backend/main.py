from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Depends, status, Request
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
from services.robust_cached_job_service import get_robust_cached_job_service
from services.auth_service import AuthService
from services.github_action_config_service import GitHubActionConfigService
from services.system_settings_service import SystemSettingsService
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
            # Use RobustCachedJobService with notification support
            self.cached_job_service = get_robust_cached_job_service(self.notification_service)
            self.retention_service = RetentionService(self.database_manager)
            self.auth_service = AuthService()
            self.github_action_config_service = GitHubActionConfigService()
            
            # Initialize Azure Pipeline config service
            from services.azure_pipeline_config_service import AzurePipelineConfigService
            self.azure_pipeline_config_service = AzurePipelineConfigService()
            
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
    
    def check_maintenance_mode_dependency(self):
        """Create a dependency that checks for maintenance mode"""
        
        async def check_maintenance_mode(request: Request = None):
            # Always allow health check endpoints even during maintenance
            if request:
                path = request.url.path
                if path.startswith("/api/health") or path in ["/api/status"]:
                    return
            
            try:
                maintenance_mode = self.database_manager.get_system_setting("maintenance_mode")
                if maintenance_mode and maintenance_mode.lower() == "true":
                    maintenance_reason = self.database_manager.get_system_setting("maintenance_reason") or "System maintenance in progress"
                    raise HTTPException(
                        status_code=503,
                        detail=f"Service temporarily unavailable: {maintenance_reason}"
                    )
            except HTTPException:
                raise  # Re-raise HTTP exceptions
            except Exception as e:
                # If we can't check maintenance mode (e.g., during database replacement), assume maintenance
                logger.warning(f"Failed to check maintenance mode: {e}")
                raise HTTPException(
                    status_code=503,
                    detail="Service temporarily unavailable: Database maintenance in progress"
                )
        
        return check_maintenance_mode
    
    def _setup_routes(self):
        """Setup all API routes using service methods"""
        
        # Create dependency functions
        get_current_user = self.get_current_user_dependency()
        require_auth = self.require_auth_dependency()
        check_maintenance_mode = self.check_maintenance_mode_dependency()
        
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
            current_user: UserDB = Depends(require_auth),
            request: Request = None,
            _: None = Depends(check_maintenance_mode)
        ):
            operations = await self.cached_job_service.get_operations(
                limit=limit,
                status=status,
                repo=repo
            )
            return APIResponse(data={"operations": operations}, total=len(operations))
        
        @self.app.get("/api/operations/{operation_id}")
        async def get_operation(operation_id: str, db: Session = Depends(get_db)):
            operation = await self.cached_job_service.get_operation(operation_id)
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
            ensure_counts: bool = True,
            request: Request = None,
            _: None = Depends(check_maintenance_mode)
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
                    
                    # CRITICAL FIX: Database session isolation issue
                    # The force_sync_operation_to_db() uses a different session than our 'db' parameter
                    # We need to ensure our session sees the committed changes
                    try:
                        # Force refresh the database session to see committed changes from other sessions
                        db.expire_all()  # Clear session cache
                        db.commit()      # Ensure any pending changes are committed
                        
                        # Now recalculate metrics with fresh data
                        await self.metrics_service.recalculate_metrics_from_operations(db)
                        logger.info(f"Metrics recalculated immediately after operation {operation_id} AI metrics update")
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
        
        @self.app.post("/api/operations/{operation_id}/multi-model-ai-metrics")
        async def update_operation_multi_model_ai_metrics(operation_id: str, metrics_data: dict, db: Session = Depends(get_db)):
            """Update operation multi-model AI metrics from PR-Agent"""
            
            try:
                success = await self.cached_job_service.update_operation_multi_model_ai_metrics(
                    operation_id=operation_id,
                    models_data=metrics_data.get('models_data', {}),
                    estimated_dev_hours_saved=metrics_data.get('estimated_dev_hours_saved')
                )
                
                if success:
                    # Force sync to database before recalculating metrics
                    await self.cached_job_service.force_sync_operation_to_db(operation_id)
                    
                    # Trigger metrics recalculation with fresh session
                    db.expire_all()  # Clear session cache to see latest data
                    await self.metrics_service.recalculate_metrics_from_operations(db)
                    
                    return {"status": "success", "message": "Multi-model AI metrics updated"}
                else:
                    return {"status": "error", "message": "Failed to update multi-model AI metrics"}
                    
            except Exception as e:
                logger.error(f"Error updating multi-model AI metrics for operation {operation_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to update multi-model AI metrics: {str(e)}")

        @self.app.post("/api/operations/{operation_id}/step")
        async def update_operation_step(operation_id: str, step_data: dict, db: Session = Depends(get_db)):
            """Update operation current step from PR-Agent"""
            
            try:
                current_step = step_data.get('current_step')
                if not current_step:
                    raise HTTPException(status_code=400, detail="current_step is required")
                
                success = await self.cached_job_service.update_operation_step(
                    operation_id=operation_id,
                    current_step=current_step
                )
                
                if success:
                    # Broadcast step update to WebSocket clients
                    await self.websocket_manager.broadcast({
                        "type": "operation_step_update",
                        "data": {
                            "operation_id": operation_id,
                            "current_step": current_step
                        }
                    })
                    
                    return {"status": "success", "message": "Operation step updated"}
                else:
                    return {"status": "error", "message": "Failed to update operation step"}
                    
            except Exception as e:
                logger.error(f"Error updating operation step for {operation_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to update operation step: {str(e)}")

        @self.app.put("/api/operations/{operation_id}/insights")
        async def update_operation_insights(operation_id: str, insights_data: dict, db: Session = Depends(get_db)):
            """Update operation insights from PR-Agent AI analysis"""
            
            try:
                success = await self.cached_job_service.update_operation_insights(
                    operation_id=operation_id,
                    insights=insights_data.get('insights', {})
                )
                
                if success:
                    logger.info(f"Operation {operation_id} insights updated successfully")
                    return {"status": "success", "message": "Operation insights updated"}
                else:
                    logger.warning(f"Operation {operation_id} not found in cache")
                    raise HTTPException(status_code=404, detail="Operation not found")
                    
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error updating operation insights for {operation_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to update operation insights: {str(e)}")

        @self.app.get("/api/operations/{operation_id}/insights")
        async def get_operation_insights(operation_id: str, db: Session = Depends(get_db)):
            """Get operation insights"""
            
            try:
                # Try to get from cache first
                operation = await self.cached_job_service.get_operation(operation_id)
                
                if operation and operation.get('insights'):
                    return APIResponse(
                        data={"insights": operation['insights']}, 
                        message="Operation insights retrieved successfully"
                    )
                
                # Fallback to database
                from models import OperationDB
                db_operation = db.query(OperationDB).filter(OperationDB.operation_id == operation_id).first()
                
                if not db_operation:
                    raise HTTPException(status_code=404, detail="Operation not found")
                
                insights = db_operation.insights if db_operation.insights else {}
                return APIResponse(
                    data={"insights": insights}, 
                    message="Operation insights retrieved successfully"
                )
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error retrieving operation insights for {operation_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to retrieve operation insights: {str(e)}")
        
        # Logs endpoints
        @self.app.get("/api/logs")
        async def get_logs(
            limit: int = 50000,  # Increased limit to show all logs, no artificial restriction
            level: Optional[str] = None,
            search: Optional[str] = None,
            repo: Optional[str] = None,
            job_id: Optional[str] = None,
            operation_id: Optional[str] = None,
            db: Session = Depends(get_db),
            request: Request = None,
            _: None = Depends(check_maintenance_mode)
        ):
            logs = await self.cached_job_service.get_logs(
                limit=limit,
                level=level,
                job_id=job_id,
                operation_id=operation_id,
                repository=repo
            )
            return APIResponse(data={"logs": logs}, message=f"Retrieved {len(logs)} logs")
        
        @self.app.get("/api/logs/job/{job_id}")
        async def get_logs_by_job(job_id: str, db: Session = Depends(get_db)):
            logs = await self.cached_job_service.get_logs(job_id=job_id, limit=10000)
            return APIResponse(data={"logs": logs}, message=f"Retrieved {len(logs)} logs for job {job_id}")
        
        @self.app.get("/api/logs/operation/{operation_id}")
        async def get_logs_by_operation(operation_id: str, db: Session = Depends(get_db)):
            logs = await self.cached_job_service.get_logs(operation_id=operation_id, limit=10000)
            return APIResponse(data={"logs": logs}, message=f"Retrieved {len(logs)} logs for operation {operation_id}")
        
        # Log ingestion endpoints
        @self.app.post("/logs/immediate")
        async def receive_immediate_log(log_data: dict, db: Session = Depends(get_db)):
            try:
                # Use robust cached job service for logs too
                log_id = await self.cached_job_service.create_log_entry(
                    level=log_data.get('level', 'INFO'),
                    message=log_data.get('message', ''),
                    source=log_data.get('source') or log_data.get('module', 'unknown'),
                    job_id=log_data.get('job_id'),
                    operation_id=log_data.get('operation_id'),
                    repository=log_data.get('repository') or log_data.get('repo'),
                    status=log_data.get('status'),
                    module=log_data.get('module'),
                    function=log_data.get('function'),
                    severity="high" if log_data.get('level') in ["ERROR", "CRITICAL"] else "normal",
                    artifacts=log_data.get('artifacts')  # Add artifacts support
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
                    log_id = await self.cached_job_service.create_log_entry(
                        level=log_data.get('level', 'INFO'),
                        message=log_data.get('message', ''),
                        source=log_data.get('source') or log_data.get('module', 'unknown'),
                        job_id=log_data.get('job_id'),
                        operation_id=log_data.get('operation_id'),
                        repository=log_data.get('repository') or log_data.get('repo'),
                        status=log_data.get('status'),
                        module=log_data.get('module'),
                        function=log_data.get('function'),
                        severity="high" if log_data.get('level') in ["ERROR", "CRITICAL"] else "normal",
                        artifacts=log_data.get('artifacts')  # Add artifacts support
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
                from timezone_utils import get_cutoff_datetime, format_datetime_for_db
                stuck_cutoff = get_cutoff_datetime(days=0, hours=0, minutes=30)
                stuck_ops = db.query(OperationDB).filter(
                    OperationDB.status.in_(["processing", "fetching_context", "preparing"]),
                    OperationDB.started_at < format_datetime_for_db(stuck_cutoff)
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
                from timezone_utils import get_cutoff_datetime, format_datetime_for_db
                
                # Get performance data for last 24 hours
                day_ago = get_cutoff_datetime(days=1)
                recent_ops = db.query(OperationDB).filter(OperationDB.started_at >= format_datetime_for_db(day_ago)).all()
                
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
        
        # PR-Agent Path Management Endpoints
        @self.app.get("/api/config/pr-agent-path")
        async def get_pr_agent_path():
            """Get the current PR-agent install path configuration"""
            try:
                custom_path = self.config_service.system_settings.get_pr_agent_install_path()
                effective_path = self.config_service.system_settings.get_effective_pr_agent_path()
                default_path = self.config_service.system_settings.get_default_pr_agent_path()
                validation = self.config_service.validate_current_path()
                
                return APIResponse(data={
                    "custom_path": custom_path,
                    "effective_path": effective_path,
                    "default_path": default_path,
                    "using_custom": custom_path is not None,
                    "validation": validation
                })
            except Exception as e:
                logger.error(f"Error getting PR-agent path: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Failed to get PR-agent path: {str(e)}")
        
        @self.app.post("/api/config/pr-agent-path/validate")
        async def validate_pr_agent_path(path_data: dict):
            """Validate a PR-agent install path"""
            try:
                path = path_data.get("path", "").strip()
                if not path:
                    raise HTTPException(status_code=400, detail="Path is required")
                
                validation = self.config_service.system_settings.validate_pr_agent_path(path)
                return APIResponse(data=validation)
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error validating PR-agent path: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Failed to validate path: {str(e)}")
        
        @self.app.post("/api/config/pr-agent-path")
        async def set_pr_agent_path(path_data: dict):
            """Set the PR-agent install path"""
            try:
                path = path_data.get("path", "").strip()
                
                # If empty path, clear the custom setting (use default)
                if not path:
                    success = self.config_service.system_settings.delete_setting("pr_agent_install_path")
                    if success:
                        # Refresh paths in config service
                        self.config_service.refresh_paths()
                        validation = self.config_service.validate_current_path()
                        return APIResponse(data={
                            "success": True,
                            "message": "PR-agent path reset to default",
                            "effective_path": self.config_service.system_settings.get_effective_pr_agent_path(),
                            "validation": validation
                        })
                    else:
                        raise HTTPException(status_code=500, detail="Failed to reset PR-agent path")
                
                # Validate the path first
                validation = self.config_service.system_settings.validate_pr_agent_path(path)
                if not validation.get("valid", False):
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Invalid PR-agent path: {validation.get('error', 'Unknown error')}"
                    )
                
                # Set the path
                success = self.config_service.system_settings.set_pr_agent_install_path(path)
                if success:
                    # Refresh paths in config service
                    self.config_service.refresh_paths()
                    validation = self.config_service.validate_current_path()
                    return APIResponse(data={
                        "success": True,
                        "message": "PR-agent path updated successfully",
                        "effective_path": path,
                        "validation": validation
                    })
                else:
                    raise HTTPException(status_code=500, detail="Failed to update PR-agent path")
                    
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error setting PR-agent path: {str(e)}")
                raise HTTPException(status_code=500, detail=f"Failed to set PR-agent path: {str(e)}")

        
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
            """Get health status of all repositories with runner services configured"""
            try:
                from services.runner_health_service import RunnerHealthService
                
                runner_service = RunnerHealthService()
                try:
                    # Use the proper runner health service that only considers repositories with runner services
                    health_summary = await runner_service.get_repository_health_summary(db)
                    
                    # Build response in expected format
                    response_data = {
                        "data": health_summary,
                        "message": "Repository health retrieved successfully"
                    }
                    
                    return response_data
                        
                finally:
                    await runner_service.close_session()
                    
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
                    
                    # Auto-fetch best practices content
                    try:
                        from services.git_utils import get_best_practices_content
                        from pr_agent.git_providers.github_provider import GithubProvider
                        from pr_agent.git_providers.azuredevops_provider import AzureDevopsProvider
                        
                        git_provider = None
                        if repo.provider == 'github' and repo.github_token:
                            git_provider = GithubProvider()
                            git_provider.github_token = repo.github_token
                            # Set repository information
                            git_provider.repo = repo.name
                            try:
                                git_provider.repo_obj = git_provider.github_client.get_repo(repo.name)
                            except Exception as repo_error:
                                logger.warning(f"Could not get repository object for {repo.name}: {repo_error}")
                                # Continue without repo_obj, get_best_practices_content will try different approaches
                        elif repo.provider == 'azure_devops' and repo.azure_pat:
                            # Configure Azure DevOps settings
                            self._configure_azure_devops_settings(repo)
                            git_provider = AzureDevopsProvider()
                            # Set repository information
                            git_provider.repo = repo.name
                        
                        if git_provider:
                            best_practices_content = get_best_practices_content(git_provider)
                            repo.has_best_practices = bool(best_practices_content)
                            repo.best_practices_content = best_practices_content
                            repo.best_practices_last_fetched = datetime.utcnow()
                            logger.info(f"Auto-fetched best practices for repository {repo.name}: {'found' if best_practices_content else 'not found'}")
                    except Exception as e:
                        logger.warning(f"Failed to auto-fetch best practices for repository {repo.name}: {e}")
                    
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

        @self.app.get("/api/repositories/{repo_id}/best-practices")
        async def get_repository_best_practices(repo_id: int, force_refresh: bool = False, db: Session = Depends(get_db)):
            """Get best practices file content from repository"""
            try:
                # Get repository
                repo = db.query(RepositoryDB).filter(RepositoryDB.id == repo_id).first()
                if not repo:
                    raise HTTPException(status_code=404, detail="Repository not found")
                
                best_practices_content = ""
                
                # If we have cached content and not forcing refresh, use it
                if not force_refresh and repo.best_practices_content and repo.best_practices_last_fetched:
                    # Check if cache is relatively fresh (less than 1 hour old)
                    from datetime import timedelta
                    cache_age = datetime.utcnow() - repo.best_practices_last_fetched
                    if cache_age < timedelta(hours=1):
                        best_practices_content = repo.best_practices_content
                        logger.info(f"Using cached best practices for repository {repo.name}")
                
                # If no cached content or forcing refresh, fetch from git
                if not best_practices_content or force_refresh:
                    try:
                        from services.git_utils import get_best_practices_content
                        from pr_agent.git_providers.github_provider import GithubProvider
                        from pr_agent.git_providers.azuredevops_provider import AzureDevopsProvider
                        
                        git_provider = None
                        if repo.provider == 'github' and repo.github_token:
                            git_provider = GithubProvider()
                            git_provider.github_token = repo.github_token
                            # Set repository information
                            git_provider.repo = repo.name
                            try:
                                git_provider.repo_obj = git_provider.github_client.get_repo(repo.name)
                            except Exception as repo_error:
                                logger.warning(f"Could not get repository object for {repo.name}: {repo_error}")
                                # Continue without repo_obj, get_best_practices_content will try different approaches
                        elif repo.provider == 'azure_devops' and repo.azure_pat:
                            # Configure Azure DevOps settings
                            self._configure_azure_devops_settings(repo)
                            git_provider = AzureDevopsProvider()
                            # Set repository information
                            git_provider.repo = repo.name
                        else:
                            raise HTTPException(status_code=400, detail=f"Repository provider {repo.provider} not supported or tokens not configured")
                        
                        # Get best practices content
                        best_practices_content = get_best_practices_content(git_provider)
                        
                        # Update cache
                        repo.has_best_practices = bool(best_practices_content)
                        repo.best_practices_content = best_practices_content
                        repo.best_practices_last_fetched = datetime.utcnow()
                        db.commit()
                        
                        logger.info(f"Refreshed best practices for repository {repo.name}: {'found' if best_practices_content else 'not found'}")
                    except Exception as fetch_error:
                        logger.error(f"Failed to fetch best practices: {fetch_error}")
                        # Fall back to cached content if available
                        if repo.best_practices_content:
                            best_practices_content = repo.best_practices_content
                            logger.info(f"Using cached best practices due to fetch error")
                        else:
                            raise HTTPException(status_code=500, detail=f"Error retrieving best practices: {str(fetch_error)}")
                
                if best_practices_content:
                    # Convert markdown to HTML for nice rendering
                    try:
                        import markdown
                        from markdown.extensions import codehilite, fenced_code, tables
                        
                        md = markdown.Markdown(extensions=[
                            'codehilite',
                            'fenced_code', 
                            'tables',
                            'nl2br',
                            'toc'
                        ])
                        content_html = md.convert(best_practices_content)
                    except ImportError:
                        # Fallback to plain text if markdown is not available
                        content_html = f"<pre>{best_practices_content}</pre>"
                    
                    result = {
                        "exists": True,
                        "content": best_practices_content,
                        "content_html": content_html,
                        "file_name": "best_practices.md",
                        "repository": repo.name,
                        "last_fetched": repo.best_practices_last_fetched.isoformat() if repo.best_practices_last_fetched else None,
                        "has_pending_pr": bool(repo.best_practices_pr_status == "pending"),
                        "pr_url": repo.best_practices_pr_url,
                        "pr_number": repo.best_practices_pr_number,
                        "pr_status": repo.best_practices_pr_status
                    }
                else:
                    result = {
                        "exists": False,
                        "content": None,
                        "content_html": None,
                        "file_name": "best_practices.md",
                        "repository": repo.name,
                        "last_fetched": repo.best_practices_last_fetched.isoformat() if repo.best_practices_last_fetched else None,
                        "has_pending_pr": bool(repo.best_practices_pr_status == "pending"),
                        "pr_url": repo.best_practices_pr_url,
                        "pr_number": repo.best_practices_pr_number,
                        "pr_status": repo.best_practices_pr_status
                    }
                
                return APIResponse(data=result, message="Best practices retrieved successfully")
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error retrieving best practices for repository {repo_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Error retrieving best practices: {str(e)}")
        
        @self.app.put("/api/repositories/{repo_id}/best-practices")
        async def update_repository_best_practices(repo_id: int, content_data: dict, db: Session = Depends(get_db)):
            """Create or update best practices file via pull request"""
            try:
                # Get repository
                repo = db.query(RepositoryDB).filter(RepositoryDB.id == repo_id).first()
                if not repo:
                    raise HTTPException(status_code=404, detail="Repository not found")
                
                content = content_data.get("content", "").strip()
                if not content:
                    raise HTTPException(status_code=400, detail="Content cannot be empty")
                
                # Set up git provider
                from pr_agent.git_providers.github_provider import GithubProvider
                from pr_agent.git_providers.azuredevops_provider import AzureDevopsProvider
                from datetime import datetime
                
                git_provider = None
                if repo.provider == 'github' and repo.github_token:
                    git_provider = GithubProvider()
                    git_provider.github_token = repo.github_token
                    # Parse repository owner and name from URL
                    repo_parts = repo.name.split('/')
                    if len(repo_parts) != 2:
                        raise HTTPException(status_code=400, detail="Invalid repository name format")
                    owner, repo_name = repo_parts
                    git_provider.repo = repo.name
                    git_provider.repo_obj = git_provider.github_client.get_repo(repo.name)
                elif repo.provider == 'azure_devops' and repo.azure_pat:
                    # Azure DevOps PR creation using REST API
                    from services.azure_pipeline_config_service import AzurePipelineConfigService
                    azure_service = AzurePipelineConfigService()
                    
                    # Parse Azure URL to get org/project/repo info
                    org_info = azure_service._parse_azure_repo_url(repo.url)
                    if not org_info['success']:
                        raise HTTPException(status_code=400, detail=f"Invalid Azure DevOps URL: {org_info['error']}")
                    
                    repo_name = org_info['repository']
                else:
                    raise HTTPException(status_code=400, detail=f"Repository provider {repo.provider} not supported or tokens not configured")
                
                # Generate branch name
                timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
                branch_name = f"update-best-practices-{repo_name}-{timestamp}"
                
                try:
                    # Check if we have a pending PR
                    if repo.best_practices_pr_status == "pending" and repo.best_practices_pr_branch:
                        # Update existing PR by adding commit to the same branch
                        logger.info(f"Updating existing best practices PR for {repo.name} on branch {repo.best_practices_pr_branch}")
                        
                        # Use existing branch
                        branch_name = repo.best_practices_pr_branch
                        git_provider.create_or_update_pr_file(
                            file_path="best_practices.md",
                            branch=branch_name,
                            contents=content,
                            message=f"Update best practices file\n\nUpdated via PR Agent Dashboard"
                        )
                        
                        # Return existing PR info
                        result = {
                            "pr_url": repo.best_practices_pr_url,
                            "pr_number": repo.best_practices_pr_number,
                            "branch_name": branch_name,
                            "status": "updated",
                            "action": "updated_existing_pr"
                        }
                        
                    else:
                        # Create new PR
                        logger.info(f"Creating new best practices PR for {repo.name} on branch {branch_name}")
                        
                        # First, create the branch from the default branch
                        default_branch = git_provider.repo_obj.default_branch
                        default_branch_ref = git_provider.repo_obj.get_git_ref(f"heads/{default_branch}")
                        try:
                            git_provider.repo_obj.create_git_ref(
                                ref=f"refs/heads/{branch_name}",
                                sha=default_branch_ref.object.sha
                            )
                            logger.info(f"Created branch {branch_name} from {default_branch}")
                        except Exception as branch_error:
                            if "already exists" in str(branch_error):
                                logger.info(f"Branch {branch_name} already exists, using existing branch")
                            else:
                                raise branch_error
                        
                        # Now create the file on the new branch
                        git_provider.create_or_update_pr_file(
                            file_path="best_practices.md",
                            branch=branch_name,
                            contents=content,
                            message=f"{'Create' if not repo.has_best_practices else 'Update'} best practices file\n\nThis file defines coding standards and best practices for this repository.\nPR-Agent will automatically enforce these practices during code review.\n\nCreated via PR Agent Dashboard"
                        )
                        
                        # Create pull request
                        pr_title = f"{'Create' if not repo.has_best_practices else 'Update'} best practices documentation"
                        pr_body = f"""## Best Practices {'Creation' if not repo.has_best_practices else 'Update'}

This PR {'creates' if not repo.has_best_practices else 'updates'} the `best_practices.md` file for this repository.

### What this enables:
- 🎯 **Automated code review guidance**: PR-Agent will automatically reference these best practices during code reviews
- 📋 **Consistent coding standards**: All team members will see these practices during development
- 🚀 **Improved code quality**: Violations will be flagged with "best practice" suggestions

### File location:
- `best_practices.md` in repository root

### Next steps:
1. Review the content below
2. Merge this PR to activate best practices enforcement
3. PR-Agent will automatically start referencing these practices in future code reviews

---

*This PR was created automatically via PR Agent Dashboard*"""
                        
                        # Create the PR using GitHub API
                        try:
                            pr_response = git_provider.repo_obj.create_pull(
                                title=pr_title,
                                body=pr_body,
                                head=branch_name,
                                base=git_provider.repo_obj.default_branch
                            )
                            
                            # Update repository with PR info
                            repo.best_practices_pr_url = pr_response.html_url
                            repo.best_practices_pr_number = pr_response.number
                            repo.best_practices_pr_branch = branch_name
                            repo.best_practices_pr_status = "pending"
                            db.commit()
                            
                            result = {
                                "pr_url": pr_response.html_url,
                                "pr_number": pr_response.number,
                                "branch_name": branch_name,
                                "status": "pending",
                                "action": "created_new_pr"
                            }
                            
                            logger.info(f"Created best practices PR #{pr_response.number} for {repo.name}")
                            
                        except Exception as pr_error:
                            logger.error(f"Failed to create PR: {pr_error}")
                            raise HTTPException(status_code=500, detail=f"Failed to create pull request: {str(pr_error)}")
                    
                    return APIResponse(data=result, message="Best practices PR created/updated successfully")
                    
                except Exception as git_error:
                    logger.error(f"Git operation failed: {git_error}")
                    raise HTTPException(status_code=500, detail=f"Git operation failed: {str(git_error)}")
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error updating best practices for repository {repo_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Error updating best practices: {str(e)}")
        
        @self.app.post("/api/repositories/{repo_id}/best-practices/check-pr-status") 
        async def check_best_practices_pr_status(repo_id: int, db: Session = Depends(get_db)):
            """Check if pending best practices PR has been merged and update status"""
            try:
                # Get repository
                repo = db.query(RepositoryDB).filter(RepositoryDB.id == repo_id).first()
                if not repo:
                    raise HTTPException(status_code=404, detail="Repository not found")
                
                if not repo.best_practices_pr_status == "pending" or not repo.best_practices_pr_number:
                    return APIResponse(data={"status": repo.best_practices_pr_status}, message="No pending PR to check")
                
                # Set up git provider to check PR status
                from pr_agent.git_providers.github_provider import GithubProvider
                
                if repo.provider == 'github' and repo.github_token:
                    git_provider = GithubProvider()
                    git_provider.github_token = repo.github_token
                    git_provider.repo = repo.name
                    git_provider.repo_obj = git_provider.github_client.get_repo(repo.name)
                    
                    try:
                        # Get PR status
                        pr = git_provider.repo_obj.get_pull(repo.best_practices_pr_number)
                        
                        if pr.state == "closed" and pr.merged:
                            # PR was merged - update status and refresh content
                            repo.best_practices_pr_status = "merged"
                            
                            # Refresh best practices content from main branch
                            from services.git_utils import get_best_practices_content
                            best_practices_content = get_best_practices_content(git_provider)
                            repo.has_best_practices = bool(best_practices_content)
                            repo.best_practices_content = best_practices_content
                            repo.best_practices_last_fetched = datetime.utcnow()
                            
                            db.commit()
                            
                            logger.info(f"Best practices PR #{repo.best_practices_pr_number} for {repo.name} was merged")
                            return APIResponse(data={"status": "merged", "content_updated": True}, message="PR was merged and content updated")
                            
                        elif pr.state == "closed" and not pr.merged:
                            # PR was closed without merging
                            repo.best_practices_pr_status = "closed"
                            db.commit()
                            
                            logger.info(f"Best practices PR #{repo.best_practices_pr_number} for {repo.name} was closed without merging")
                            return APIResponse(data={"status": "closed"}, message="PR was closed without merging")
                        
                        else:
                            # PR is still open
                            return APIResponse(data={"status": "pending"}, message="PR is still pending")
                            
                    except Exception as pr_error:
                        logger.error(f"Failed to check PR status: {pr_error}")
                        raise HTTPException(status_code=500, detail=f"Failed to check PR status: {str(pr_error)}")
                
                else:
                    raise HTTPException(status_code=400, detail="GitHub provider and token required for PR status checking")
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error checking best practices PR status for repository {repo_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Error checking PR status: {str(e)}")

        @self.app.get("/api/repositories/{repo_id}/pr-agent-config")
        async def get_repository_pr_agent_config(repo_id: int, force_refresh: bool = False, db: Session = Depends(get_db)):
            """Get PR-Agent config file content from repository"""
            try:
                from datetime import datetime, timedelta
                
                # Get repository
                repo = db.query(RepositoryDB).filter(RepositoryDB.id == repo_id).first()
                if not repo:
                    raise HTTPException(status_code=404, detail="Repository not found")
                
                pr_agent_config_content = ""
                
                # Check if we should use cached content
                if not force_refresh and repo.pr_agent_config_content and repo.pr_agent_config_last_fetched:
                    # Use cache if it's less than 1 hour old
                    cache_age = datetime.utcnow() - repo.pr_agent_config_last_fetched
                    if cache_age < timedelta(hours=1):
                        pr_agent_config_content = repo.pr_agent_config_content
                        logger.info(f"Using cached PR-Agent config for repository {repo.name}")
                
                # Fetch fresh content if no cache or force refresh
                if not pr_agent_config_content or force_refresh:
                    try:
                        from services.git_utils import get_pr_agent_config_content
                        from pr_agent.git_providers.github_provider import GithubProvider
                        from pr_agent.git_providers.azuredevops_provider import AzureDevopsProvider
                        
                        git_provider = None
                        if repo.provider == 'github' and repo.github_token:
                            git_provider = GithubProvider()
                            git_provider.github_token = repo.github_token
                            git_provider.repo = repo.name
                            git_provider.repo_obj = git_provider.github_client.get_repo(repo.name)
                        elif repo.provider == 'azure_devops' and repo.azure_pat:
                            # Configure Azure DevOps settings
                            self._configure_azure_devops_settings(repo)
                            git_provider = AzureDevopsProvider()
                            # Set repository information
                            git_provider.repo = repo.name
                        else:
                            # Continue without repo_obj, get_pr_agent_config_content will try different approaches
                            logger.warning(f"No provider configured for repository {repo.name}, attempting direct fetch")
                        
                        # Get PR-Agent config content
                        pr_agent_config_content = get_pr_agent_config_content(git_provider)
                        
                        # Update cache
                        repo.has_pr_agent_config = bool(pr_agent_config_content)
                        repo.pr_agent_config_content = pr_agent_config_content
                        repo.pr_agent_config_last_fetched = datetime.utcnow()
                        db.commit()
                        
                        logger.info(f"Refreshed PR-Agent config for repository {repo.name}: {'found' if pr_agent_config_content else 'not found'}")
                    except Exception as fetch_error:
                        logger.error(f"Failed to fetch PR-Agent config: {fetch_error}")
                        # Fall back to cached content if available
                        if repo.pr_agent_config_content:
                            pr_agent_config_content = repo.pr_agent_config_content
                            logger.info(f"Using cached PR-Agent config due to fetch error")
                        else:
                            raise HTTPException(status_code=500, detail=f"Error retrieving PR-Agent config: {str(fetch_error)}")
                
                if pr_agent_config_content:
                    # Parse TOML content to validate it and potentially return as JSON
                    try:
                        import toml
                        parsed_config = toml.loads(pr_agent_config_content)
                        
                        return APIResponse(data={
                            "content": pr_agent_config_content,
                            "parsed_config": parsed_config,
                            "has_config": True,
                            "last_fetched": repo.pr_agent_config_last_fetched.isoformat() if repo.pr_agent_config_last_fetched else None,
                            "pr_status": repo.pr_agent_config_pr_status,
                            "pr_url": repo.pr_agent_config_pr_url,
                            "pr_number": repo.pr_agent_config_pr_number
                        }, message="PR-Agent config found")
                    except Exception as parse_error:
                        logger.warning(f"Failed to parse PR-Agent config TOML: {parse_error}")
                        return APIResponse(data={
                            "content": pr_agent_config_content,
                            "parsed_config": None,
                            "has_config": True,
                            "parse_error": str(parse_error),
                            "last_fetched": repo.pr_agent_config_last_fetched.isoformat() if repo.pr_agent_config_last_fetched else None,
                            "pr_status": repo.pr_agent_config_pr_status,
                            "pr_url": repo.pr_agent_config_pr_url,
                            "pr_number": repo.pr_agent_config_pr_number
                        }, message="PR-Agent config found (parse error)")
                else:
                    return APIResponse(data={
                        "content": "",
                        "parsed_config": None,
                        "has_config": False,
                        "last_fetched": repo.pr_agent_config_last_fetched.isoformat() if repo.pr_agent_config_last_fetched else None,
                        "pr_status": repo.pr_agent_config_pr_status,
                        "pr_url": repo.pr_agent_config_pr_url,
                        "pr_number": repo.pr_agent_config_pr_number
                    }, message="No PR-Agent config found")
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error retrieving PR-Agent config for repository {repo_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Error retrieving PR-Agent config: {str(e)}")

        @self.app.put("/api/repositories/{repo_id}/pr-agent-config")
        async def update_repository_pr_agent_config(repo_id: int, content_data: dict, db: Session = Depends(get_db)):
            """Create or update PR-Agent config file via pull request"""
            try:
                # Get repository
                repo = db.query(RepositoryDB).filter(RepositoryDB.id == repo_id).first()
                if not repo:
                    raise HTTPException(status_code=404, detail="Repository not found")
                
                # Handle content extraction with proper error handling
                if not isinstance(content_data, dict):
                    logger.error(f"Expected dict but received {type(content_data)}: {content_data}")
                    raise HTTPException(status_code=400, detail="Request body must be a JSON object")
                
                content_raw = content_data.get("content", "")
                
                if isinstance(content_raw, dict):
                    logger.error(f"Received dict instead of string for content: {content_raw}")
                    raise HTTPException(status_code=400, detail="Content must be a string, not a dictionary")
                
                content = str(content_raw).strip() if content_raw else ""
                if not content:
                    raise HTTPException(status_code=400, detail="Content cannot be empty")
                
                # Validate TOML content
                try:
                    import toml
                    parsed_config = toml.loads(content)
                except Exception as toml_error:
                    raise HTTPException(status_code=400, detail=f"Invalid TOML format: {str(toml_error)}")
                
                # Set up git provider
                from pr_agent.git_providers.github_provider import GithubProvider
                from pr_agent.git_providers.azuredevops_provider import AzureDevopsProvider
                from datetime import datetime
                
                git_provider = None
                if repo.provider == 'github' and repo.github_token:
                    git_provider = GithubProvider()
                    git_provider.github_token = repo.github_token
                    # Parse repository owner and name from URL
                    repo_parts = repo.name.split('/')
                    if len(repo_parts) != 2:
                        raise HTTPException(status_code=400, detail="Invalid repository name format")
                    owner, repo_name = repo_parts
                    git_provider.repo = repo.name
                    git_provider.repo_obj = git_provider.github_client.get_repo(repo.name)
                elif repo.provider == 'azure_devops' and repo.azure_pat:
                    # Azure DevOps PR creation using REST API  
                    from services.azure_pipeline_config_service import AzurePipelineConfigService
                    azure_service = AzurePipelineConfigService()
                    
                    # Parse Azure URL to get org/project/repo info
                    org_info = azure_service._parse_azure_repo_url(repo.url)
                    if not org_info['success']:
                        raise HTTPException(status_code=400, detail=f"Invalid Azure DevOps URL: {org_info['error']}")
                    
                    repo_name = org_info['repository']
                else:
                    raise HTTPException(status_code=400, detail=f"Repository provider {repo.provider} not supported or tokens not configured")
                
                # Generate branch name
                timestamp = datetime.utcnow().strftime("%Y%m%d-%H%M%S")
                branch_name = f"update-pr-agent-config-{repo_name}-{timestamp}"
                
                try:
                    # Check if we have a pending PR
                    if repo.pr_agent_config_pr_status == "pending" and repo.pr_agent_config_pr_branch:
                        # Update existing PR by adding commit to the same branch
                        logger.info(f"Updating existing PR-Agent config PR for {repo.name} on branch {repo.pr_agent_config_pr_branch}")
                        
                        # Use existing branch
                        branch_name = repo.pr_agent_config_pr_branch
                        git_provider.create_or_update_pr_file(
                            file_path=".pr_agent.toml",
                            branch=branch_name,
                            contents=content,
                            message=f"Update PR-Agent configuration\n\nUpdated via PR Agent Dashboard"
                        )
                        
                        # Return existing PR info
                        result = {
                            "pr_url": repo.pr_agent_config_pr_url,
                            "pr_number": repo.pr_agent_config_pr_number,
                            "branch_name": branch_name,
                            "status": "updated",
                            "action": "updated_existing_pr"
                        }
                        
                    else:
                        # Create new PR
                        logger.info(f"Creating new PR-Agent config PR for {repo.name} on branch {branch_name}")
                        
                        # First, create the branch from the default branch
                        default_branch = git_provider.repo_obj.default_branch
                        default_branch_ref = git_provider.repo_obj.get_git_ref(f"heads/{default_branch}")
                        try:
                            git_provider.repo_obj.create_git_ref(
                                ref=f"refs/heads/{branch_name}",
                                sha=default_branch_ref.object.sha
                            )
                            logger.info(f"Created branch {branch_name} from {default_branch}")
                        except Exception as branch_error:
                            if "already exists" in str(branch_error):
                                logger.info(f"Branch {branch_name} already exists, using existing branch")
                            else:
                                raise branch_error
                        
                        # Now create the file on the new branch
                        git_provider.create_or_update_pr_file(
                            file_path=".pr_agent.toml",
                            branch=branch_name,
                            contents=content,
                            message=f"{'Create' if not repo.has_pr_agent_config else 'Update'} PR-Agent configuration\n\nThis file defines repository-specific configuration overrides for PR-Agent.\nThese settings will take precedence over global configuration.\n\nCreated via PR Agent Dashboard"
                        )
                        
                        # Create pull request
                        pr_title = f"{'Create' if not repo.has_pr_agent_config else 'Update'} PR-Agent configuration"
                        pr_body = f"""## PR-Agent Configuration {'Creation' if not repo.has_pr_agent_config else 'Update'}

This PR {'creates' if not repo.has_pr_agent_config else 'updates'} the `.pr_agent.toml` file for this repository.

### What this enables:
- 🎯 **Repository-specific settings**: Override global PR-Agent configuration for this repo
- ⚙️ **Customized behavior**: Tailor PR-Agent's actions to match this repository's needs
- 🔧 **Fine-tuned control**: Configure models, prompts, thresholds, and other settings

### File location:
- `.pr_agent.toml` in repository root

### Configuration scope:
This file can override any setting from the global PR-Agent configuration, including:
- AI models and reasoning settings
- Code review parameters
- Suggestion thresholds
- Custom instructions
- Feature toggles

### Next steps:
1. Review the configuration below
2. Merge this PR to activate repository-specific settings
3. PR-Agent will automatically use these settings for this repository

---

*This PR was created automatically via PR Agent Dashboard*"""
                        
                        # Create the PR using GitHub API
                        try:
                            pr_response = git_provider.repo_obj.create_pull(
                                title=pr_title,
                                body=pr_body,
                                head=branch_name,
                                base=git_provider.repo_obj.default_branch
                            )
                            
                            # Update repository with PR info
                            repo.pr_agent_config_pr_url = pr_response.html_url
                            repo.pr_agent_config_pr_number = pr_response.number
                            repo.pr_agent_config_pr_branch = branch_name
                            repo.pr_agent_config_pr_status = "pending"
                            db.commit()
                            
                            result = {
                                "pr_url": pr_response.html_url,
                                "pr_number": pr_response.number,
                                "branch_name": branch_name,
                                "status": "pending",
                                "action": "created_new_pr"
                            }
                            
                            logger.info(f"Created PR-Agent config PR #{pr_response.number} for {repo.name}")
                            
                        except Exception as pr_error:
                            logger.error(f"Failed to create PR: {pr_error}")
                            raise HTTPException(status_code=500, detail=f"Failed to create pull request: {str(pr_error)}")
                    
                    return APIResponse(data=result, message="PR-Agent config PR created/updated successfully")
                    
                except Exception as git_error:
                    logger.error(f"Git operation failed: {git_error}")
                    raise HTTPException(status_code=500, detail=f"Git operation failed: {str(git_error)}")
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error updating PR-Agent config for repository {repo_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Error updating PR-Agent config: {str(e)}")

        @self.app.post("/api/repositories/{repo_id}/pr-agent-config/check-pr-status") 
        async def check_pr_agent_config_pr_status(repo_id: int, db: Session = Depends(get_db)):
            """Check if pending PR-Agent config PR has been merged and update status"""
            try:
                # Get repository
                repo = db.query(RepositoryDB).filter(RepositoryDB.id == repo_id).first()
                if not repo:
                    raise HTTPException(status_code=404, detail="Repository not found")
                
                if not repo.pr_agent_config_pr_status == "pending" or not repo.pr_agent_config_pr_number:
                    return APIResponse(data={"status": repo.pr_agent_config_pr_status}, message="No pending PR to check")
                
                # Set up git provider to check PR status
                from pr_agent.git_providers.github_provider import GithubProvider
                
                if repo.provider == 'github' and repo.github_token:
                    git_provider = GithubProvider()
                    git_provider.github_token = repo.github_token
                    git_provider.repo = repo.name
                    git_provider.repo_obj = git_provider.github_client.get_repo(repo.name)
                    
                    try:
                        # Get PR status
                        pr = git_provider.repo_obj.get_pull(repo.pr_agent_config_pr_number)
                        
                        if pr.state == "closed" and pr.merged:
                            # PR was merged - update status and refresh content
                            repo.pr_agent_config_pr_status = "merged"
                            
                            # Refresh PR-Agent config content from main branch
                            from pr_agent.algo.utils import get_pr_agent_config_content
                            pr_agent_config_content = get_pr_agent_config_content(git_provider)
                            repo.has_pr_agent_config = bool(pr_agent_config_content)
                            repo.pr_agent_config_content = pr_agent_config_content
                            repo.pr_agent_config_last_fetched = datetime.utcnow()
                            
                            db.commit()
                            
                            logger.info(f"PR-Agent config PR #{repo.pr_agent_config_pr_number} for {repo.name} was merged")
                            return APIResponse(data={"status": "merged", "content_updated": True}, message="PR was merged and content updated")
                            
                        elif pr.state == "closed" and not pr.merged:
                            # PR was closed without merging
                            repo.pr_agent_config_pr_status = "closed"
                            db.commit()
                            
                            logger.info(f"PR-Agent config PR #{repo.pr_agent_config_pr_number} for {repo.name} was closed")
                            return APIResponse(data={"status": "closed"}, message="PR was closed without merging")
                            
                        else:
                            # PR is still pending
                            return APIResponse(data={"status": "pending"}, message="PR is still pending")
                    
                    except Exception as e:
                        logger.error(f"Error checking PR-Agent config PR status for repository {repo_id}: {e}")
                        raise HTTPException(status_code=500, detail=f"Error checking PR status: {str(e)}")
                
                else:
                    raise HTTPException(status_code=400, detail=f"Repository provider {repo.provider} not supported or tokens not configured")
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error checking PR-Agent config PR status for repository {repo_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Error checking PR status: {str(e)}")
        
        # GitHub Action Config endpoints
        @self.app.get("/api/repositories/{repo_id}/github-action-config")
        async def get_repository_github_action_config(repo_id: int, force_refresh: bool = False, db: Session = Depends(get_db)):
            """Get GitHub Action configuration for a repository"""
            try:
                # Get repository (using same approach as PR-Agent config endpoint)
                repo = db.query(RepositoryDB).filter(RepositoryDB.id == repo_id).first()
                if not repo:
                    raise HTTPException(status_code=404, detail="Repository not found")
                
                # Convert to dict for service
                repo_data = {
                    'id': repo.id,
                    'name': repo.name,
                    'provider': repo.provider,
                    'url': repo.url,
                    'github_token': repo.github_token
                }
                
                # Check GitHub Action config
                result = await self.github_action_config_service.check_github_action_config(repo_data)
                
                if result['exists']:
                    # Parse the YAML content
                    parse_result = self.github_action_config_service.parse_yaml_config(result['decoded_content'])
                    
                    if parse_result['success']:
                        return APIResponse(
                            data={
                                'exists': True,
                                'content': result['decoded_content'],
                                'env_vars': parse_result['env_vars'],
                                'config': parse_result['config'],
                                'last_modified': result['last_modified'],
                                'path': result['path'],
                                'sha': result['sha'],
                                'has_pending_pr': repo.github_action_config_pr_status == 'pending',
                                'pr_number': repo.github_action_config_pr_number,
                                'pr_url': repo.github_action_config_pr_url,
                                'pr_status': repo.github_action_config_pr_status
                            },
                            message="GitHub Action configuration retrieved"
                        )
                    else:
                        return APIResponse(
                            data={
                                'exists': True,
                                'content': result['decoded_content'],
                                'error': parse_result['error'],
                                'last_modified': result['last_modified'],
                                'path': result['path'],
                                'has_pending_pr': repo.github_action_config_pr_status == 'pending',
                                'pr_number': repo.github_action_config_pr_number,
                                'pr_url': repo.github_action_config_pr_url,
                                'pr_status': repo.github_action_config_pr_status
                            },
                            message="GitHub Action configuration found but could not be parsed"
                        )
                else:
                    # Return template for creation
                    template = self.github_action_config_service.get_default_config_template()
                    env_vars = self.github_action_config_service.get_github_action_env_vars()
                    
                    return APIResponse(
                        data={
                            'exists': False,
                            'template': template,
                            'env_vars': env_vars,
                            'error': result.get('error', 'Configuration not found'),
                            'has_pending_pr': repo.github_action_config_pr_status == 'pending',
                            'pr_number': repo.github_action_config_pr_number,
                            'pr_url': repo.github_action_config_pr_url,
                            'pr_status': repo.github_action_config_pr_status
                        },
                        message="GitHub Action configuration not found"
                    )
                    
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error getting GitHub Action config for repository {repo_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Error retrieving configuration: {str(e)}")

        @self.app.put("/api/repositories/{repo_id}/github-action-config")
        async def update_repository_github_action_config(repo_id: int, content_data: dict, db: Session = Depends(get_db)):
            """Update GitHub Action configuration for a repository"""
            try:
                # Get repository (using same approach as PR-Agent config endpoint)
                repo = db.query(RepositoryDB).filter(RepositoryDB.id == repo_id).first()
                if not repo:
                    raise HTTPException(status_code=404, detail="Repository not found")
                
                # Validate required fields
                if 'env_vars' not in content_data:
                    raise HTTPException(status_code=400, detail="Environment variables are required")
                
                # Convert to dict for service
                repo_data = {
                    'id': repo.id,
                    'name': repo.name,
                    'provider': repo.provider,
                    'url': repo.url,
                    'github_token': repo.github_token
                }
                
                # Generate YAML config from environment variables
                config_content = self.github_action_config_service.generate_yaml_config(content_data['env_vars'])
                
                # Create PR with the configuration
                result = await self.github_action_config_service.create_github_action_config_pr(repo_data, config_content, db)
                
                if result['success']:
                    return APIResponse(
                        data={
                            'pr_created': True,
                            'pr_number': result['pr_number'],
                            'pr_url': result['pr_url'],
                            'branch_name': result['branch_name']
                        },
                        message="GitHub Action configuration PR created successfully"
                    )
                else:
                    raise HTTPException(status_code=500, detail=f"Failed to create PR: {result['error']}")
                    
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error updating GitHub Action config for repository {repo_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Error updating configuration: {str(e)}")

        @self.app.post("/api/repositories/{repo_id}/github-action-config/check-pr-status")
        async def check_github_action_config_pr_status(repo_id: int, request_data: dict, db: Session = Depends(get_db)):
            """Check the status of a GitHub Action config pull request"""
            try:
                # Get repository (using same approach as PR-Agent config endpoint)
                repo = db.query(RepositoryDB).filter(RepositoryDB.id == repo_id).first()
                if not repo:
                    raise HTTPException(status_code=404, detail="Repository not found")
                
                # Get PR number from request data
                pr_number = request_data.get('pr_number')
                if not pr_number:
                    raise HTTPException(status_code=400, detail="PR number is required")
                
                # Set up git provider to check PR status
                from pr_agent.git_providers.github_provider import GithubProvider
                
                if repo.provider == 'github' and repo.github_token:
                    git_provider = GithubProvider()
                    git_provider.github_token = repo.github_token
                    git_provider.repo = repo.name
                    git_provider.repo_obj = git_provider.github_client.get_repo(repo.name)
                    
                    try:
                        # Get PR status
                        pr = git_provider.repo_obj.get_pull(pr_number)
                        
                        if pr.state == "closed" and pr.merged:
                            # PR was merged - update database
                            repo.github_action_config_pr_status = 'merged'
                            db.commit()
                            logger.info(f"GitHub Action config PR #{pr_number} for {repo.name} was merged")
                            return APIResponse(data={"status": "merged"}, message="PR was merged")
                            
                        elif pr.state == "closed" and not pr.merged:
                            # PR was closed without merging - update database
                            repo.github_action_config_pr_status = 'closed'
                            db.commit()
                            logger.info(f"GitHub Action config PR #{pr_number} for {repo.name} was closed")
                            return APIResponse(data={"status": "closed"}, message="PR was closed without merging")
                            
                        else:
                            # PR is still pending
                            return APIResponse(data={"status": "pending"}, message="PR is still pending")
                    
                    except Exception as e:
                        logger.error(f"Error checking GitHub Action config PR status for repository {repo_id}: {e}")
                        raise HTTPException(status_code=500, detail=f"Error checking PR status: {str(e)}")
                
                else:
                    raise HTTPException(status_code=400, detail=f"Repository provider {repo.provider} not supported or tokens not configured")
                    
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error checking GitHub Action config PR status for repository {repo_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Error checking PR status: {str(e)}")

        @self.app.get("/api/repositories/{repo_id}/github-action-config/env-vars")
        async def get_github_action_env_vars(repo_id: int):
            """Get available GitHub Action environment variables"""
            try:
                env_vars = self.github_action_config_service.get_github_action_env_vars()
                return APIResponse(
                    data={'env_vars': env_vars},
                    message="GitHub Action environment variables retrieved"
                )
            except Exception as e:
                logger.error(f"Error getting GitHub Action env vars: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/repositories/{repo_id}/github-action-config/template")
        async def get_github_action_config_template(repo_id: int):
            """Get GitHub Action config template for a repository"""
            try:
                from .services.github_action_config_service import GitHubActionConfigService
                service = GitHubActionConfigService()
                
                # Get template with placeholder environment variables
                template = service.get_yaml_template()
                
                return APIResponse(data={"template": template}, message="Template retrieved successfully")
                
            except Exception as e:
                logger.error(f"Error getting GitHub Action config template: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        # Azure Pipeline config endpoints
        @self.app.get("/api/repositories/{repo_id}/azure-pipeline-config")
        async def get_repository_azure_pipeline_config(repo_id: int, force_refresh: bool = False, db: Session = Depends(get_db)):
            """Get Azure Pipeline configuration for a repository"""
            try:
                # Get repository
                repo = db.query(RepositoryDB).filter(RepositoryDB.id == repo_id).first()
                if not repo:
                    raise HTTPException(status_code=404, detail="Repository not found")
                
                # Only check Azure DevOps repositories
                if repo.provider != 'azure_devops':
                    raise HTTPException(status_code=400, detail="Azure Pipeline config is only supported for Azure DevOps repositories")
                
                # Convert repository data to dict for service
                repo_data = {
                    'id': repo.id,
                    'name': repo.name,
                    'provider': repo.provider,
                    'url': repo.url,
                    'azure_pat': repo.azure_pat
                }
                
                # Check pipeline configuration
                config_info = await self.azure_pipeline_config_service.check_azure_pipeline_config(repo_data)
                
                return APIResponse(data=config_info, message="Azure Pipeline config checked successfully")
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error getting Azure Pipeline config for repository {repo_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Error retrieving configuration: {str(e)}")

        @self.app.put("/api/repositories/{repo_id}/azure-pipeline-config")
        async def update_repository_azure_pipeline_config(repo_id: int, content_data: dict, db: Session = Depends(get_db)):
            """Update Azure Pipeline configuration for a repository"""
            try:
                # Get repository
                repo = db.query(RepositoryDB).filter(RepositoryDB.id == repo_id).first()
                if not repo:
                    raise HTTPException(status_code=404, detail="Repository not found")
                
                # Validate required fields
                if 'content' not in content_data:
                    raise HTTPException(status_code=400, detail="Configuration content is required")
                
                # Convert to dict for service
                repo_data = {
                    'id': repo.id,
                    'name': repo.name,
                    'provider': repo.provider,
                    'url': repo.url,
                    'azure_pat': repo.azure_pat
                }
                
                # Use the provided content directly
                config_content = content_data['content']
                
                # Create PR with the configuration
                result = await self.azure_pipeline_config_service.create_azure_pipeline_config_pr(repo_data, config_content, db)
                
                if result['success']:
                    return APIResponse(
                        data={
                            'pr_created': True,
                            'pr_number': result['pr_number'],
                            'pr_url': result['pr_url'],
                            'branch_name': result['branch_name']
                        },
                        message="Azure Pipeline configuration PR created successfully"
                    )
                else:
                    raise HTTPException(status_code=500, detail=f"Failed to create PR: {result['error']}")
                    
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error updating Azure Pipeline config for repository {repo_id}: {e}")
                raise HTTPException(status_code=500, detail=f"Error updating configuration: {str(e)}")

        @self.app.get("/api/repositories/{repo_id}/azure-pipeline-config/env-vars")
        async def get_azure_pipeline_env_vars(repo_id: int):
            """Get list of available environment variables for Azure Pipeline configuration"""
            try:
                env_vars = self.azure_pipeline_config_service.get_azure_pipeline_env_vars()
                return APIResponse(data={"env_vars": env_vars}, message="Environment variables retrieved successfully")
            except Exception as e:
                logger.error(f"Error getting Azure Pipeline env vars: {e}")
                raise HTTPException(status_code=500, detail=f"Error retrieving environment variables: {str(e)}")

        @self.app.get("/api/repositories/{repo_id}/azure-pipeline-config/template")
        async def get_azure_pipeline_config_template(repo_id: int):
            """Get Azure Pipeline configuration template"""
            try:
                template = self.azure_pipeline_config_service.get_default_config_template()
                return APIResponse(data={"template": template}, message="Azure Pipeline config template retrieved successfully")
            except Exception as e:
                logger.error(f"Error getting Azure Pipeline config template: {e}")
                raise HTTPException(status_code=500, detail=f"Error retrieving template: {str(e)}")

        @self.app.get("/api/repositories/{repo_id}/azure-pipeline-config/check")
        async def check_azure_pipeline_config(repo_id: int, db: Session = Depends(get_db)):
            """Check Azure pipeline configuration status for a repository"""
            try:
                from services.azure_pipeline_config_service import AzurePipelineConfigService
                
                # Get repository
                repo = db.query(RepositoryDB).filter(RepositoryDB.id == repo_id).first()
                if not repo:
                    raise HTTPException(status_code=404, detail="Repository not found")
                
                if repo.provider != 'azure_devops':
                    raise HTTPException(status_code=400, detail="Repository is not an Azure DevOps repository")
                
                if not repo.azure_pat:
                    raise HTTPException(status_code=400, detail="Azure PAT not configured for this repository")
                
                service = AzurePipelineConfigService()
                
                # Check pipeline configuration
                pipeline_check = await service.check_azure_pipeline_config({
                    'name': repo.name,
                    'url': repo.url,
                    'provider': repo.provider,
                    'azure_pat': repo.azure_pat
                })
                
                return APIResponse(data=pipeline_check, message="Azure pipeline configuration checked")
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error checking Azure pipeline config for repository {repo_id}: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/repositories/{repo_id}/azure-pipeline-config/installation-guide")
        async def get_azure_pipeline_installation_guide(repo_id: int, db: Session = Depends(get_db)):
            """Get Azure Pipeline installation guide for a repository"""
            try:
                # Get repository
                repo = db.query(RepositoryDB).filter(RepositoryDB.id == repo_id).first()
                if not repo:
                    raise HTTPException(status_code=404, detail="Repository not found")
                
                if repo.provider != 'azure_devops':
                    raise HTTPException(status_code=400, detail="Repository is not an Azure DevOps repository")
                
                from services.azure_pipeline_config_service import AzurePipelineConfigService
                service = AzurePipelineConfigService()
                
                # Parse Azure repo info
                org_info = service._parse_azure_repo_url(repo.url)
                if not org_info['success']:
                    raise HTTPException(status_code=400, detail=f"Invalid Azure DevOps URL: {org_info['error']}")
                
                # Generate installation guide
                guide = {
                    "title": "Azure DevOps Pipeline Installation Guide",
                    "repository": repo.name,
                    "organization": org_info['organization'],
                    "project": org_info['project'],
                    "steps": [
                        {
                            "step": 1,
                            "title": "Create Azure Pipeline",
                            "description": "Set up a new pipeline in your Azure DevOps project",
                            "instructions": [
                                f"1. Navigate to your Azure DevOps project: https://dev.azure.com/{org_info['organization']}/{org_info['project']}",
                                "2. Click on 'Pipelines' in the left navigation menu",
                                "3. Click 'New pipeline' or 'Create Pipeline'",
                                "4. Select 'Azure Repos Git' as your code location",
                                f"5. Select your repository: {org_info['repository']}",
                                "6. Choose 'Existing Azure Pipelines YAML file'",
                                "7. Select the branch and path: '/azure-pipelines.yml'",
                                "8. Review and run the pipeline"
                            ]
                        },
                        {
                            "step": 2,
                            "title": "Configure Environment Variables",
                            "description": "Add required environment variables to your pipeline",
                            "instructions": [
                                "1. In your pipeline, click on 'Edit'",
                                "2. Click on 'Variables' (top right)",
                                "3. Add the following variables:",
                                "   - AZURE_DEVOPS_PAT: Your Azure DevOps Personal Access Token",
                                "   - AZURE_DEVOPS_ORG: Your organization name",
                                "   - Any additional PR-Agent configuration variables"
                            ],
                            "variables": service.get_environment_variables()
                        },
                        {
                            "step": 3,
                            "title": "Install Azure DevOps Agent (Optional)",
                            "description": "For private agents, install the Azure DevOps agent",
                            "instructions": [
                                "1. Download the agent from Azure DevOps",
                                "2. Extract and configure the agent",
                                "3. Register agent with your organization",
                                "4. Start the agent service"
                            ],
                            "agent_links": {
                                "download_url": f"https://dev.azure.com/{org_info['organization']}/_settings/agentpools",
                                "documentation": "https://docs.microsoft.com/en-us/azure/devops/pipelines/agents/"
                            }
                        },
                        {
                            "step": 4,
                            "title": "Test Pipeline",
                            "description": "Verify the pipeline works correctly",
                            "instructions": [
                                "1. Create a test pull request",
                                "2. Check that the pipeline triggers automatically",
                                "3. Verify PR-Agent comments appear on the pull request",
                                "4. Check pipeline logs for any errors"
                            ]
                        }
                    ],
                    "links": {
                        "project_url": f"https://dev.azure.com/{org_info['organization']}/{org_info['project']}",
                        "pipelines_url": f"https://dev.azure.com/{org_info['organization']}/{org_info['project']}/_build",
                        "settings_url": f"https://dev.azure.com/{org_info['organization']}/{org_info['project']}/_settings",
                        "agent_pools_url": f"https://dev.azure.com/{org_info['organization']}/_settings/agentpools"
                    },
                    "troubleshooting": [
                        {
                            "issue": "Pipeline not triggering on pull requests",
                            "solution": "Check that PR triggers are enabled in your azure-pipelines.yml file"
                        },
                        {
                            "issue": "Authentication errors",
                            "solution": "Verify your Azure DevOps PAT has the correct permissions (Code: Read & Write, Pull Request: Read & Write)"
                        },
                        {
                            "issue": "Agent not found",
                            "solution": "Check agent pool configuration and ensure agents are online"
                        }
                    ]
                }
                
                return APIResponse(data=guide, message="Installation guide generated")
                
            except HTTPException:
                raise
            except Exception as e:
                logger.error(f"Error generating Azure pipeline installation guide: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        # Runner service management endpoints
        @self.app.post("/api/repositories/{repo_id}/runner-service/check")
        async def check_runner_service(repo_id: int, request_data: dict, db: Session = Depends(get_db)):
            """Check the status of a GitHub Actions runner service"""
            try:
                # Get repository
                repo = db.query(RepositoryDB).filter(RepositoryDB.id == repo_id).first()
                if not repo:
                    raise HTTPException(status_code=404, detail="Repository not found")
                
                service_name = request_data.get("service_name")
                if not service_name:
                    raise HTTPException(status_code=400, detail="Service name is required")
                
                # Import and use the runner service monitor
                from services.runner_service_monitor import RunnerServiceMonitor
                monitor = RunnerServiceMonitor()
                
                # Check service status
                service_status = monitor.check_service_status(service_name)
                logger.info(f"Service status response from monitor: {service_status}")
                
                # Update repository with runner service information  
                repo.runner_service_name = service_name
                repo.runner_service_status = service_status.get('status', 'unknown')
                repo.runner_service_last_checked = datetime.utcnow()
                repo.runner_service_details = service_status
                
                # Map service status to repository health impact
                health_impact = monitor.get_service_health_impact(service_status)
                logger.info(f"Health impact determined: {health_impact}")
                
                # Update overall runner status based on service health impact
                if health_impact == 'healthy':
                    repo.runner_status = 'running'
                    repo.runner_error = None
                elif health_impact == 'warning':
                    repo.runner_status = 'warning'
                    repo.runner_error = f"Service {service_status.get('status')}: {service_status.get('status_display', 'Unknown')}"
                else:  # error
                    repo.runner_status = 'error'
                    repo.runner_error = service_status.get('error') or f"Service {service_status.get('status')}: {service_status.get('status_display', 'Unknown')}"
                
                db.commit()
                
                # Trigger a health system refresh to update overall status
                try:
                    health_status = await self.health_service.get_system_health(use_cache=False)
                    logger.info(f"System health refreshed after runner service check: {health_status.get('overall', {}).get('status', 'unknown')}")
                except Exception as e:
                    logger.warning(f"Failed to refresh system health after runner service check: {e}")
                
                logger.info(f"Final API response data: {service_status}")
                return APIResponse(data=service_status, message="Service status checked successfully")
                
            except Exception as e:
                logger.error(f"Error checking runner service: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.put("/api/repositories/{repo_id}/runner-service/name")
        async def save_runner_service_name(repo_id: int, request_data: dict, db: Session = Depends(get_db)):
            """Save the GitHub Actions runner service name for a repository"""
            try:
                # Get repository
                repo = db.query(RepositoryDB).filter(RepositoryDB.id == repo_id).first()
                if not repo:
                    raise HTTPException(status_code=404, detail="Repository not found")
                
                service_name = request_data.get("service_name")
                if not service_name:
                    raise HTTPException(status_code=400, detail="Service name is required")
                
                # Update repository with runner service name
                repo.runner_service_name = service_name
                db.commit()
                
                return APIResponse(data={"service_name": service_name}, message="Runner service name saved successfully")
                
            except Exception as e:
                logger.error(f"Error saving runner service name: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/repositories/{repo_id}/runner-service/list")
        async def list_github_runner_services(repo_id: int, db: Session = Depends(get_db)):
            """List all GitHub Actions runner services on the system"""
            try:
                # Get repository (for auth check)
                repo = db.query(RepositoryDB).filter(RepositoryDB.id == repo_id).first()
                if not repo:
                    raise HTTPException(status_code=404, detail="Repository not found")
                
                # Import and use the runner service monitor
                from services.runner_service_monitor import RunnerServiceMonitor
                monitor = RunnerServiceMonitor()
                
                # List all GitHub runner services
                services = monitor.list_github_runner_services()
                
                return APIResponse(data={"services": services}, message="GitHub runner services listed successfully")
                
            except Exception as e:
                logger.error(f"Error listing GitHub runner services: {e}")
                raise HTTPException(status_code=500, detail=str(e))
        
        @self.app.get("/api/system/runner-services")
        async def list_all_runner_services():
            """List all GitHub Actions runner services on the system (for debugging)"""
            try:
                from services.runner_service_monitor import RunnerServiceMonitor
                monitor = RunnerServiceMonitor()
                
                # List all GitHub runner services
                services = monitor.list_github_runner_services()
                
                # Also try to get all services that might be runners
                all_services = []
                try:
                    import subprocess
                    import json
                    
                    # Get all services containing "GitHub", "Actions", or "Runner"
                    cmd = [
                        'powershell.exe', 
                        '-NoProfile', 
                        '-Command',
                        'Get-Service | Where-Object { $_.Name -like "*GitHub*" -or $_.DisplayName -like "*GitHub*" -or $_.DisplayName -like "*Actions*" -or $_.DisplayName -like "*Runner*" } | ConvertTo-Json'
                    ]
                    
                    result = subprocess.run(
                        cmd, 
                        capture_output=True, 
                        text=True, 
                        timeout=15,
                        creationflags=subprocess.CREATE_NO_WINDOW
                    )
                    
                    if result.returncode == 0 and result.stdout.strip():
                        services_data = json.loads(result.stdout.strip())
                        
                        # Handle single service or list of services
                        if isinstance(services_data, dict):
                            services_data = [services_data]
                        elif not isinstance(services_data, list):
                            services_data = []
                        
                        for service in services_data:
                            all_services.append({
                                'name': service.get('Name', ''),
                                'display_name': service.get('DisplayName', ''),
                                'status': service.get('Status', 'Unknown'),
                                'can_stop': service.get('CanStop', False)
                            })
                            
                except Exception as e:
                    logger.warning(f"Could not get extended service list: {e}")
                
                return APIResponse(data={
                    "github_services": services,
                    "all_runner_related_services": all_services,
                    "total_found": len(services) + len(all_services)
                }, message="All runner services listed successfully")
                
            except Exception as e:
                logger.error(f"Error listing all runner services: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        # Azure DevOps agent service management endpoints
        @self.app.post("/api/repositories/{repo_id}/azure-agent-service/check")
        async def check_azure_agent_service(repo_id: int, request_data: dict, db: Session = Depends(get_db)):
            """Check the status of an Azure DevOps agent service"""
            try:
                # Get repository
                repo = db.query(RepositoryDB).filter(RepositoryDB.id == repo_id).first()
                if not repo:
                    raise HTTPException(status_code=404, detail="Repository not found")
                
                service_name = request_data.get("service_name")
                if not service_name:
                    raise HTTPException(status_code=400, detail="Service name is required")
                
                # Import and use the Azure agent service monitor
                from services.azure_agent_service_monitor import AzureAgentServiceMonitor
                monitor = AzureAgentServiceMonitor()
                
                # Check service status
                service_status = monitor.check_service_status(service_name)
                logger.info(f"Azure agent service status response: {service_status}")
                
                # Update repository with Azure agent service information  
                repo.azure_agent_service_name = service_name
                repo.azure_agent_service_status = service_status.get('status', 'unknown')
                repo.azure_agent_service_last_checked = datetime.utcnow()
                repo.azure_agent_service_details = service_status
                
                # Map service status to repository health impact
                health_impact = monitor.get_service_health_impact(service_status)
                logger.info(f"Azure agent health impact determined: {health_impact}")
                
                # Update overall Azure agent status based on service health impact
                if health_impact == 'healthy':
                    repo.azure_agent_status = 'running'
                    repo.azure_agent_error = None
                elif health_impact == 'warning':
                    repo.azure_agent_status = 'warning'
                    repo.azure_agent_error = f"Service {service_status.get('status')}: {service_status.get('status_display', 'Unknown')}"
                else:  # error
                    repo.azure_agent_status = 'error'
                    repo.azure_agent_error = service_status.get('error') or f"Service {service_status.get('status')}: {service_status.get('status_display', 'Unknown')}"
                
                db.commit()
                
                # Trigger a health system refresh to update overall status
                try:
                    health_status = await self.health_service.get_system_health(use_cache=False)
                    logger.info(f"System health refreshed after Azure agent service check: {health_status.get('overall', {}).get('status', 'unknown')}")
                except Exception as e:
                    logger.warning(f"Failed to refresh system health after Azure agent service check: {e}")
                
                logger.info(f"Final Azure agent API response data: {service_status}")
                return APIResponse(data=service_status, message="Azure agent service status checked successfully")
                
            except Exception as e:
                logger.error(f"Error checking Azure agent service: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.put("/api/repositories/{repo_id}/azure-agent-service/name")
        async def save_azure_agent_service_name(repo_id: int, request_data: dict, db: Session = Depends(get_db)):
            """Save the Azure DevOps agent service name for a repository"""
            try:
                # Get repository
                repo = db.query(RepositoryDB).filter(RepositoryDB.id == repo_id).first()
                if not repo:
                    raise HTTPException(status_code=404, detail="Repository not found")
                
                service_name = request_data.get("service_name")
                if not service_name:
                    raise HTTPException(status_code=400, detail="Service name is required")
                
                # Update repository with Azure agent service name
                repo.azure_agent_service_name = service_name
                db.commit()
                
                return APIResponse(data={"service_name": service_name}, message="Azure agent service name saved successfully")
                
            except Exception as e:
                logger.error(f"Error saving Azure agent service name: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/repositories/{repo_id}/azure-agent-service/list")
        async def list_azure_agent_services(repo_id: int, db: Session = Depends(get_db)):
            """List all Azure DevOps agent services on the system"""
            try:
                # Get repository (for auth check)
                repo = db.query(RepositoryDB).filter(RepositoryDB.id == repo_id).first()
                if not repo:
                    raise HTTPException(status_code=404, detail="Repository not found")
                
                # Import and use the Azure agent service monitor
                from services.azure_agent_service_monitor import AzureAgentServiceMonitor
                monitor = AzureAgentServiceMonitor()
                
                # List all Azure agent services
                services = monitor.list_azure_agent_services()
                
                return APIResponse(data={"services": services}, message="Azure agent services listed successfully")
                
            except Exception as e:
                logger.error(f"Error listing Azure agent services: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        # Token testing endpoints
        @self.app.post("/api/repositories/{repo_id}/test-token")
        async def test_repository_token(repo_id: int, db: Session = Depends(get_db)):
            """Test the repository's access token permissions"""
            try:
                # Get repository
                repo = db.query(RepositoryDB).filter(RepositoryDB.id == repo_id).first()
                if not repo:
                    raise HTTPException(status_code=404, detail="Repository not found")
                
                if repo.provider == 'github':
                    if not repo.github_token:
                        raise HTTPException(status_code=400, detail="No GitHub token configured")
                    
                    # Test GitHub token
                    result = await self._test_github_token(repo)
                    
                elif repo.provider == 'azure_devops':
                    if not repo.azure_pat:
                        raise HTTPException(status_code=400, detail="No Azure DevOps PAT configured")
                    
                    # Test Azure DevOps PAT
                    result = await self._test_azure_devops_token(repo)
                    
                else:
                    raise HTTPException(status_code=400, detail=f"Token testing not supported for provider: {repo.provider}")
                
                return APIResponse(data=result, message="Token test completed")
                
            except Exception as e:
                logger.error(f"Error testing token for repository {repo_id}: {e}")
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
                result = self.retention_service.create_backup(compressed=compressed)
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
            """Restore database from a backup file with progress updates"""
            import asyncio
            import concurrent.futures
            
            try:
                # Send initial progress update
                await self.websocket_manager.broadcast({
                    "type": "backup_restore_progress",
                    "progress": 0,
                    "message": "Starting backup restore...",
                    "filename": filename
                })
                
                # Send initial status
                await self.websocket_manager.broadcast({
                    "type": "backup_restore_progress",
                    "message": "Restoring database... This may take a few minutes.",
                    "filename": filename
                })
                
                # Run restore operation in thread pool
                loop = asyncio.get_event_loop()
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    result = await loop.run_in_executor(
                        executor, 
                        self.retention_service.restore_backup, 
                        filename, 
                        None  # No progress callback
                    )
                
                # Send completion update
                await self.websocket_manager.broadcast({
                    "type": "backup_restore_complete",
                    "success": result["success"],
                    "message": result.get("message", result.get("error", "Unknown result")),
                    "filename": filename
                })
                
                if result["success"]:
                    return APIResponse(data=result, message=result["message"])
                else:
                    raise HTTPException(status_code=400, detail=result["error"])
                    
            except Exception as e:
                logger.error(f"Failed to restore backup: {e}")
                
                # Send error update
                await self.websocket_manager.broadcast({
                    "type": "backup_restore_complete",
                    "success": False,
                    "message": str(e),
                    "filename": filename
                })
                
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/api/admin/timezone/validate")
        async def validate_timezone_storage(db: Session = Depends(get_db)):
            """Validate that database timestamps are properly stored in UTC"""
            try:
                from models import JobDB, OperationDB, LogEntryDB
                from datetime import timezone
                
                report = {
                    'status': 'success',
                    'issues_found': 0,
                    'tables_checked': 0,
                    'recommendations': [],
                    'sample_data': {}
                }
                
                # Check Jobs table
                report['tables_checked'] += 1
                jobs_count = db.query(JobDB).count()
                if jobs_count > 0:
                    recent_job = db.query(JobDB).order_by(JobDB.started_at.desc()).first()
                    if recent_job and recent_job.started_at:
                        tz_info = recent_job.started_at.tzinfo
                        report['sample_data']['jobs'] = {
                            'sample_timestamp': recent_job.started_at.isoformat(),
                            'has_timezone_info': tz_info is not None,
                            'is_utc': tz_info == timezone.utc if tz_info else False
                        }
                        if tz_info is None:
                            report['issues_found'] += 1
                            report['recommendations'].append("Jobs table contains naive timestamps (no timezone info)")
                
                # Check Operations table  
                report['tables_checked'] += 1
                ops_count = db.query(OperationDB).count()
                if ops_count > 0:
                    recent_op = db.query(OperationDB).order_by(OperationDB.started_at.desc()).first()
                    if recent_op and recent_op.started_at:
                        tz_info = recent_op.started_at.tzinfo
                        report['sample_data']['operations'] = {
                            'sample_timestamp': recent_op.started_at.isoformat(),
                            'has_timezone_info': tz_info is not None,
                            'is_utc': tz_info == timezone.utc if tz_info else False
                        }
                        if tz_info is None:
                            report['issues_found'] += 1
                            report['recommendations'].append("Operations table contains naive timestamps")
                
                # Check Logs table
                report['tables_checked'] += 1 
                logs_count = db.query(LogEntryDB).count()
                if logs_count > 0:
                    recent_log = db.query(LogEntryDB).order_by(LogEntryDB.timestamp.desc()).first()
                    if recent_log and recent_log.timestamp:
                        tz_info = recent_log.timestamp.tzinfo
                        report['sample_data']['logs'] = {
                            'sample_timestamp': recent_log.timestamp.isoformat(),
                            'has_timezone_info': tz_info is not None,
                            'is_utc': tz_info == timezone.utc if tz_info else False
                        }
                        if tz_info is None:
                            report['issues_found'] += 1
                            report['recommendations'].append("Logs table contains naive timestamps")
                
                if report['issues_found'] == 0:
                    report['message'] = f"All {report['tables_checked']} tables have proper timezone-aware timestamps"
                else:
                    report['status'] = 'warning'
                    report['message'] = f"Found {report['issues_found']} potential timezone issues"
                    report['recommendations'].append("Consider that SQLite stores datetimes as strings, so timezone info may not be preserved")
                    report['recommendations'].append("Ensure all new timestamps use datetime.utcnow() in the backend")
                
                return APIResponse(data=report, message="Timezone validation completed")
                
            except Exception as e:
                logger.error(f"Timezone validation failed: {e}")
                raise HTTPException(status_code=500, detail=f"Timezone validation failed: {str(e)}")

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
                                "timestamp": datetime.utcnow().isoformat()
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

        @self.app.get("/api/dev/stale-jobs")
        async def check_stale_jobs():
            """Check for jobs that would be considered stale by the timeout monitor"""
            try:
                from datetime import datetime, timedelta
                from timezone_utils import get_cutoff_datetime
                cutoff_time = get_cutoff_datetime(days=0, hours=1)
                
                running_jobs = await self.cached_job_service.get_jobs(
                    status="running", 
                    limit=1000
                )
                
                stale_jobs = []
                active_jobs = []
                
                for job_data in running_jobs:
                    job_id = job_data.get('job_id')
                    if not job_id:
                        continue
                        
                    last_activity = await self._get_job_last_activity(job_id, job_data)
                    
                    from timezone_utils import get_minutes_since, safe_datetime_compare
                    job_info = {
                        'job_id': job_id,
                        'repository': job_data.get('repository', 'Unknown'),
                        'job_type': job_data.get('job_type', 'Unknown'),
                        'last_activity': last_activity.isoformat() if last_activity else None,
                        'minutes_since_activity': get_minutes_since(last_activity)
                    }
                    
                    if last_activity and safe_datetime_compare(last_activity, cutoff_time):
                        stale_jobs.append(job_info)
                    else:
                        active_jobs.append(job_info)
                
                return APIResponse(data={
                    "stale_jobs": stale_jobs,
                    "active_jobs": active_jobs,
                    "total_running": len(running_jobs),
                    "stale_count": len(stale_jobs),
                    "active_count": len(active_jobs),
                    "timeout_threshold_hours": 1
                }, message=f"Found {len(stale_jobs)} stale jobs and {len(active_jobs)} active jobs")
                
            except Exception as e:
                logger.error(f"Failed to check stale jobs: {e}")
                return APIResponse(data={"error": str(e)}, message="Failed to check stale jobs")

        @self.app.post("/api/dev/force-timeout-check")
        async def force_timeout_check():
            """Manually trigger the job timeout check for testing"""
            try:
                from datetime import datetime, timedelta
                from timezone_utils import get_cutoff_datetime
                cutoff_time = get_cutoff_datetime(days=0, hours=1)
                
                running_jobs = await self.cached_job_service.get_jobs(
                    status="running", 
                    limit=1000
                )
                
                stale_jobs = []
                
                for job_data in running_jobs:
                    job_id = job_data.get('job_id')
                    if not job_id:
                        continue
                        
                    last_activity = await self._get_job_last_activity(job_id, job_data)
                    
                    from timezone_utils import safe_datetime_compare, get_minutes_since
                    if last_activity and safe_datetime_compare(last_activity, cutoff_time):
                        stale_jobs.append({
                            'job_id': job_id,
                            'last_activity': last_activity,
                            'repository': job_data.get('repository', 'Unknown'),
                            'job_type': job_data.get('job_type', 'Unknown'),
                            'stale_duration_minutes': get_minutes_since(last_activity)
                        })
                
                # Mark stale jobs as failed (same logic as the background task)
                failed_jobs = []
                errors = []
                
                for stale_job in stale_jobs:
                    try:
                        await self.cached_job_service.update_job_status(
                            stale_job['job_id'], 
                            "failed", 
                            error_details="Job timed out - No activity received for over 1 hour (manual check)"
                        )
                        
                        self._log_system_event('WARNING', 
                            f"Job {stale_job['job_id']} manually marked as failed due to timeout",
                            {
                                'system_event': 'job_timeout_manual',
                                'job_id': stale_job['job_id'],
                                'repository': stale_job['repository'],
                                'job_type': stale_job['job_type'],
                                'last_activity': stale_job['last_activity'].isoformat(),
                                'stale_duration_minutes': stale_job['stale_duration_minutes'],
                                'timeout_threshold_hours': 1
                            }
                        )
                        
                        failed_jobs.append(stale_job['job_id'])
                        
                    except Exception as e:
                        errors.append(f"Failed to mark job {stale_job['job_id']} as failed: {e}")
                
                return APIResponse(data={
                    "stale_jobs_found": len(stale_jobs),
                    "jobs_marked_failed": len(failed_jobs),
                    "failed_job_ids": failed_jobs,
                    "errors": errors
                }, message=f"Manually marked {len(failed_jobs)} stale jobs as failed")
                
            except Exception as e:
                logger.error(f"Failed to force timeout check: {e}")
                return APIResponse(data={"error": str(e)}, message="Failed to force timeout check")

        @self.app.get("/api/dev/scheduled-jobs/status")
        async def get_scheduled_jobs_status():
            """Get the status of all background scheduled jobs"""
            try:
                from datetime import datetime
                
                status = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "services": {}
                }
                
                logger.info("Starting scheduled jobs status check")
                
                # Health monitoring service status
                try:
                    logger.debug("Checking health monitoring service")
                    health_stats = await self.health_service.get_system_health()
                    db_stats = self.retention_service.get_database_stats()
                    
                    status["services"]["health_monitoring"] = {
                        "name": "Health Monitoring Service",
                        "enabled": True,
                        "status": "running",
                        "last_check": db_stats.get("last_health_check"),
                        "next_check": "Every 5 minutes",
                        "check_interval_minutes": 5,
                        "details": {
                            "overall_status": health_stats.get("status", "unknown"),
                            "services_checked": len(health_stats.get("services", {})),
                            "unhealthy_services": len([s for s in health_stats.get("services", {}).values() if s.get("status") not in ["healthy", "disabled", "configured"]])
                        }
                    }
                    logger.debug("Health monitoring service check completed successfully")
                except Exception as e:
                    logger.error(f"Health monitoring service error: {e}")
                    status["services"]["health_monitoring"] = {
                        "name": "Health Monitoring Service",
                        "enabled": True,
                        "status": "error",
                        "error": str(e)
                    }
                
                # Backup service status
                try:
                    logger.debug("Checking backup service")
                    retention_config = self.retention_service.get_retention_config()
                    db_stats = self.retention_service.get_database_stats()
                    
                    status["services"]["backup_service"] = {
                        "name": "Automatic Backup Service",
                        "enabled": retention_config.get("auto_backup_enabled", False),
                        "status": "running" if retention_config.get("auto_backup_enabled", False) else "disabled",
                        "last_backup": db_stats.get("last_backup"),
                        "next_backup": "Every 168 hours" if retention_config.get("auto_backup_enabled", False) else "Disabled",
                        "backup_interval_hours": retention_config.get("backup_schedule_hours", 168),
                        "details": {
                            "compression_enabled": retention_config.get("backup_compression", True),
                            "backup_count": db_stats.get("backup_count", 0),
                            "database_size_mb": db_stats.get("database_size_mb", 0)
                        }
                    }
                    logger.debug("Backup service check completed successfully")
                except Exception as e:
                    logger.error(f"Backup service error: {e}")
                    status["services"]["backup_service"] = {
                        "name": "Automatic Backup Service",
                        "enabled": False,
                        "status": "error",
                        "error": str(e)
                    }
                
                # Job timeout monitoring status
                try:
                    logger.debug("Checking job timeout monitoring service")
                    running_jobs_data = await self.cached_job_service.get_jobs(status="running", limit=1000)
                    from datetime import timedelta
                    from timezone_utils import get_cutoff_datetime, safe_datetime_compare
                    cutoff_time = get_cutoff_datetime(days=0, hours=1)
                    
                    stale_count = 0
                    for job_data in running_jobs_data:
                        job_id = job_data.get('job_id')
                        if job_id:
                            last_activity = await self._get_job_last_activity(job_id, job_data)
                            if last_activity and safe_datetime_compare(last_activity, cutoff_time):
                                stale_count += 1
                    
                    db_stats = self.retention_service.get_database_stats()
                    
                    status["services"]["job_timeout_monitoring"] = {
                        "name": "Job Timeout Monitoring",
                        "enabled": True,
                        "status": "running",
                        "last_check": db_stats.get("last_job_timeout_check"),
                        "next_check": "Every 10 minutes",
                        "check_interval_minutes": 10,
                        "details": {
                            "timeout_threshold_hours": 1,
                            "running_jobs_count": len(running_jobs_data),
                            "stale_jobs_count": stale_count
                        }
                    }
                    logger.debug("Job timeout monitoring service check completed successfully")
                except Exception as e:
                    logger.error(f"Job timeout monitoring service error: {e}")
                    status["services"]["job_timeout_monitoring"] = {
                        "name": "Job Timeout Monitoring",
                        "enabled": True,
                        "status": "error", 
                        "error": str(e)
                    }
                
                # Cleanup service status
                try:
                    logger.debug("Checking cleanup service")
                    retention_config = self.retention_service.get_retention_config()
                    db_stats = self.retention_service.get_database_stats()
                    
                    status["services"]["cleanup_service"] = {
                        "name": "Data Cleanup Service",
                        "enabled": retention_config.get("auto_cleanup_enabled", True),
                        "status": "running" if retention_config.get("auto_cleanup_enabled", True) else "disabled",
                        "last_cleanup": db_stats.get("last_cleanup"),
                        "next_cleanup": f"Every {retention_config.get('cleanup_schedule_hours', 24)} hours" if retention_config.get("auto_cleanup_enabled", True) else "Disabled",
                        "cleanup_interval_hours": retention_config.get("cleanup_schedule_hours", 24),
                        "details": {
                            "logs_retention_days": retention_config.get("logs_retention_days", 30),
                            "operations_retention_days": retention_config.get("operations_retention_days", 90),
                            "total_logs": db_stats.get("total_logs", 0),
                            "total_operations": db_stats.get("total_operations", 0)
                        }
                    }
                    logger.debug("Cleanup service check completed successfully")
                except Exception as e:
                    logger.error(f"Cleanup service error: {e}")
                    status["services"]["cleanup_service"] = {
                        "name": "Data Cleanup Service",
                        "enabled": False,
                        "status": "error",
                        "error": str(e)
                    }
                
                logger.info(f"Scheduled jobs status check completed. Found {len(status['services'])} services")
                return APIResponse(data=status, message="Retrieved scheduled jobs status")
                
            except Exception as e:
                logger.error(f"Failed to get scheduled jobs status: {e}")
                import traceback
                traceback.print_exc()
                from timezone_utils import utcnow_aware
                return APIResponse(data={"error": str(e), "services": {}, "timestamp": utcnow_aware().isoformat()}, message="Failed to get scheduled jobs status")

        @self.app.get("/api/dev/scheduled-jobs/simple-status")
        async def get_simple_scheduled_jobs_status():
            """Get a simple status of scheduled jobs for debugging"""
            try:
                from datetime import datetime
                
                # Simple fallback that always works
                status = {
                    "timestamp": datetime.utcnow().isoformat(),
                    "services": {
                        "health_monitoring": {
                            "name": "Health Monitoring Service",
                            "enabled": True,
                            "status": "running",
                            "last_check": "Unknown",
                            "next_check": "Every 5 minutes",
                            "check_interval_minutes": 5,
                            "details": {"note": "Basic service info"}
                        },
                        "backup_service": {
                            "name": "Automatic Backup Service", 
                            "enabled": False,
                            "status": "disabled",
                            "last_backup": "Unknown",
                            "next_backup": "Disabled",
                            "backup_interval_hours": 168,
                            "details": {"note": "Basic service info"}
                        },
                        "job_timeout_monitoring": {
                            "name": "Job Timeout Monitoring",
                            "enabled": True,
                            "status": "running",
                            "last_check": "Every 10 minutes", 
                            "next_check": "Every 10 minutes",
                            "check_interval_minutes": 10,
                            "details": {"note": "Basic service info"}
                        },
                        "cleanup_service": {
                            "name": "Data Cleanup Service",
                            "enabled": True,
                            "status": "running",
                            "last_cleanup": "Unknown",
                            "next_cleanup": "Every 24 hours",
                            "cleanup_interval_hours": 24,
                            "details": {"note": "Basic service info"}
                        }
                    }
                }
                
                return APIResponse(data=status, message="Retrieved simple scheduled jobs status")
                
            except Exception as e:
                logger.error(f"Failed to get simple scheduled jobs status: {e}")
                return APIResponse(data={"error": str(e)}, message="Failed to get simple scheduled jobs status")

        @self.app.post("/api/dev/scheduled-jobs/trigger/{service_name}")
        async def trigger_scheduled_job(service_name: str):
            """Manually trigger a specific scheduled job"""
            try:
                result = {"service": service_name, "triggered": False, "message": ""}
                
                if service_name == "health_monitoring":
                    # Force a health check
                    health_status = await self.health_service.get_system_health()
                    
                    # Update last health check timestamp
                    self.database_manager.set_system_setting("last_health_check_time", datetime.utcnow().isoformat())
                    
                    self._log_system_event('INFO', 
                        "Health monitoring manually triggered - System check completed",
                        {
                            'system_event': 'health_check_manual',
                            'overall_status': health_status.get('status'),
                            'services_checked': len(health_status.get('services', {}))
                        }
                    )
                    
                    result.update({
                        "triggered": True,
                        "message": f"Health check completed - System status: {health_status.get('status')}",
                        "details": health_status
                    })
                    
                elif service_name == "backup_service":
                    # Force an automatic backup (bypass schedule check for manual trigger)
                    backup_result = self.retention_service.perform_automatic_backup(force=True)
                    
                    if backup_result.get("success"):
                        result.update({
                            "triggered": True,
                            "message": backup_result.get("message", "Automatic backup completed (forced)"),
                            "details": backup_result
                        })
                    else:
                        # If automatic backup failed (e.g., disabled), fall back to manual backup
                        backup_result = self.retention_service.create_backup(compressed=True)
                        result.update({
                            "triggered": True,
                            "message": f"Manual backup created (automatic backup: {backup_result.get('reason', 'failed')})",
                            "details": backup_result
                        })
                    
                elif service_name == "job_timeout_monitoring":
                    # Force job timeout check (reuse existing endpoint logic)
                    from timezone_utils import get_cutoff_datetime, safe_datetime_compare
                    cutoff_time = get_cutoff_datetime(days=0, hours=1)
                    
                    running_jobs = await self.cached_job_service.get_jobs(status="running", limit=1000)
                    stale_jobs = []
                    
                    for job_data in running_jobs:
                        job_id = job_data.get('job_id')
                        if job_id:
                            last_activity = await self._get_job_last_activity(job_id, job_data)
                            if last_activity and safe_datetime_compare(last_activity, cutoff_time):
                                stale_jobs.append(job_id)
                    
                    # Mark stale jobs as failed
                    failed_count = 0
                    for job_id in stale_jobs:
                        try:
                            from models import JobStatus
                            await self.cached_job_service.update_job_status(
                                job_id, JobStatus.FAILED, 
                                error_details="Job timed out - No activity received for over 1 hour (manual trigger)"
                            )
                            failed_count += 1
                            logger.info(f"Manually marked stale job {job_id} as failed")
                        except Exception as e:
                            logger.error(f"Failed to mark job {job_id} as failed during manual timeout check: {e}")
                    
                    # Update last job timeout check timestamp
                    from timezone_utils import utcnow_aware
                    self.database_manager.set_system_setting("last_job_timeout_check_time", utcnow_aware().isoformat())
                    
                    result.update({
                        "triggered": True,
                        "message": f"Job timeout check completed - Marked {failed_count} stale jobs as failed",
                        "details": {
                            "stale_jobs_found": len(stale_jobs),
                            "jobs_marked_failed": failed_count,
                            "running_jobs_total": len(running_jobs)
                        }
                    })
                    
                elif service_name == "cleanup_service":
                    # Force cleanup
                    cleanup_result = self.retention_service.perform_cleanup(dry_run=False)
                    
                    # Note: cleanup service already updates last_cleanup_time in perform_cleanup()
                    result.update({
                        "triggered": True,
                        "message": f"Cleanup completed - Deleted {cleanup_result.get('total_deleted', 0)} records",
                        "details": cleanup_result
                    })
                    
                else:
                    result.update({
                        "triggered": False,
                        "message": f"Unknown service: {service_name}"
                    })
                
                return APIResponse(data=result, message=result["message"])
                
            except Exception as e:
                logger.error(f"Failed to trigger scheduled job {service_name}: {e}")
                return APIResponse(data={"error": str(e), "service": service_name, "triggered": False}, 
                                 message=f"Failed to trigger {service_name}")
    
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
                # Small delay to ensure cache service is fully ready
                await asyncio.sleep(0.1)
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
            
            # Start background monitoring tasks with error handling
            cleanup_task = None
            backup_task = None
            health_task = None
            job_timeout_task = None
            startup_logging_task = None
            
            try:
                cleanup_task = asyncio.create_task(self._cleanup_old_data())
            except Exception as e:
                logger.error(f"Failed to start cleanup task: {e}")
                
            try:
                backup_task = asyncio.create_task(self._backup_scheduler())
            except Exception as e:
                logger.error(f"Failed to start backup scheduler: {e}")
                
            try:
                health_task = asyncio.create_task(self._monitor_system_health())
            except Exception as e:
                logger.error(f"Failed to start system health monitoring: {e}")
                
            try:
                job_timeout_task = asyncio.create_task(self._monitor_job_timeouts())
            except Exception as e:
                logger.error(f"Failed to start job timeout monitoring: {e}")
            
            # Start health service background monitoring
            try:
                await self.health_service.start_background_monitoring()
            except Exception as e:
                logger.error(f"Failed to start health monitoring: {e}")
            
            # Create a task to log system startup after server is fully ready
            try:
                startup_logging_task = asyncio.create_task(self._log_system_startup_after_delay())
            except Exception as e:
                logger.error(f"Failed to create startup logging task: {e}")
            
            yield
            
            # Shutdown - start graceful task cancellation
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
            
            # Gracefully stop health service monitoring first
            try:
                await self.health_service.stop_background_monitoring()
                logger.info("Health service monitoring stopped")
            except Exception as e:
                logger.error(f"Failed to stop health monitoring: {e}")
            
            # Cancel background tasks gracefully
            tasks_to_cancel = [task for task in [cleanup_task, backup_task, health_task, job_timeout_task, startup_logging_task] if task is not None]
            for task in tasks_to_cancel:
                if not task.done():
                    task.cancel()
            
            # Wait for tasks to finish cancellation (with timeout)
            if tasks_to_cancel:
                try:
                    await asyncio.wait_for(
                        asyncio.gather(*tasks_to_cancel, return_exceptions=True), 
                        timeout=5.0
                    )
                except asyncio.TimeoutError:
                    logger.warning("Some background tasks did not cancel within timeout")
                except Exception as e:
                    pass  # Tasks cancelled successfully
            
            # Shutdown robust cache service
            try:
                await shutdown_robust_cache_service()
                logger.info("Robust cache service shutdown successfully")
            except Exception as e:
                logger.error(f"Failed to shutdown robust cache service: {e}")
            
            logger.info(f"{settings.app_name} stopped")
        
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
    
    def _configure_azure_devops_settings(self, repo):
        """Configure Azure DevOps settings for provider initialization"""
        from pr_agent.config_loader import get_settings
        settings = get_settings()
        
        # Parse organization from repository URL
        org_url = repo.url
        if 'dev.azure.com' in org_url:
            # Extract organization from URL like https://dev.azure.com/organization/project/_git/repo
            org_parts = org_url.split('/')
            if len(org_parts) >= 4:
                org_name = org_parts[3]
                org_url = f"https://dev.azure.com/{org_name}"
        elif 'visualstudio.com' in org_url:
            # Extract organization from URL like https://organization.visualstudio.com/project/_git/repo
            from urllib.parse import urlparse
            parsed_url = urlparse(org_url)
            # For visualstudio.com, the organization is the subdomain
            org_url = f"{parsed_url.scheme}://{parsed_url.netloc}"
        
        # Set Azure DevOps configuration in settings
        if not hasattr(settings, 'azure_devops'):
            settings.azure_devops = {}
        settings.azure_devops['org'] = org_url
        settings.azure_devops['pat'] = repo.azure_pat

    async def _test_github_token(self, repo):
        """Test GitHub token permissions"""
        import requests
        from datetime import datetime
        
        headers = {
            'Authorization': f'token {repo.github_token}',
            'Accept': 'application/vnd.github.v3+json',
            'User-Agent': 'PR-Agent-Dashboard'
        }
        
        # Parse repository from URL
        repo_parts = repo.url.replace('https://github.com/', '').replace('.git', '').split('/')
        if len(repo_parts) < 2:
            return {
                'success': False,
                'error': 'Invalid GitHub repository URL format',
                'details': {},
                'tested_at': datetime.utcnow().isoformat()
            }
        
        owner, repo_name = repo_parts[0], repo_parts[1]
        
        try:
            # Test 1: Get user info
            user_response = requests.get('https://api.github.com/user', headers=headers, timeout=10)
            
            # Test 2: Get repository info
            repo_response = requests.get(f'https://api.github.com/repos/{owner}/{repo_name}', headers=headers, timeout=10)
            
            # Test 3: Check actions permissions
            actions_response = requests.get(f'https://api.github.com/repos/{owner}/{repo_name}/actions/runs?per_page=1', headers=headers, timeout=10)
            
            # Analyze results
            permissions = []
            issues = []
            
            if user_response.status_code == 200:
                user_data = user_response.json()
                permissions.append("✅ User authentication successful")
            else:
                issues.append(f"❌ User authentication failed: {user_response.status_code}")
            
            if repo_response.status_code == 200:
                repo_data = repo_response.json()
                permissions.append("✅ Repository access granted")
                
                # Check specific permissions
                if repo_data.get('permissions', {}).get('admin'):
                    permissions.append("✅ Admin permissions")
                elif repo_data.get('permissions', {}).get('push'):
                    permissions.append("✅ Push permissions")
                elif repo_data.get('permissions', {}).get('pull'):
                    permissions.append("✅ Pull permissions")
                else:
                    issues.append("⚠️ Limited repository permissions")
                    
            else:
                issues.append(f"❌ Repository access denied: {repo_response.status_code}")
            
            if actions_response.status_code == 200:
                permissions.append("✅ Actions read access")
            elif actions_response.status_code == 404:
                permissions.append("⚠️ Actions not enabled or no runs found")
            else:
                issues.append(f"❌ Actions access denied: {actions_response.status_code}")
            
            # Check rate limit
            rate_limit_remaining = user_response.headers.get('X-RateLimit-Remaining', 'Unknown')
            rate_limit_reset = user_response.headers.get('X-RateLimit-Reset', 'Unknown')
            
            return {
                'success': len(issues) == 0,
                'permissions': permissions,
                'issues': issues,
                'details': {
                    'username': user_data.get('login') if user_response.status_code == 200 else None,
                    'rate_limit_remaining': rate_limit_remaining,
                    'rate_limit_reset': rate_limit_reset,
                    'repository_accessible': repo_response.status_code == 200,
                    'actions_accessible': actions_response.status_code == 200
                },
                'tested_at': datetime.utcnow().isoformat()
            }
            
        except requests.exceptions.RequestException as e:
            return {
                'success': False,
                'error': f'Network error: {str(e)}',
                'details': {},
                'tested_at': datetime.utcnow().isoformat()
            }

    async def _test_azure_devops_token(self, repo):
        """Test Azure DevOps PAT permissions"""
        import requests
        import base64
        from datetime import datetime
        from urllib.parse import urlparse
        
        logger.info(f"Testing Azure DevOps token for repository: {repo.name} ({repo.url})")
        
        # Parse Azure DevOps URL
        try:
            parsed_url = urlparse(repo.url)
            logger.info(f"Parsed URL: netloc={parsed_url.netloc}, path={parsed_url.path}")
            
            if 'dev.azure.com' in parsed_url.netloc:
                # Format: https://dev.azure.com/organization/project/_git/repo
                path_parts = parsed_url.path.strip('/').split('/')
                logger.info(f"dev.azure.com path parts: {path_parts}")
                if len(path_parts) >= 3:
                    organization = path_parts[0]
                    project = path_parts[1]
                    repo_name = path_parts[3] if len(path_parts) > 3 else path_parts[2]
                else:
                    raise ValueError("Invalid Azure DevOps URL format")
            elif 'visualstudio.com' in parsed_url.netloc:
                # Format: https://organization.visualstudio.com/project/_git/repo
                organization = parsed_url.netloc.split('.')[0]
                path_parts = parsed_url.path.strip('/').split('/')
                logger.info(f"visualstudio.com path parts: {path_parts}")
                if len(path_parts) >= 3:
                    project = path_parts[0]
                    repo_name = path_parts[2]
                else:
                    raise ValueError("Invalid Azure DevOps URL format")
            else:
                raise ValueError("Unrecognized Azure DevOps URL format")
                
            logger.info(f"Parsed Azure DevOps details: org={organization}, project={project}, repo={repo_name}")
            
        except Exception as e:
            logger.error(f"Failed to parse Azure DevOps URL: {e}")
            return {
                'success': False,
                'error': f'Invalid Azure DevOps URL: {str(e)}',
                'details': {},
                'tested_at': datetime.utcnow().isoformat()
            }
        
        # Setup authentication
        auth_string = base64.b64encode(f':{repo.azure_pat}'.encode()).decode()
        headers = {
            'Authorization': f'Basic {auth_string}',
            'Accept': 'application/json',
            'User-Agent': 'PR-Agent-Dashboard'
        }
        
        try:
            permissions = []
            issues = []
            
            # Test 1: Get user profile
            if 'dev.azure.com' in repo.url:
                profile_url = f'https://app.vssps.visualstudio.com/_apis/profile/profiles/me?api-version=6.0'
                org_url = f'https://dev.azure.com/{organization}'
            else:
                profile_url = f'https://app.vssps.visualstudio.com/_apis/profile/profiles/me?api-version=6.0'
                org_url = f'https://{organization}.visualstudio.com'
            
            logger.info(f"Testing user profile: {profile_url}")
            profile_response = requests.get(profile_url, headers=headers, timeout=10)
            logger.info(f"Profile response: {profile_response.status_code}")
            
            # Test 2: Get project info
            project_url = f'{org_url}/_apis/projects/{project}?api-version=6.0'
            logger.info(f"Testing project access: {project_url}")
            project_response = requests.get(project_url, headers=headers, timeout=10)
            logger.info(f"Project response: {project_response.status_code}")
            
            # Test 3: Get repository info
            repo_url = f'{org_url}/{project}/_apis/git/repositories/{repo_name}?api-version=6.0'
            logger.info(f"Testing repository access: {repo_url}")
            repo_response = requests.get(repo_url, headers=headers, timeout=10)
            logger.info(f"Repository response: {repo_response.status_code}")
            
            # Test 4: Get pipelines (if accessible)
            pipelines_url = f'{org_url}/{project}/_apis/pipelines?api-version=6.0-preview.1'
            logger.info(f"Testing pipelines access: {pipelines_url}")
            pipelines_response = requests.get(pipelines_url, headers=headers, timeout=10)
            logger.info(f"Pipelines response: {pipelines_response.status_code}")
            
            # Helper function to get detailed error info
            def get_error_details(response):
                try:
                    if response.status_code >= 400:
                        error_data = response.json()
                        return error_data.get('message', f'HTTP {response.status_code}')
                except:
                    return f'HTTP {response.status_code}'
                return None
            
            # Analyze results with detailed error logging
            profile_data = None
            if profile_response.status_code == 200:
                profile_data = profile_response.json()
                permissions.append("✅ User authentication successful")
                logger.info(f"User profile success: {profile_data.get('displayName', 'Unknown')}")
            else:
                error_detail = get_error_details(profile_response)
                # Profile failure is not critical if other endpoints work
                permissions.append(f"⚠️ User profile unavailable: {error_detail}")
                logger.warning(f"User profile failed (non-critical): {error_detail}")
                if profile_response.status_code == 401:
                    logger.warning("Profile endpoint requires different permissions (this is normal for some PAT scopes)")
                elif profile_response.status_code == 403:
                    logger.warning("Profile endpoint access denied (this is normal for some PAT scopes)")
            
            if project_response.status_code == 200:
                permissions.append("✅ Project access granted")
                logger.info(f"Project access success for: {project}")
            else:
                error_detail = get_error_details(project_response)
                issues.append(f"❌ Project access denied: {error_detail}")
                logger.error(f"Project access failed: {error_detail}")
                if project_response.status_code == 404:
                    logger.error(f"Project '{project}' not found or no access")
            
            if repo_response.status_code == 200:
                permissions.append("✅ Repository access granted")
                logger.info(f"Repository access success for: {repo_name}")
            else:
                error_detail = get_error_details(repo_response)
                issues.append(f"❌ Repository access denied: {error_detail}")
                logger.error(f"Repository access failed: {error_detail}")
                if repo_response.status_code == 404:
                    logger.error(f"Repository '{repo_name}' not found or no access")
            
            if pipelines_response.status_code == 200:
                permissions.append("✅ Pipelines read access")
                logger.info("Pipelines access success")
            elif pipelines_response.status_code == 403:
                permissions.append("⚠️ Limited pipeline permissions")
                logger.warning("Limited pipeline permissions")
            else:
                error_detail = get_error_details(pipelines_response)
                issues.append(f"❌ Pipelines access denied: {error_detail}")
                logger.error(f"Pipelines access failed: {error_detail}")
            
            # Token is considered successful if core functionality works (project and repository access)
            core_functionality_works = (project_response.status_code == 200 and 
                                       repo_response.status_code == 200)
            
            result = {
                'success': core_functionality_works and len(issues) == 0,
                'permissions': permissions,
                'issues': issues,
                'details': {
                    'organization': organization,
                    'project': project,
                    'repository': repo_name,
                    'username': profile_data.get('displayName') if profile_data else None,
                    'project_accessible': project_response.status_code == 200,
                    'repository_accessible': repo_response.status_code == 200,
                    'pipelines_accessible': pipelines_response.status_code == 200
                },
                'tested_at': datetime.utcnow().isoformat()
            }
            
            logger.info(f"Token test result: success={result['success']}, issues={len(issues)}")
            if issues:
                logger.warning(f"Token test issues: {issues}")
            
            return result
            
        except requests.exceptions.RequestException as e:
            error_msg = f'Network error: {str(e)}'
            logger.error(f"Azure DevOps token test failed: {error_msg}")
            return {
                'success': False,
                'error': error_msg,
                'details': {},
                'tested_at': datetime.utcnow().isoformat()
            }

    def _log_system_event(self, level: str, message: str, context: dict = None):
        """Log system events to the dashboard logging system"""
        try:
            import requests
            from datetime import datetime
            from timezone_utils import utcnow_aware, format_datetime_for_db
            
            # Create a system log entry
            log_data = {
                'timestamp': format_datetime_for_db(utcnow_aware()),
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
                        from timezone_utils import parse_datetime_safe, utcnow_aware
                        last_cleanup_dt = parse_datetime_safe(last_cleanup)
                        if last_cleanup_dt:
                            next_cleanup_dt = last_cleanup_dt + timedelta(hours=schedule_hours)
                            should_cleanup = utcnow_aware() >= next_cleanup_dt
                        else:
                            logger.warning(f"Could not parse last cleanup time: {last_cleanup}")
                            should_cleanup = True  # If we can't parse, do cleanup to be safe
                    except Exception as e:
                        logger.warning(f"Could not parse last cleanup time: {e}")
                        should_cleanup = True  # If we can't parse, do cleanup to be safe
                
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
                
                # Check for due backups
                
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
                
                # Update last health check timestamp
                self.database_manager.set_system_setting("last_health_check_time", datetime.utcnow().isoformat())
                
                # Log any issues
                overall_status = health.get("overall", {}).get("status", "unknown")
                if overall_status != "healthy":
                    logger.warning(f"System health degraded: {overall_status}")
                    
                    # Check individual services (exclude 'overall' from service checks)
                    for service_name, service_health in health.items():
                        if service_name == "overall":
                            continue
                        service_status = service_health.get("status", "unknown")
                        if service_status not in ["healthy", "disabled", "configured"]:
                            logger.warning(f"Service {service_name} status: {service_status}")
                
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
                    "Background services started - Cleanup, backup, health monitoring, and job timeout monitoring active",
                    {
                        'system_event': 'background_services_started',
                        'services': ['cleanup_scheduler', 'backup_scheduler', 'health_monitor', 'job_timeout_monitor']
                    }
                )
                logger.info("Logged background services startup")
            except Exception as e:
                logger.warning(f"Failed to log background services start: {e}")
                
        except asyncio.CancelledError:
            logger.info("System startup logging task cancelled")
        except Exception as e:
            logger.error(f"Error in system startup logging: {e}")

    async def _monitor_job_timeouts(self):
        """Monitor jobs for timeout and automatically mark stale jobs as failed"""
        while True:
            try:
                await asyncio.sleep(600)  # Check every 10 minutes
                
                # Get current time and calculate 1 hour ago threshold
                from datetime import datetime, timedelta
                from timezone_utils import get_cutoff_datetime
                cutoff_time = get_cutoff_datetime(days=0, hours=1)
                
                # Check for stale running jobs using the cache service
                try:
                    running_jobs = await self.cached_job_service.get_jobs(
                        status="running", 
                        limit=1000  # Check all running jobs
                    )
                    
                    stale_jobs = []
                    
                    for job_data in running_jobs:
                        job_id = job_data.get('job_id')
                        if not job_id:
                            continue
                            
                        # Get the most recent activity timestamp for this job
                        last_activity = await self._get_job_last_activity(job_id, job_data)
                        
                        from timezone_utils import safe_datetime_compare, get_minutes_since
                        if last_activity and safe_datetime_compare(last_activity, cutoff_time):
                            stale_jobs.append({
                                'job_id': job_id,
                                'last_activity': last_activity,
                                'repository': job_data.get('repository', 'Unknown'),
                                'job_type': job_data.get('job_type', 'Unknown'),
                                'stale_duration_minutes': get_minutes_since(last_activity)
                            })
                    
                    # Mark stale jobs as failed
                    if stale_jobs:
                        logger.warning(f"Found {len(stale_jobs)} stale jobs to mark as failed")
                        
                        for stale_job in stale_jobs:
                            try:
                                # Mark job as failed
                                from models import JobStatus
                                await self.cached_job_service.update_job_status(
                                    stale_job['job_id'], 
                                    JobStatus.FAILED, 
                                    error_details="Job timed out - No activity received for over 1 hour"
                                )
                                
                                # Log the timeout action
                                self._log_system_event('WARNING', 
                                    f"Job {stale_job['job_id']} automatically marked as failed due to timeout",
                                    {
                                        'system_event': 'job_timeout',
                                        'job_id': stale_job['job_id'],
                                        'repository': stale_job['repository'],
                                        'job_type': stale_job['job_type'],
                                        'last_activity': stale_job['last_activity'].isoformat(),
                                        'stale_duration_minutes': stale_job['stale_duration_minutes'],
                                        'timeout_threshold_hours': 1
                                    }
                                )
                                
                                logger.info(f"Marked stale job {stale_job['job_id']} as failed "
                                          f"(idle for {stale_job['stale_duration_minutes']} minutes)")
                                
                            except Exception as e:
                                logger.error(f"Failed to mark job {stale_job['job_id']} as failed: {e}")
                                
                        # Send notification about timeout actions if notification service is available
                        if hasattr(self, 'notification_service') and self.notification_service:
                            try:
                                await self.notification_service.send_notification(
                                    event_type="job_timeout",
                                    message=f"Automatically marked {len(stale_jobs)} stale jobs as failed",
                                    context={
                                        'stale_jobs_count': len(stale_jobs),
                                        'timeout_threshold_hours': 1,
                                        'jobs': [job['job_id'] for job in stale_jobs[:5]]  # First 5 job IDs
                                    }
                                )
                            except Exception as e:
                                logger.debug(f"Failed to send timeout notification: {e}")
                    else:
                        logger.debug("Job timeout monitor: No stale jobs found")
                    
                    # Update last job timeout check timestamp (regardless of whether stale jobs were found)
                    self.database_manager.set_system_setting("last_job_timeout_check_time", datetime.utcnow().isoformat())
                        
                except Exception as e:
                    logger.error(f"Error during job timeout check: {e}")
                    
            except asyncio.CancelledError:
                logger.info("Job timeout monitoring task cancelled")
                break
            except Exception as e:
                logger.error(f"Unexpected error in job timeout monitoring: {e}")
                # Continue running even after errors
                await asyncio.sleep(300)  # Wait 5 minutes before retrying

    async def _get_job_last_activity(self, job_id: str, job_data: dict) -> datetime:
        """Get the most recent activity timestamp for a job considering job updates, operations, and logs"""
        try:
            from datetime import datetime
            from timezone_utils import parse_datetime_safe, ensure_timezone_aware, safe_datetime_compare
            
            # Start with job's own last_updated timestamp
            job_last_updated = job_data.get('last_updated')
            last_activity = None
            
            if job_last_updated:
                if isinstance(job_last_updated, str):
                    last_activity = parse_datetime_safe(job_last_updated)
                elif isinstance(job_last_updated, datetime):
                    last_activity = ensure_timezone_aware(job_last_updated)
            
            # Check latest operation activity
            try:
                operations = await self.cached_job_service.get_operations(job_id=job_id, limit=10)
                for operation in operations:
                    op_last_updated = operation.get('last_updated')
                    if op_last_updated:
                        if isinstance(op_last_updated, str):
                            op_timestamp = parse_datetime_safe(op_last_updated)
                        elif isinstance(op_last_updated, datetime):
                            op_timestamp = ensure_timezone_aware(op_last_updated)
                        else:
                            continue
                            
                        if op_timestamp and (last_activity is None or safe_datetime_compare(last_activity, op_timestamp)):
                            last_activity = op_timestamp
            except Exception as e:
                logger.debug(f"Error checking operation activity for job {job_id}: {e}")
            
            # Check latest log activity  
            try:
                logs = await self.cached_job_service.get_logs(job_id=job_id, limit=5)
                for log in logs:
                    log_timestamp = log.get('timestamp')
                    if log_timestamp:
                        if isinstance(log_timestamp, str):
                            log_dt = parse_datetime_safe(log_timestamp)
                        elif isinstance(log_timestamp, datetime):
                            log_dt = ensure_timezone_aware(log_timestamp)
                        else:
                            continue
                            
                        if log_dt and (last_activity is None or safe_datetime_compare(last_activity, log_dt)):
                            last_activity = log_dt
            except Exception as e:
                logger.debug(f"Error checking log activity for job {job_id}: {e}")
            
            # If no activity found, use job's started_at as fallback
            if last_activity is None:
                job_started_at = job_data.get('started_at')
                if job_started_at:
                    if isinstance(job_started_at, str):
                        last_activity = parse_datetime_safe(job_started_at)
                    elif isinstance(job_started_at, datetime):
                        last_activity = ensure_timezone_aware(job_started_at)
            
            return last_activity
            
        except Exception as e:
            logger.error(f"Error determining last activity for job {job_id}: {e}")
            return None
    
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