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
        
        # Initialize health cache service
        from services.health_cache_service import HealthCacheService
        self.health_cache = HealthCacheService()
        
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
                
                # Enhanced notification data with repository details
                event_data = {
                    'service': service_name,
                    'previous_status': last_state,
                    'current_status': current_state,
                    'message': current_info.get('message', ''),
                    'timestamp': datetime.utcnow().isoformat()
                }
                
                # Add repository-specific details for repository health changes
                if service_name == 'repositories' and current_info.get('affected_repositories'):
                    affected_repos = current_info.get('affected_repositories', [])
                    if affected_repos:
                        repo_details = []
                        for repo in affected_repos:
                            repo_details.append(f"{repo.get('name', 'Unknown')}: {repo.get('status', 'unknown')} - {repo.get('error', 'No details')}")
                        
                        event_data['repository_details'] = repo_details
                        event_data['affected_count'] = len(affected_repos)
                        event_data['message'] = f"{current_info.get('message', '')} - Affected repositories: {', '.join([r.get('name', 'Unknown') for r in affected_repos[:3]])}"
                        if len(affected_repos) > 3:
                            event_data['message'] += f" and {len(affected_repos) - 3} more"
                
                try:
                    await self.notification_service.send_notification(
                        'SYSTEM_HEALTH_CHANGE',
                        event_data,
                        []  # No specific repositories for health changes
                    )
                except Exception as e:
                    logger.error(f"Failed to send health change notification: {e}")

    async def get_system_health(self, use_cache: bool = True) -> Dict[str, Any]:
        """Get current system health status with caching support"""
        try:
            from database import SessionLocal
            db = SessionLocal()
            
            try:
                # Initialize cache if needed
                await self.health_cache.initialize_default_services(db)
                
                if use_cache:
                    # Get cached statuses first
                    cached_statuses = await self.health_cache.get_all_cached_health_status(db)
                    health_status = {}
                    
                    # Convert cached statuses to health format
                    for service_name, cached in cached_statuses.items():
                        health_status[service_name] = {
                            'status': cached.status,
                            'message': cached.message,
                            'error_details': cached.error_details,
                            'endpoint': cached.endpoint,
                            'timestamp': cached.last_checked,
                            'is_checking': cached.is_checking,
                            'details': cached.details or {}
                        }
                    
                    # Add overall health calculation
                    health_status['overall'] = self._calculate_overall_health(health_status)
                    
                    return health_status
                else:
                    # Perform fresh health checks and update cache
                    return await self._perform_fresh_health_checks(db)
                    
            finally:
                db.close()
            
        except Exception as e:
            logger.error(f"Error getting system health: {e}")
            return {
                'overall': {
                    'status': 'error',
                    'message': f'Health check failed: {str(e)}',
                    'timestamp': datetime.utcnow().isoformat()
                }
            }
    
    async def _perform_fresh_health_checks(self, db) -> Dict[str, Any]:
        """Perform fresh health checks and update cache"""
        try:
            # Get configuration to check which services should be monitored
            from services.config_service import ConfigService
            config_service = ConfigService(self.database)
            config = await config_service.get_config()
            
            health_status = {}
            
            # Set all services to checking state
            services_to_check = ['database', 'context_service', 'repositories', 'pr_agent_config']
            for service in services_to_check:
                await self.health_cache.set_checking_status(db, service, True)
            
            # Check database
            db_health = await self._check_database_health()
            await self.health_cache.update_health_cache(db, 'database', db_health)
            health_status['database'] = db_health
            
            # Check context service (if enabled)
            context_enabled = config.get('csharp_code_context_service', {}).get('enabled', False)
            if context_enabled:
                context_health = await self._check_context_service_health(config)
                await self.health_cache.update_health_cache(db, 'context_service', context_health)
                health_status['context_service'] = context_health
            else:
                context_health = {
                    'status': 'disabled',
                    'message': 'Context service is disabled in configuration',
                    'timestamp': datetime.utcnow().isoformat()
                }
                await self.health_cache.update_health_cache(db, 'context_service', context_health)
                health_status['context_service'] = context_health
            
            # Check repository runners health
            repo_health = await self._check_repositories_health()
            await self.health_cache.update_health_cache(db, 'repositories', repo_health)
            health_status['repositories'] = repo_health
            
            # Check PR Agent config
            config_health = await self._check_pr_agent_config_health(config)
            await self.health_cache.update_health_cache(db, 'pr_agent_config', config_health)
            health_status['pr_agent_config'] = config_health
            
            # Calculate overall health
            health_status['overall'] = self._calculate_overall_health(health_status)
            
            return health_status
            
        except Exception as e:
            logger.error(f"Error performing fresh health checks: {e}")
            return {
                'overall': {
                    'status': 'error',
                    'message': f'Health check failed: {str(e)}',
                    'timestamp': datetime.utcnow().isoformat()
                }
            }
    
    async def _check_pr_agent_config_health(self, config):
        """Check PR Agent configuration health"""
        try:
            # Check if configuration is accessible and valid
            if not config:
                return {
                    'status': 'error',
                    'message': 'Configuration not accessible',
                    'timestamp': datetime.utcnow().isoformat()
                }
            
            # Check for required configuration sections
            required_sections = ['config']
            missing_sections = [section for section in required_sections if section not in config]
            
            if missing_sections:
                return {
                    'status': 'warning',
                    'message': f'Missing configuration sections: {", ".join(missing_sections)}',
                    'timestamp': datetime.utcnow().isoformat()
                }
            
            # Check if model is configured
            model = config.get('config', {}).get('model')
            if not model:
                return {
                    'status': 'warning',
                    'message': 'No AI model configured',
                    'timestamp': datetime.utcnow().isoformat()
                }
            
            return {
                'status': 'connected',
                'message': f'Configuration loaded successfully (model: {model})',
                'timestamp': datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Configuration check failed: {str(e)}',
                'timestamp': datetime.utcnow().isoformat()
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
            
            # Get endpoint from config - check both possible config keys
            endpoint = context_config.get('url') or context_config.get('endpoint', 'https://localhost:7110/')
            if not endpoint.endswith('/'):
                endpoint += '/'
            
            timeout = aiohttp.ClientTimeout(total=10)  # Increased timeout for HTTPS
            
            # Create SSL context that doesn't verify certificates for localhost
            import ssl
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            connector = aiohttp.TCPConnector(ssl=ssl_context)
            
            async with aiohttp.ClientSession(timeout=timeout, connector=connector) as session:
                # Try to make a minimal request to test connectivity
                # We'll try a simple GET request to the root endpoint first
                try:
                    async with session.get(endpoint) as response:
                        # Any response (even 404) indicates the service is running
                        if response.status in [200, 404, 405]:  # Common "service is up" responses
                            return {
                                'status': 'connected',
                                'message': f'Context service is responsive (HTTP {response.status})',
                                'timestamp': datetime.utcnow().isoformat(),
                                'endpoint': endpoint
                            }
                        else:
                            return {
                                'status': 'warning',
                                'message': f'Context service responded with HTTP {response.status}',
                                'timestamp': datetime.utcnow().isoformat(),
                                'endpoint': endpoint
                            }
                except aiohttp.ClientResponseError as e:
                    # If we get a response error, the service is still up but returned an error
                    if e.status in [400, 401, 403, 404, 405]:  # Client errors indicate service is up
                        return {
                            'status': 'connected',
                            'message': f'Context service is responsive (HTTP {e.status})',
                            'timestamp': datetime.utcnow().isoformat(),
                            'endpoint': endpoint
                        }
                    else:
                        return {
                            'status': 'error',
                            'message': f'Context service error: HTTP {e.status}',
                            'timestamp': datetime.utcnow().isoformat(),
                            'endpoint': endpoint
                        }
                        
        except asyncio.TimeoutError:
            return {
                'status': 'error',
                'message': 'Context service timeout - service may be down or slow to respond',
                'timestamp': datetime.utcnow().isoformat(),
                'endpoint': endpoint if 'endpoint' in locals() else 'unknown'
            }
        except aiohttp.ClientConnectorError as e:
            return {
                'status': 'error',
                'message': f'Context service connection failed: {str(e)}',
                'timestamp': datetime.utcnow().isoformat(),
                'endpoint': endpoint if 'endpoint' in locals() else 'unknown'
            }
        except Exception as e:
            return {
                'status': 'error',
                'message': f'Context service error: {str(e)}',
                'timestamp': datetime.utcnow().isoformat(),
                'endpoint': endpoint if 'endpoint' in locals() else 'unknown'
            }

    async def _check_repositories_health(self):
        """Check repository runner health including Azure pipeline monitoring"""
        try:
            from database import SessionLocal
            from services.runner_health_service import RunnerHealthService
            from services.azure_pipeline_config_service import AzurePipelineConfigService
            from models import RepositoryDB
            
            runner_service = RunnerHealthService()
            azure_service = AzurePipelineConfigService()
            db = SessionLocal()
            
            try:
                # Get base runner health summary
                summary = await runner_service.get_repository_health_summary(db)
                
                total = summary.get('total_repos', 0)
                healthy = summary.get('healthy_repos', 0)
                unhealthy = summary.get('unhealthy_repos', 0)
                error_repos = summary.get('error_repos', [])
                
                # Enhanced monitoring for Azure DevOps repositories
                azure_repos = db.query(RepositoryDB).filter(
                    RepositoryDB.provider == 'azure_devops',
                    RepositoryDB.is_active == True
                ).all()
                
                azure_pipeline_issues = []
                
                for repo in azure_repos:
                    if repo.azure_pat:
                        try:
                            # Check Azure pipeline health
                            pipeline_check = await azure_service.check_azure_pipeline_config({
                                'name': repo.name,
                                'url': repo.url,
                                'provider': repo.provider,
                                'azure_pat': repo.azure_pat
                            })
                            
                            # If pipeline check shows issues, add to error tracking
                            if not pipeline_check.get('has_pipeline') or pipeline_check.get('status') == 'error':
                                azure_pipeline_issues.append({
                                    'name': repo.name,
                                    'error': pipeline_check.get('error', 'No pipeline configuration found'),
                                    'status': 'pipeline_missing'
                                })
                                
                            # Update repository with pipeline status
                            repo.last_activity = datetime.utcnow()
                            
                        except Exception as azure_error:
                            logger.warning(f"Azure pipeline check failed for {repo.name}: {azure_error}")
                            azure_pipeline_issues.append({
                                'name': repo.name,
                                'error': f'Pipeline check failed: {str(azure_error)}',
                                'status': 'check_failed'
                            })
                
                # Combine runner health issues with Azure pipeline issues
                all_error_repos = list(error_repos) + azure_pipeline_issues
                total_unhealthy = unhealthy + len(azure_pipeline_issues)
                total_repos = total + len(azure_repos)
                total_healthy = total_repos - total_unhealthy
                
                if total_repos == 0:
                    return {
                        'status': 'warning',
                        'message': 'No repositories configured',
                        'timestamp': datetime.utcnow().isoformat(),
                        'details': {'total': 0, 'healthy': 0, 'unhealthy': 0}
                    }
                
                if total_unhealthy == 0:
                    return {
                        'status': 'connected',
                        'message': f'All {total_healthy}/{total_repos} repositories are healthy',
                        'timestamp': datetime.utcnow().isoformat(),
                        'details': {
                            'total': total_repos, 
                            'healthy': total_healthy, 
                            'unhealthy': total_unhealthy,
                            'azure_repos': len(azure_repos),
                            'azure_pipeline_issues': len(azure_pipeline_issues)
                        }
                    }
                else:
                    error_names = [repo['name'] for repo in all_error_repos[:3]]  # Show first 3
                    error_text = ', '.join(error_names)
                    if len(all_error_repos) > 3:
                        error_text += f' and {len(all_error_repos) - 3} more'
                    
                    return {
                        'status': 'error',
                        'message': f'{total_healthy}/{total_repos} repositories healthy',
                        'error_details': f'Issues with: {error_text}',
                        'timestamp': datetime.utcnow().isoformat(),
                        'details': {
                            'total': total_repos, 
                            'healthy': total_healthy, 
                            'unhealthy': total_unhealthy, 
                            'error_repos': all_error_repos,
                            'azure_repos': len(azure_repos),
                            'azure_pipeline_issues': len(azure_pipeline_issues),
                            'runner_issues': unhealthy
                        },
                        'affected_repositories': all_error_repos  # Add this for notifications
                    }
                
                # Commit any repository updates
                db.commit()
                    
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