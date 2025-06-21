"""
Health Service - Responsible for system health monitoring and checks
Follows Single Responsibility Principle
"""
import aiohttp
import toml
from datetime import datetime
from pathlib import Path
from typing import Dict, Any
from config import settings


class HealthService:
    """Service for monitoring system health and external dependencies"""
    
    def __init__(self):
        self.last_check = None
        self.cached_results = {}
    
    async def get_system_health(self) -> Dict[str, Any]:
        """Get comprehensive system health status"""
        health_status = {
            "status": "healthy",
            "timestamp": datetime.utcnow().isoformat(),
            "version": "1.0.0",
            "developer_mode": settings.developer_mode,
            "services": {}
        }
        
        # Check all services
        services_checks = [
            self._check_database(),
            self._check_pr_agent_config(),
            self._check_context_service()
        ]
        
        for service_result in services_checks:
            service_name, service_health = await service_result
            health_status["services"][service_name] = service_health
            
            # Update overall status based on service health
            service_status = service_health["status"]
            
            # Critical services that affect overall health
            if service_status in ["unhealthy", "error"]:
                health_status["status"] = "unhealthy"
            elif service_status in ["unreachable", "misconfigured"] and health_status["status"] == "healthy":
                health_status["status"] = "degraded"
            elif service_status == "unavailable" and service_name != "pr_agent_config" and health_status["status"] == "healthy":
                # Context service unavailable when enabled should degrade health
                health_status["status"] = "degraded"
        
        return health_status
    
    async def _check_database(self) -> tuple[str, Dict[str, Any]]:
        """Check database connectivity"""
        try:
            # This would be injected in a real implementation
            from database import SessionLocal
            from sqlalchemy import text
            
            db = SessionLocal()
            try:
                db.execute(text("SELECT 1"))
                return "database", {
                    "status": "healthy",
                    "type": "sqlite",
                    "url": str(settings.database_url).replace("sqlite:///", ""),
                    "last_check": datetime.utcnow().isoformat()
                }
            finally:
                db.close()
                
        except Exception as e:
            return "database", {
                "status": "unhealthy",
                "error": str(e),
                "last_check": datetime.utcnow().isoformat()
            }
    
    async def _check_pr_agent_config(self) -> tuple[str, Dict[str, Any]]:
        """Check PR-Agent configuration file accessibility"""
        try:
            # Handle case where config path might be None
            config_path = getattr(settings, 'pr_agent_config_path', None)
            if not config_path:
                return "pr_agent_config", {
                    "status": "unavailable",
                    "error": "PR-Agent config path not configured",
                    "last_check": datetime.utcnow().isoformat()
                }
            
            config_exists = config_path.exists()
            config_readable = config_path.is_file() if config_exists else False
            
            # Additional debugging info
            status_info = {
                "status": "healthy" if config_exists and config_readable else "unavailable",
                "path": str(settings.pr_agent_config_path),
                "exists": config_exists,
                "readable": config_readable,
                "last_check": datetime.utcnow().isoformat()
            }
            
            # If healthy, try to read a bit of the config to ensure it's valid
            if config_exists and config_readable:
                try:
                    with open(settings.pr_agent_config_path, 'r') as f:
                        config = toml.load(f)
                        status_info["sections"] = list(config.keys())[:5]  # First 5 sections
                        status_info["valid_toml"] = True
                except Exception as read_error:
                    status_info["status"] = "unhealthy"
                    status_info["error"] = f"Config file exists but cannot be read: {str(read_error)}"
                    status_info["valid_toml"] = False
            
            return "pr_agent_config", status_info
            
        except Exception as e:
            return "pr_agent_config", {
                "status": "error",
                "error": str(e),
                "path": str(getattr(settings, 'pr_agent_config_path', 'Unknown')),
                "last_check": datetime.utcnow().isoformat()
            }
    
    async def _check_context_service(self) -> tuple[str, Dict[str, Any]]:
        """Check if the C# context service is accessible"""
        try:
            # Use ConfigService to get the proper merged configuration
            from services.config_service import ConfigService
            config_service = ConfigService()
            config = await config_service.get_config()
            
            # Check if context service is enabled
            context_config = config.get('csharp_code_context_service', {})
            context_enabled = context_config.get('enabled', False)
            
            if not context_enabled:
                return "context_service", {
                    "status": "disabled",
                    "message": "Context service is disabled in configuration",
                    "last_check": datetime.utcnow().isoformat()
                }
            
            # If enabled, try to ping the service (if URL is configured)  
            service_url = context_config.get('url')
            if service_url and service_url.strip():
                try:
                    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=5)) as session:
                        # Try to ping both /health and base URL endpoints
                        health_urls = [f"{service_url.rstrip('/')}/health", f"{service_url.rstrip('/')}/"]
                        
                        for url in health_urls:
                            try:
                                async with session.get(url) as response:
                                    if response.status == 200:
                                        return "context_service", {
                                            "status": "healthy",
                                            "url": service_url,
                                            "enabled": True,
                                            "endpoint": url,
                                            "response_time": response.headers.get('X-Response-Time', 'N/A'),
                                            "last_check": datetime.utcnow().isoformat()
                                        }
                                    elif response.status in [404, 405]:
                                        # Service is running but endpoint doesn't exist - still healthy
                                        continue
                            except aiohttp.ClientError:
                                continue
                        
                        # If we get here, none of the endpoints worked
                        return "context_service", {
                            "status": "unreachable",
                            "url": service_url,
                            "enabled": True,
                            "error": "Service is not responding on any known endpoint",
                            "last_check": datetime.utcnow().isoformat()
                        }
                        
                except Exception as e:
                    return "context_service", {
                        "status": "unreachable",
                        "url": service_url,
                        "enabled": True,
                        "error": f"Connection failed: {str(e)}",
                        "last_check": datetime.utcnow().isoformat()
                    }
            else:
                return "context_service", {
                    "status": "misconfigured",
                    "enabled": True,
                    "error": "Context service is enabled but no URL configured or URL is empty",
                    "last_check": datetime.utcnow().isoformat()
                }
                
        except Exception as e:
            return "context_service", {
                "status": "error",
                "error": str(e),
                "last_check": datetime.utcnow().isoformat()
            }
    
    async def get_simple_status(self) -> Dict[str, Any]:
        """Get simple system status for quick health checks"""
        try:
            from database import SessionLocal
            from sqlalchemy import text
            from models import OperationDB
            
            # Quick database check
            db = SessionLocal()
            try:
                db.execute(text("SELECT 1"))
                
                # Get basic metrics
                active_ops = db.query(OperationDB).filter(
                    OperationDB.status.in_(["processing", "fetching_context", "preparing"])
                ).count()
                
                # Get last activity
                last_op = db.query(OperationDB).order_by(OperationDB.started_at.desc()).first()
                last_activity = last_op.started_at.isoformat() if last_op else None
                
                return {
                    "status": "healthy",
                    "timestamp": datetime.utcnow().isoformat(),
                    "active_operations": active_ops,
                    "last_activity": last_activity,
                    "services": {
                        "database": "online",
                        "api": "online"
                    }
                }
            finally:
                db.close()
                
        except Exception as e:
            return {
                "status": "unhealthy",
                "timestamp": datetime.utcnow().isoformat(),
                "error": str(e),
                "active_operations": 0,
                "last_activity": None,
                "services": {
                    "database": "offline",
                    "api": "degraded"
                }
            } 