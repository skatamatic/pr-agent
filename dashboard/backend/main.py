from fastapi import FastAPI, HTTPException, WebSocket, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import asyncio
import logging
from datetime import datetime

# Import configuration and database
from config import settings
from models import get_db, APIResponse, ConfigUpdate, Repository, RepositoryCreate, RepositoryUpdate
from websocket_manager import WebSocketManager

# Import services (Dependency Inversion Principle)
from services.health_service import HealthService
from services.metrics_service import MetricsService
from services.operation_service import OperationService, LogService
from services.config_service import ConfigService
from services.repository_service import RepositoryService

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.log_level),
    format=settings.log_format
)
logger = logging.getLogger(__name__)


class DashboardApplication:
    """Main application class following Single Responsibility Principle"""
    
    def __init__(self):
        self.app = FastAPI(
            title=settings.app_name,
            description="API for monitoring PR Agent operations and logs",
            version="1.0.0",
            debug=settings.debug
        )
        
        # Initialize services (Dependency Injection)
        self.health_service = HealthService()
        self.metrics_service = MetricsService()
        self.operation_service = OperationService()
        self.log_service = LogService()
        self.config_service = ConfigService()
        self.repository_service = RepositoryService()
        self.websocket_manager = WebSocketManager()
        
        # Setup application
        self._setup_middleware()
        self._setup_routes()
        self._setup_background_tasks()
    
    def _setup_middleware(self):
        """Configure CORS and other middleware"""
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    
    def _setup_routes(self):
        """Setup all API routes using service methods"""
        
        # Health endpoints
        @self.app.get("/api/health")
        async def health_check():
            return await self.health_service.get_system_health()
        
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
        
        # Operations endpoints
        @self.app.get("/api/operations")
        async def get_operations(
            limit: int = 100,
            status: Optional[str] = None,
            repo: Optional[str] = None,
            db: Session = Depends(get_db)
        ):
            return await self.operation_service.get_operations(db, limit, status, repo)
        
        @self.app.get("/api/operations/{operation_id}")
        async def get_operation(operation_id: str, db: Session = Depends(get_db)):
            operation = await self.operation_service.get_operation(db, operation_id)
            if not operation:
                raise HTTPException(status_code=404, detail="Operation not found")
            return APIResponse(data=operation)
        
        # Logs endpoints
        @self.app.get("/api/logs")
        async def get_logs(
            limit: int = 1000,
            level: Optional[str] = None,
            search: Optional[str] = None,
            repo: Optional[str] = None,
            db: Session = Depends(get_db)
        ):
            return await self.log_service.get_logs(db, limit, level, search, repo)
        
        @self.app.get("/api/logs/operation/{operation_id}")
        async def get_logs_by_operation(operation_id: str, db: Session = Depends(get_db)):
            return await self.log_service.get_logs_by_operation(db, operation_id)
        
        # Log ingestion endpoints
        @self.app.post("/logs/immediate")
        async def receive_immediate_log(log_data: dict, db: Session = Depends(get_db)):
            try:
                log_entry = await self.log_service.create_log_entry(db, log_data)
                
                # Update operation status if needed
                if log_data.get('status'):
                    await self.operation_service.update_operation_status(db, log_data)
                
                # Broadcast to WebSocket clients
                await self.websocket_manager.broadcast({
                    "type": "log",
                    "data": {
                        "id": log_entry.id,
                        "timestamp": log_data.get('timestamp'),
                        "level": log_data.get('level'),
                        "message": log_data.get('message'),
                        "status": log_data.get('status'),
                        "severity": "high" if log_data.get('level') in ["ERROR", "CRITICAL"] else "normal"
                    }
                })
                
                return {"status": "received", "id": log_entry.id}
                
            except Exception as e:
                logger.error(f"Failed to process immediate log: {e}")
                raise HTTPException(status_code=500, detail=f"Failed to process log: {str(e)}")
        
        @self.app.post("/logs/batch")
        async def receive_batch_logs(batch_data: dict, db: Session = Depends(get_db)):
            try:
                logs = batch_data.get('logs', [])
                received_logs = await self.log_service.process_batch_logs(db, logs)
                
                # Update operations for logs with status
                for log_data in logs:
                    if log_data.get('status'):
                        await self.operation_service.update_operation_status(db, log_data)
                
                # Broadcast to WebSocket clients
                await self.websocket_manager.broadcast({
                    "type": "logs_batch",
                    "data": [{"id": log.id, "message": log.message} for log in received_logs]
                })
                
                return {"status": "received", "count": len(received_logs)}
                
            except Exception as e:
                logger.error(f"Failed to process batch logs: {e}")
                raise HTTPException(status_code=500, detail="Failed to process logs")
        
        # Metrics endpoints
        @self.app.get("/api/status/realtime")
        async def get_realtime_status(db: Session = Depends(get_db)):
            return await self.metrics_service.get_realtime_status(db)
        
        @self.app.get("/api/system/alerts")
        async def get_system_alerts(db: Session = Depends(get_db)):
            alerts = await self.metrics_service.get_system_alerts(db)
            return APIResponse(data=alerts)
        
        @self.app.get("/api/system/performance")
        async def get_system_performance(db: Session = Depends(get_db)):
            performance = await self.metrics_service.get_performance_metrics(db)
            return APIResponse(data=performance)
        
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
        
        @self.app.get("/api/repositories/{repo_id}")
        async def get_repository(repo_id: int, db: Session = Depends(get_db)):
            repository = await self.repository_service.get_repository(db, repo_id)
            if not repository:
                raise HTTPException(status_code=404, detail="Repository not found")
            return APIResponse(data=repository)
        
        @self.app.put("/api/repositories/{repo_id}")
        async def update_repository(repo_id: int, repo_update: RepositoryUpdate, db: Session = Depends(get_db)):
            try:
                repository = await self.repository_service.update_repository(db, repo_id, repo_update)
                if not repository:
                    raise HTTPException(status_code=404, detail="Repository not found")
                return APIResponse(data=repository, message="Repository updated successfully")
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
        
        @self.app.get("/api/repositories/names")
        async def get_repository_names(active_only: bool = True, db: Session = Depends(get_db)):
            names = await self.repository_service.get_repository_names(db, active_only)
            return APIResponse(data=names)
        
        # Developer endpoints (Open/Closed Principle - easily extensible)
        if settings.developer_mode:
            self._setup_developer_routes()
        
        # WebSocket endpoint
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            await self.websocket_manager.connect(websocket)
            try:
                while True:
                    await asyncio.sleep(30)
                    await websocket.send_json({
                        "type": "ping", 
                        "timestamp": datetime.utcnow().isoformat()
                    })
            except Exception as e:
                logger.error(f"WebSocket error: {e}")
            finally:
                self.websocket_manager.disconnect(websocket)
    
    def _setup_developer_routes(self):
        """Setup developer-only routes (Interface Segregation Principle)"""
        
        @self.app.post("/api/dev/generate-test-data")
        async def generate_test_data():
            from test_data import generate_test_data
            result = await generate_test_data()
            
            if result["status"] == "success":
                return APIResponse(data=result["data"], message=result["message"])
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
            from test_data import clear_all_data
            result = await clear_all_data()
            
            if result["status"] == "success":
                return APIResponse(data={}, message=result["message"])
            else:
                raise HTTPException(status_code=500, detail=result["message"])
    
    def _setup_background_tasks(self):
        """Setup background monitoring tasks using modern lifespan events"""
        from contextlib import asynccontextmanager
        
        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # Startup
            logger.info(f"{settings.app_name} started")
            if settings.developer_mode:
                logger.info("Developer mode enabled")
                
            # Initialize database with schema updates
            try:
                from database import initialize_database
                initialize_database()
                logger.info("Database initialized successfully")
            except Exception as e:
                logger.error(f"Database initialization failed: {e}")
                # Continue anyway, the fallback in models.py should handle it
            
            # Start background monitoring tasks
            cleanup_task = asyncio.create_task(self._cleanup_old_data())
            health_task = asyncio.create_task(self._monitor_system_health())
            
            yield
            
            # Shutdown
            logger.info(f"{settings.app_name} stopped")
            cleanup_task.cancel()
            health_task.cancel()
        
        # Apply lifespan to the app
        self.app.router.lifespan_context = lifespan
    
    async def _cleanup_old_data(self):
        """Background task to cleanup old data"""
        while True:
            try:
                await asyncio.sleep(3600)  # Run every hour
                
                from database import SessionLocal
                from models import OperationDB, LogEntryDB
                from datetime import timedelta
                
                db = SessionLocal()
                try:
                    # Delete operations older than 30 days
                    cutoff_date = datetime.utcnow() - timedelta(days=30)
                    old_ops = db.query(OperationDB).filter(
                        OperationDB.completed_at < cutoff_date,
                        OperationDB.status.in_(["completed", "failed"])
                    ).count()
                    
                    if old_ops > 0:
                        db.query(OperationDB).filter(
                            OperationDB.completed_at < cutoff_date,
                            OperationDB.status.in_(["completed", "failed"])
                        ).delete()
                        
                        # Also cleanup old logs
                        old_logs = db.query(LogEntryDB).filter(
                            LogEntryDB.timestamp < cutoff_date
                        ).count()
                        
                        if old_logs > 100:  # Keep at least 100 logs
                            db.query(LogEntryDB).filter(
                                LogEntryDB.timestamp < cutoff_date
                            ).delete()
                        
                        db.commit()
                        logger.info(f"Cleaned up {old_ops} old operations and {old_logs} old logs")
                        
                finally:
                    db.close()
                    
            except Exception as e:
                logger.error(f"Error in cleanup task: {e}")
    
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