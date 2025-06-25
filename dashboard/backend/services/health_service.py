"""
Health Service - Responsible for system health monitoring and checks
Follows Single Responsibility Principle
"""
import aiohttp
import toml
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional
from config import settings
import asyncio
import logging
import json

logger = logging.getLogger(__name__)

class HealthService:
    """Service for monitoring system health and external dependencies"""
    
    def __init__(self, database_manager, notification_service=None, config_service=None):
        self.database = database_manager
        self.notification_service = notification_service
        self.config_service = config_service
        self.last_health_status = {}
        self.monitoring_task = None
        self.monitoring_interval = 30  # seconds
        self.last_check = None
        self.cached_results = {}
        
        # Note: Health service startup logging moved to be called after server is running
    
    def _log_health_service_startup(self):
        """Log health service startup with configuration summary"""
        try:
            config_summary = self._get_health_config_summary()
            
            self._log_to_system('INFO', 
                f"Health monitor service started - Monitoring {len(config_summary.get('services', []))} services (check interval: {config_summary.get('check_interval', 'unknown')})",
                {
                    'config': config_summary,
                    'system_event': 'health_service_start',
                    'service_count': len(config_summary.get('services', []))
                }
            )
        except Exception as e:
            logger.warning(f"Failed to log health service startup: {e}")
    
    def _log_health_service_shutdown(self):
        """Log health service shutdown"""
        try:
            self._log_to_system('INFO', 
                "Health monitor service stopped - Health monitoring disabled",
                {'system_event': 'health_service_stop'}
            )
        except Exception as e:
            # Use basic logging if system logging fails during shutdown
            logger.error(f"Failed to log health service shutdown: {e}")
    
    def _get_health_config_summary(self) -> Dict[str, Any]:
        """Get health service configuration summary"""
        try:
            # Get configuration from config service or use defaults
            config = {}
            if self.config_service:
                try:
                    # Note: config_service.get_config() is async, but we're in sync context
                    # For now, use empty config - TODO: make this properly async
                    pass
                except Exception:
                    pass
            
            services_monitored = []
            
            # Check which services are configured for monitoring
            if config.get('pr_agent_url'):
                services_monitored.append('pr_agent')
            if config.get('database_path'):
                services_monitored.append('database')
            if config.get('context_service', {}).get('enabled'):
                services_monitored.append('context_service')
            
            # Always monitor API and websocket
            services_monitored.extend(['api', 'websocket'])
            
            return {
                'services': services_monitored,
                'check_interval': '5 minutes',  # Default monitoring interval
                'pr_agent_enabled': bool(config.get('pr_agent_url')),
                'context_service_enabled': bool(config.get('context_service', {}).get('enabled')),
                'database_monitoring': bool(config.get('database_path'))
            }
        except Exception:
            return {
                'services': ['api', 'websocket'],
                'check_interval': '5 minutes',
                'error': 'Failed to get configuration'
            }
    
    def _log_to_system(self, level: str, message: str, context: dict = None):
        """Create a system log entry for health service events"""
        try:
            # Only attempt logging if we're not in initialization phase
            import requests
            
            # Create a system log entry
            log_data = {
                'timestamp': datetime.utcnow().isoformat(),
                'level': level,
                'message': f"[HEALTH] {message}",
                'source': 'health_system',
                'job_id': None,
                'operation_id': None,
                'repository': None,
                'status': None
            }
            
            # Add context to log data
            if context:
                log_data.update(context)
            
            # Send directly to dashboard backend
            try:
                requests.post('http://localhost:8000/logs/immediate', json=log_data, timeout=2)
            except Exception:
                # If dashboard is not available, log normally - but don't fail
                try:
                    getattr(logger, level.lower(), logger.info)(message)
                except Exception:
                    pass  # Don't let logging failures cascade
                
        except Exception as e:
            # Don't let logging errors break the health service
            pass

    async def start_background_monitoring(self):
        """Start background health monitoring"""
        if self.monitoring_task is None or self.monitoring_task.done():
            logger.info("Starting background health monitoring")
            self.monitoring_task = asyncio.create_task(self._background_health_monitor())
            
            # Log monitoring start
            self._log_to_system('INFO', 
                "Health monitoring started - Background health checks enabled",
                {'system_event': 'health_monitoring_start'}
            )
    
    async def stop_background_monitoring(self):
        """Stop background health monitoring"""
        if self.monitoring_task and not self.monitoring_task.done():
            logger.info("Stopping background health monitoring")
            self.monitoring_task.cancel()
            try:
                await self.monitoring_task
            except asyncio.CancelledError:
                pass
            
            # Log monitoring stop
            self._log_health_service_shutdown()
    
    async def _background_health_monitor(self):
        """Background task to monitor health and send notifications on changes"""
        try:
            while True:
                try:
                    # Get current health status
                    current_status = await self.get_system_health()
                    
                    # Check for changes and send notifications
                    await self._check_health_changes(current_status)
                    
                    # Update last known status
                    self.last_health_status = current_status.copy()
                    
                except Exception as e:
                    logger.error(f"Error in background health monitoring: {e}")
                
                # Wait before next check
                await asyncio.sleep(self.monitoring_interval)
                
        except asyncio.CancelledError:
            logger.info("Background health monitoring cancelled")
            raise
        except Exception as e:
            logger.error(f"Background health monitoring failed: {e}")
    
    async def _check_health_changes(self, current_status: Dict[str, Any]):
        """Check for health status changes and send notifications"""
        if not self.notification_service:
            return
            
        for service_name, current_info in current_status.items():
            if service_name == 'overall':
                continue
                
            current_state = current_info.get('status', 'unknown')
            last_state = self.last_health_status.get(service_name, {}).get('status', 'unknown')
            
            # Only notify on actual status changes (not initial state)
            if last_state != 'unknown' and current_state != last_state:
                logger.info(f"Health change detected for {service_name}: {last_state} -> {current_state}")
                
                # Send notification
                event_data = {
                    'service': service_name,
                    'previous_status': last_state,
                    'current_status': current_state,
                    'message': current_info.get('message', ''),
                    'timestamp': datetime.utcnow().isoformat()
                }
                
                try:
                    await self.notification_service.send_notification(
                        'SYSTEM_HEALTH_CHANGE',
                        event_data,
                        []  # No specific repositories for health changes
                    )
                except Exception as e:
                    logger.error(f"Failed to send health change notification: {e}")

    async def get_system_health(self) -> Dict[str, Any]:
        """Get current system health status"""
        try:
            # Get configuration to check which services should be monitored
            from services.config_service import ConfigService
            config_service = ConfigService(self.database)
            config = await config_service.get_config()
            
            health_status = {}
            
            # Check database
            health_status['database'] = await self._check_database_health()
            
            # Check git provider (if configured)
            if config.get('git', {}).get('provider'):
                health_status['git_provider'] = await self._check_git_provider_health(config)
            
            # Check AI service (if configured)
            if config.get('ai', {}).get('model'):
                health_status['ai_service'] = await self._check_ai_service_health(config)
            
            # Check context service (if enabled)
            context_enabled = config.get('csharp_code_context_service', {}).get('enabled', False)
            if context_enabled:
                health_status['context_service'] = await self._check_context_service_health(config)
            else:
                health_status['context_service'] = {
                    'status': 'disabled',
                    'message': 'Context service is disabled in configuration',
                    'timestamp': datetime.utcnow().isoformat()
                }
            
            # Check repository runners health
            health_status['repositories'] = await self._check_repositories_health()
            
            # Calculate overall health
            health_status['overall'] = self._calculate_overall_health(health_status)
            
            return health_status
            
        except Exception as e:
            logger.error(f"Error getting system health: {e}")
            return {
                'overall': {
                    'status': 'error',
                    'message': f'Health check failed: {str(e)}',
                    'timestamp': datetime.utcnow().isoformat()
                }
            }

    async def _check_database_health(self):
        """Check database connectivity"""
        try:
            # Simple database query to check connectivity
            configs = self.database.get_notification_configs()
            return {
                'status': 'connected',
                'message': 'Database is accessible',
                'timestamp': datetime.utcnow().isoformat()
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Database error: {str(e)}',
                'timestamp': datetime.utcnow().isoformat()
            }

    async def _check_git_provider_health(self, config):
        """Check git provider connectivity"""
        try:
            # This would need to be implemented based on the specific git provider
            # For now, return a basic check
            provider = config.get('git', {}).get('provider', 'unknown')
            return {
                'status': 'connected',
                'message': f'{provider} provider configured',
                'timestamp': datetime.utcnow().isoformat()
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Git provider error: {str(e)}',
                'timestamp': datetime.utcnow().isoformat()
            }

    async def _check_ai_service_health(self, config):
        """Check AI service connectivity"""
        try:
            # This would need to be implemented based on the AI service
            model = config.get('ai', {}).get('model', 'unknown')
            return {
                'status': 'connected',
                'message': f'AI model {model} configured',
                'timestamp': datetime.utcnow().isoformat()
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'AI service error: {str(e)}',
                'timestamp': datetime.utcnow().isoformat()
            }

    async def _check_context_service_health(self, config):
        """Check context service health"""
        try:
            context_config = config.get('csharp_code_context_service', {})
            if not context_config.get('enabled', False):
                return {
                    'status': 'disabled',
                    'message': 'Context service is disabled',
                    'timestamp': datetime.utcnow().isoformat()
                }
            
            # Check if context service endpoint is accessible
            endpoint = context_config.get('endpoint', 'http://localhost:5000')
            timeout = aiohttp.ClientTimeout(total=5)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(f"{endpoint}/health") as response:
                    if response.status == 200:
                        return {
                            'status': 'connected',
                            'message': 'Context service is responsive',
                            'timestamp': datetime.utcnow().isoformat()
                        }
                    else:
                        return {
                            'status': 'error',
                            'message': f'Context service returned status {response.status}',
                            'timestamp': datetime.utcnow().isoformat()
                        }
        except asyncio.TimeoutError:
            return {
                'status': 'error',
                'message': 'Context service timeout',
                'timestamp': datetime.utcnow().isoformat()
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Context service error: {str(e)}',
                'timestamp': datetime.utcnow().isoformat()
            }

    async def _check_repositories_health(self):
        """Check repository runner health"""
        try:
            from database import SessionLocal
            from services.runner_health_service import RunnerHealthService
            
            runner_service = RunnerHealthService()
            db = SessionLocal()
            
            try:
                summary = await runner_service.get_repository_health_summary(db)
                
                total = summary.get('total_repos', 0)
                healthy = summary.get('healthy_repos', 0)
                unhealthy = summary.get('unhealthy_repos', 0)
                error_repos = summary.get('error_repos', [])
                
                if total == 0:
                    return {
                        'status': 'warning',
                        'message': 'No repositories configured',
                        'timestamp': datetime.utcnow().isoformat(),
                        'details': {'total': 0, 'healthy': 0, 'unhealthy': 0}
                    }
                
                if unhealthy == 0:
                    return {
                        'status': 'connected',
                        'message': f'All {healthy}/{total} repositories are healthy',
                        'timestamp': datetime.utcnow().isoformat(),
                        'details': {'total': total, 'healthy': healthy, 'unhealthy': unhealthy}
                    }
                else:
                    error_names = [repo['name'] for repo in error_repos[:3]]  # Show first 3
                    error_text = ', '.join(error_names)
                    if len(error_repos) > 3:
                        error_text += f' and {len(error_repos) - 3} more'
                    
                    return {
                        'status': 'error',
                        'message': f'{healthy}/{total} repositories healthy',
                        'error_details': f'Issues with: {error_text}',
                        'timestamp': datetime.utcnow().isoformat(),
                        'details': {'total': total, 'healthy': healthy, 'unhealthy': unhealthy, 'error_repos': error_repos}
                    }
                    
            finally:
                await runner_service.close_session()
                db.close()
                
        except Exception as e:
            logger.error(f"Error checking repositories health: {e}")
            return {
                'status': 'error',
                'message': f'Repository health check failed: {str(e)}',
                'timestamp': datetime.utcnow().isoformat()
            }

    def _calculate_overall_health(self, health_status):
        """Calculate overall system health"""
        statuses = []
        for service, info in health_status.items():
            if service != 'overall':
                status = info.get('status', 'unknown')
                if status != 'disabled':  # Don't count disabled services
                    statuses.append(status)
        
        if not statuses:
            overall_status = 'unknown'
            message = 'No services to monitor'
        elif any(status == 'error' for status in statuses):
            overall_status = 'error'
            message = 'One or more services have errors'
        elif any(status == 'warning' for status in statuses):
            overall_status = 'warning'
            message = 'One or more services have warnings'
        elif all(status == 'connected' for status in statuses):
            overall_status = 'connected'
            message = 'All services are healthy'
        else:
            overall_status = 'unknown'
            message = 'System health status unclear'
        
        return {
            'status': overall_status,
            'message': message,
            'timestamp': datetime.utcnow().isoformat()
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