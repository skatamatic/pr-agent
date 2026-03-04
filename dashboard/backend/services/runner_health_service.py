import asyncio
import logging
import sys
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
import aiohttp
import subprocess
import json
import os
import base64
import toml
import yaml
from sqlalchemy.orm import Session

from models import RepositoryDB

logger = logging.getLogger(__name__)

# Throttle full runner/agent API checks when returning repository health (avoid rate limits)
REPOSITORY_HEALTH_REFRESH_INTERVAL = timedelta(seconds=120)
_last_repository_health_refresh: Optional[datetime] = None

# Cloud/Linux: local Windows service checks are not available; use API-based health only.
def _is_windows() -> bool:
    return sys.platform == "win32"


class RunnerHealthService:
    """Service for checking the health of GitHub self-hosted runners and Azure DevOps agents (local and remote/API)."""
    
    def __init__(self):
        self.session = None
        self._session_timeout = aiohttp.ClientTimeout(total=10)
    
    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        if self.session is None or self.session.closed:
            self.session = aiohttp.ClientSession(timeout=self._session_timeout)
        return self.session
    
    async def close_session(self):
        """Close aiohttp session"""
        if self.session and not self.session.closed:
            await self.session.close()
    
    async def validate_repository_token(self, db: Session, repo: RepositoryDB) -> Dict[str, Any]:
        """Validate repository access token by attempting to access repository info"""
        try:
            if repo.provider == "github":
                return await self._validate_github_token(repo)
            elif repo.provider == "azure_devops":
                return await self._validate_azure_token(repo)
            else:
                return {
                    "valid": False,
                    "error": f"Unsupported provider: {repo.provider}",
                    "status": "error"
                }
        except Exception as e:
            logger.error(f"Error validating token for {repo.name}: {e}")
            return {
                "valid": False,
                "error": str(e),
                "status": "error"
            }
    
    async def _validate_github_token(self, repo: RepositoryDB) -> Dict[str, Any]:
        """Validate GitHub token by checking repository access"""
        if not repo.github_token:
            return {
                "valid": False,
                "error": "GitHub token not provided",
                "status": "misconfigured"
            }
        
        try:
            # Extract owner/repo from repo name or URL
            if "/" in repo.name:
                owner, repo_name = repo.name.split("/", 1)
            else:
                # Try to extract from URL
                url_parts = repo.url.rstrip("/").split("/")
                if len(url_parts) >= 2:
                    owner, repo_name = url_parts[-2], url_parts[-1]
                    if repo_name.endswith(".git"):
                        repo_name = repo_name[:-4]
                else:
                    return {
                        "valid": False,
                        "error": "Cannot parse repository owner/name",
                        "status": "misconfigured"
                    }
            
            session = await self._get_session()
            
            # First check repository access (requires Metadata:read permission)
            url = f"https://api.github.com/repos/{owner}/{repo_name}"
            headers = {
                "Authorization": f"Bearer {repo.github_token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "PR-Agent-Dashboard/1.0"
            }
            
            logger.info(f"Testing repository access for {owner}/{repo_name}")
            async with session.get(url, headers=headers) as response:
                if response.status == 401:
                    return {
                        "valid": False,
                        "error": "GitHub token is invalid or expired",
                        "status": "error"
                    }
                elif response.status == 403:
                    return {
                        "valid": False,
                        "error": "GitHub token lacks 'Metadata:read' permission for repository access",
                        "status": "error"
                    }
                elif response.status == 404:
                    return {
                        "valid": False,
                        "error": f"Repository {owner}/{repo_name} not found or no access",
                        "status": "error"
                    }
                elif response.status != 200:
                    return {
                        "valid": False,
                        "error": f"GitHub API error: {response.status}",
                        "status": "error"
                    }
                
                logger.info(f"Repository access successful for {owner}/{repo_name}")
                
                # Token is valid for basic access, now try runner check (optional)
                runner_health = await self._check_github_runner(repo)
                
                # If runner check fails due to permissions, still consider token valid
                if runner_health.get("status") == "misconfigured" and "Actions:read" in runner_health.get("error", ""):
                    logger.warning(f"Runner check failed for {owner}/{repo_name}: {runner_health.get('error')}")
                    return {
                        "valid": True,
                        "error": None,
                        "status": "healthy",  # Token is valid, just can't check runners
                        "last_seen": datetime.utcnow(),
                        "details": "Token valid but lacks Actions:read permission for runner monitoring"
                    }
                
                return {
                    "valid": True,
                    "error": None,
                    "status": runner_health.get("status", "healthy"),
                    "last_seen": runner_health.get("last_seen"),
                    "details": runner_health.get("details")
                }
        
        except aiohttp.ClientError as e:
            return {
                "valid": False,
                "error": f"Network error: {str(e)}",
                "status": "error"
            }
        except Exception as e:
            return {
                "valid": False,
                "error": f"Unexpected error: {str(e)}",
                "status": "error"
            }
    
    async def _validate_azure_token(self, repo: RepositoryDB) -> Dict[str, Any]:
        """Validate Azure DevOps token by checking repository access"""
        if not repo.azure_pat:
            return {
                "valid": False,
                "error": "Azure DevOps PAT not provided",
                "status": "misconfigured"
            }
        
        try:
            # Extract organization and project info
            organization = None
            project = None
            
            # Try to get from repo config first
            if repo.config and isinstance(repo.config, dict):
                organization = repo.config.get("azure_organization")
                project = repo.config.get("azure_project")
            
            # If not in config, try to parse from URL
            if not organization or not project:
                if "dev.azure.com" in repo.url:
                    url_parts = repo.url.split("/")
                    if len(url_parts) >= 5:
                        organization = url_parts[3]
                        project = url_parts[4]
                elif ".visualstudio.com" in repo.url:
                    url_parts = repo.url.split("/")
                    if len(url_parts) >= 4:
                        organization = url_parts[2].split(".")[0]
                        project = url_parts[3]
            
            if not organization or not project:
                return {
                    "valid": False,
                    "error": "Cannot determine Azure DevOps organization/project",
                    "status": "misconfigured"
                }
            
            session = await self._get_session()
            
            # Test PAT by getting project info - using current stable API version
            url = f"https://dev.azure.com/{organization}/_apis/projects/{project}?api-version=7.1-preview.4"
            auth_header = base64.b64encode(f":{repo.azure_pat}".encode('utf-8')).decode('ascii')
            headers = {
                "Authorization": f"Basic {auth_header}",
                "Accept": "application/json",
                "User-Agent": "PR-Agent-Dashboard/1.0"
            }
            
            logger.info(f"Testing Azure PAT for {organization}/{project} with URL: {url}")
            
            async with session.get(url, headers=headers) as response:
                logger.info(f"Azure PAT validation response: {response.status} {response.reason}")
                
                if response.status == 401:
                    return {
                        "valid": False,
                        "error": "Azure DevOps PAT is invalid or expired",
                        "status": "error"
                    }
                elif response.status == 403:
                    return {
                        "valid": False,
                        "error": "Azure DevOps PAT lacks required permissions",
                        "status": "error"
                    }
                elif response.status == 404:
                    return {
                        "valid": False,
                        "error": f"Azure DevOps project {organization}/{project} not found",
                        "status": "error"
                    }
                elif response.status == 203:
                    # Non-Authoritative Information - treat as success with warning
                    logger.warning(f"Azure DevOps API returned 203 (Non-Authoritative Information) for {organization}/{project}")
                    # 203 typically means the response is from a cache or proxy, continue processing
                    pass
                elif response.status != 200:
                    response_text = await response.text()
                    logger.error(f"Azure DevOps API error {response.status}: {response_text}")
                    return {
                        "valid": False,
                        "error": f"Azure DevOps API error: {response.status} - {response.reason}",
                        "status": "error"
                    }
                
                # Token is valid, check agent status as well
                agent_health = await self._check_azure_agent(repo)
                
                return {
                    "valid": True,
                    "error": None,
                    "status": agent_health.get("status", "healthy"),
                    "last_seen": agent_health.get("last_seen"),
                    "details": agent_health.get("details")
                }
        
        except aiohttp.ClientError as e:
            return {
                "valid": False,
                "error": f"Network error: {str(e)}",
                "status": "error"
            }
        except Exception as e:
            return {
                "valid": False,
                "error": f"Unexpected error: {str(e)}",
                "status": "error"
            }
    
    async def check_repository_runner_health(self, db: Session, repo: RepositoryDB) -> Dict[str, Any]:
        """Check runner health for a specific repository"""
        try:
            # Check cloud runner status (GitHub Actions runner API or Azure DevOps)
            cloud_runner_result = None
            if repo.provider == "github":
                cloud_runner_result = await self._check_github_runner(repo)
            elif repo.provider == "azure_devops":
                cloud_runner_result = await self._check_azure_agent(repo)
            else:
                cloud_runner_result = {
                    "status": "unknown",
                    "error": f"Unsupported provider: {repo.provider}",
                    "last_seen": None
                }
            
            # Check local Windows service status only on Windows when service name is configured
            service_runner_result = None
            if repo.runner_service_name and _is_windows():
                service_runner_result = await self._check_local_runner_service(repo)
            elif repo.runner_service_name and not _is_windows():
                service_runner_result = {
                    "status": "cloud_only",
                    "error": "Local runner service check is only available on Windows. On Linux/Cloud Run, health is from GitHub API above.",
                    "last_seen": None,
                    "health_impact": "healthy",
                    "details": "Use API-based runner status (cloud_runner) on this platform.",
                }
            
            # Combine results - prioritize service status for overall health
            overall_status = cloud_runner_result.get("status", "unknown")
            overall_error = cloud_runner_result.get("error")
            overall_last_seen = cloud_runner_result.get("last_seen")
            
            # If we have service monitoring and it's more critical, use that
            if service_runner_result:
                service_status = service_runner_result.get("status", "unknown")
                if service_status in ["stopped", "not_found", "error"]:
                    # Service issues take precedence over cloud runner status
                    overall_status = service_status
                    overall_error = service_runner_result.get("error")
                elif service_status == "running" and overall_status in ["stopped", "error"]:
                    # Service is running but cloud runner shows issues
                    overall_status = "warning"
                    overall_error = f"Service running but {overall_error}"
            
            return {
                "status": overall_status,
                "error": overall_error,
                "last_seen": overall_last_seen,
                "cloud_runner": cloud_runner_result,
                "service_runner": service_runner_result
            }
        except Exception as e:
            logger.error(f"Error checking runner health for {repo.name}: {e}")
            return {
                "status": "error",
                "error": str(e),
                "last_seen": None
            }
    
    async def _check_github_runner(self, repo: RepositoryDB) -> Dict[str, Any]:
        """Check GitHub self-hosted runner status"""
        if not repo.github_token:
            return {
                "status": "misconfigured",
                "error": "GitHub token not configured",
                "last_seen": None
            }
        
        try:
            # Extract owner/repo from repo name or URL
            if "/" in repo.name:
                owner, repo_name = repo.name.split("/", 1)
            else:
                # Try to extract from URL
                url_parts = repo.url.rstrip("/").split("/")
                if len(url_parts) >= 2:
                    owner, repo_name = url_parts[-2], url_parts[-1]
                    if repo_name.endswith(".git"):
                        repo_name = repo_name[:-4]
                else:
                    return {
                        "status": "misconfigured",
                        "error": "Cannot parse repository owner/name",
                        "last_seen": None
                    }
            
            session = await self._get_session()
            
            # Check self-hosted runners for the repository (requires Actions:read permission)
            url = f"https://api.github.com/repos/{owner}/{repo_name}/actions/runners"
            headers = {
                "Authorization": f"Bearer {repo.github_token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "PR-Agent-Dashboard/1.0"
            }
            
            logger.info(f"Checking runners for {owner}/{repo_name}")
            async with session.get(url, headers=headers) as response:
                if response.status == 401:
                    return {
                        "status": "misconfigured",
                        "error": "GitHub token is invalid or expired",
                        "last_seen": None
                    }
                elif response.status == 403:
                    return {
                        "status": "misconfigured", 
                        "error": "GitHub token lacks 'Actions:read' permission to check runners. For fine-grained tokens, ensure 'Actions' permission is set to 'Read'.",
                        "last_seen": None
                    }
                elif response.status == 404:
                    return {
                        "status": "misconfigured",
                        "error": f"Repository {owner}/{repo_name} not found or no access",
                        "last_seen": None
                    }
                elif response.status != 200:
                    return {
                        "status": "error",
                        "error": f"GitHub API error: {response.status}",
                        "last_seen": None
                    }
                
                logger.info(f"Successfully accessed runners API for {owner}/{repo_name}")
                data = await response.json()
                runners = data.get("runners", [])
                
                if not runners:
                    return {
                        "status": "stopped",
                        "error": "No self-hosted runners configured",
                        "last_seen": None
                    }
                
                # Check for online runners
                online_runners = [r for r in runners if r.get("status") == "online"]
                
                if not online_runners:
                    return {
                        "status": "stopped",
                        "error": f"All {len(runners)} runners are offline",
                        "last_seen": None
                    }
                
                # Find the most recently active runner and collect detailed info
                most_recent = None
                runner_details = []
                
                for runner in online_runners:
                    if runner.get("status") == "online":
                        # GitHub doesn't provide last_seen, but we can assume online = recent
                        most_recent = datetime.utcnow()
                        
                        # Collect runner details
                        runner_info = {
                            "name": runner.get("name", "Unknown"),
                            "os": runner.get("os", "Unknown"),
                            "architecture": runner.get("architecture", "Unknown"),
                            "labels": runner.get("labels", []),
                            "busy": runner.get("busy", False)
                        }
                        runner_details.append(runner_info)
                
                return {
                    "status": "running",
                    "error": None,
                    "last_seen": most_recent,
                    "details": f"{len(online_runners)}/{len(runners)} runners online",
                    "runner_info": runner_details
                }
        
        except aiohttp.ClientError as e:
            return {
                "status": "error",
                "error": f"Network error: {str(e)}",
                "last_seen": None
            }
        except Exception as e:
            return {
                "status": "error", 
                "error": f"Unexpected error: {str(e)}",
                "last_seen": None
            }
    
    async def _check_azure_agent(self, repo: RepositoryDB) -> Dict[str, Any]:
        """Check Azure DevOps agent status"""
        if not repo.azure_pat:
            return {
                "status": "misconfigured",
                "error": "Azure DevOps PAT not configured",
                "last_seen": None
            }
        
        try:
            # Extract organization and project from repo URL or config
            organization = None
            project = None
            
            # Try to get from repo config first
            if repo.config and isinstance(repo.config, dict):
                organization = repo.config.get("azure_organization")
                project = repo.config.get("azure_project")
            
            # If not in config, try to parse from URL
            if not organization or not project:
                # Azure DevOps URLs: https://dev.azure.com/org/project/_git/repo
                if "dev.azure.com" in repo.url:
                    url_parts = repo.url.split("/")
                    if len(url_parts) >= 5:
                        organization = url_parts[3]
                        project = url_parts[4]
                elif ".visualstudio.com" in repo.url:
                    # Legacy format: https://org.visualstudio.com/project/_git/repo
                    url_parts = repo.url.split("/")
                    if len(url_parts) >= 4:
                        organization = url_parts[2].split(".")[0]
                        project = url_parts[3]
            
            if not organization or not project:
                return {
                    "status": "misconfigured",
                    "error": "Cannot determine Azure organization/project from URL or config",
                    "last_seen": None
                }
            
            session = await self._get_session()
            
            # Get agent pools using updated API version and proper auth
            url = f"https://dev.azure.com/{organization}/_apis/distributedtask/pools?api-version=7.1-preview.1"
            auth_header = base64.b64encode(f":{repo.azure_pat}".encode('utf-8')).decode('ascii')
            headers = {
                "Authorization": f"Basic {auth_header}",
                "Accept": "application/json",
                "User-Agent": "PR-Agent-Dashboard/1.0"
            }
            
            logger.info(f"Checking Azure agent pools for {organization} with URL: {url}")
            
            async with session.get(url, headers=headers) as response:
                logger.info(f"Azure agent pools response: {response.status} {response.reason}")
                
                if response.status == 401:
                    return {
                        "status": "misconfigured", 
                        "error": "Azure DevOps PAT is invalid or expired",
                        "last_seen": None
                    }
                elif response.status == 403:
                    return {
                        "status": "misconfigured",
                        "error": "Azure DevOps PAT lacks required permissions",
                        "last_seen": None
                    }
                elif response.status == 203:
                    # Non-Authoritative Information - treat as success with warning
                    logger.warning(f"Azure DevOps agent pools API returned 203 (Non-Authoritative Information) for {organization}")
                    # 203 typically means the response is from a cache or proxy, continue processing
                    pass
                elif response.status != 200:
                    response_text = await response.text()
                    logger.error(f"Azure agent pools API error {response.status}: {response_text}")
                    return {
                        "status": "error",
                        "error": f"Azure DevOps API error: {response.status}",
                        "last_seen": None
                    }
                
                pools_data = await response.json()
                pools = pools_data.get("value", [])
                
                if not pools:
                    return {
                        "status": "stopped",
                        "error": "No agent pools found",
                        "last_seen": None
                    }
                
                # Check agents in each pool
                total_agents = 0
                online_agents = 0
                most_recent = None
                
                for pool in pools:
                    pool_id = pool.get("id")
                    agents_url = f"https://dev.azure.com/{organization}/_apis/distributedtask/pools/{pool_id}/agents?api-version=7.0"
                    
                    async with session.get(agents_url, headers=headers) as agents_response:
                        if agents_response.status == 200:
                            agents_data = await agents_response.json()
                            agents = agents_data.get("value", [])
                            total_agents += len(agents)
                            
                            for agent in agents:
                                if agent.get("status") == "online":
                                    online_agents += 1
                                    # Get last activity time if available
                                    last_activity = agent.get("lastCompletedTime")
                                    if last_activity:
                                        try:
                                            agent_time = datetime.fromisoformat(last_activity.replace("Z", "+00:00"))
                                            if most_recent is None or agent_time > most_recent:
                                                most_recent = agent_time
                                        except:
                                            pass
                
                if total_agents == 0:
                    return {
                        "status": "stopped",
                        "error": "No agents found in any pool",
                        "last_seen": None
                    }
                
                if online_agents == 0:
                    return {
                        "status": "stopped",
                        "error": f"All {total_agents} agents are offline",
                        "last_seen": most_recent
                    }
                
                return {
                    "status": "running",
                    "error": None,
                    "last_seen": most_recent or datetime.utcnow(),
                    "details": f"{online_agents}/{total_agents} agents online"
                }
        
        except aiohttp.ClientError as e:
            return {
                "status": "error",
                "error": f"Network error: {str(e)}",
                "last_seen": None
            }
        except Exception as e:
            return {
                "status": "error",
                "error": f"Unexpected error: {str(e)}",
                "last_seen": None
            }
    
    async def _check_local_runner_service(self, repo: RepositoryDB) -> Dict[str, Any]:
        """Check local Windows service runner status (Windows only; call only when _is_windows())."""
        if not _is_windows():
            return {
                "status": "cloud_only",
                "error": "Local service check is only available on Windows.",
                "last_seen": None,
                "health_impact": "healthy",
            }
        try:
            from services.runner_service_monitor import RunnerServiceMonitor
            monitor = RunnerServiceMonitor()
            
            # Check service status
            service_status = monitor.check_service_status(repo.runner_service_name)
            
            # Map service status to repository health impact
            status = service_status.get('status', 'unknown')
            health_impact = monitor.get_service_health_impact(service_status)
            
            # Update repository with latest service information
            repo.runner_service_status = status
            repo.runner_service_last_checked = datetime.utcnow()
            repo.runner_service_details = service_status
            
            # Update overall runner status based on service health impact
            if health_impact == 'healthy':
                repo.runner_status = 'running'
                repo.runner_error = None
            elif health_impact == 'warning':
                repo.runner_status = 'warning'
                repo.runner_error = f"Service {status}: {service_status.get('status_display', status)}"
            else:  # error
                repo.runner_status = 'error'
                repo.runner_error = service_status.get('error') or f"Service {status}: {service_status.get('status_display', status)}"
            
            return {
                "status": status,
                "error": service_status.get('error'),
                "last_seen": datetime.utcnow() if status == 'running' else None,
                "service_name": repo.runner_service_name,
                "details": service_status,
                "health_impact": health_impact
            }
        except Exception as e:
            logger.error(f"Error checking local runner service for {repo.name}: {e}")
            # Update repository with error status
            repo.runner_status = 'error'
            repo.runner_error = f"Failed to check service: {str(e)}"
            repo.runner_service_status = 'error'
            repo.runner_service_last_checked = datetime.utcnow()
            
            return {
                "status": "error",
                "error": f"Failed to check service: {str(e)}",
                "last_seen": None,
                "service_name": repo.runner_service_name,
                "health_impact": "error"
            }
    
    async def check_all_repositories(self, db: Session) -> Dict[str, Any]:
        """Check runner health for all active repositories with runner/agent config (local service or API token)."""
        try:
            # Include repos that have local runner/agent service name OR provider token (API-based health)
            from sqlalchemy import or_, and_
            repositories = db.query(RepositoryDB).filter(
                RepositoryDB.is_active == True,
                or_(
                    and_(
                        RepositoryDB.runner_service_name.isnot(None),
                        RepositoryDB.runner_service_name != ""
                    ),
                    and_(
                        RepositoryDB.azure_agent_service_name.isnot(None),
                        RepositoryDB.azure_agent_service_name != ""
                    ),
                    and_(RepositoryDB.github_token.isnot(None), RepositoryDB.github_token != ""),
                    and_(RepositoryDB.azure_pat.isnot(None), RepositoryDB.azure_pat != "")
                )
            ).all()
            
            results = {
                "total_repos": len(repositories),
                "healthy_repos": 0,
                "unhealthy_repos": 0,
                "error_repos": [],
                "status_summary": {},
                "last_updated": datetime.utcnow().isoformat()
            }
            
            # Check each repository
            for repo in repositories:
                health_result = await self.check_repository_runner_health(db, repo)
                
                # Update repository with health status (from cloud API and/or local service)
                repo.runner_status = health_result["status"]
                repo.runner_error = health_result["error"]
                if health_result["last_seen"]:
                    repo.runner_last_seen = health_result["last_seen"]
                # For ADO, also set azure_agent_status from cloud result so summary reflects API-based health
                if repo.provider == "azure_devops" and health_result.get("cloud_runner"):
                    repo.azure_agent_status = health_result["cloud_runner"].get("status")
                    repo.azure_agent_error = health_result["cloud_runner"].get("error")
                
                # Update counters
                if health_result["status"] == "running":
                    results["healthy_repos"] += 1
                else:
                    results["unhealthy_repos"] += 1
                    results["error_repos"].append({
                        "name": repo.name,
                        "status": health_result["status"],
                        "error": health_result["error"]
                    })
                
                # Track status summary
                status = health_result["status"]
                if status not in results["status_summary"]:
                    results["status_summary"][status] = 0
                results["status_summary"][status] += 1
            
            # Commit all updates
            db.commit()
            
            return results
            
        except Exception as e:
            logger.error(f"Error checking all repositories: {e}")
            db.rollback()
            raise Exception(f"Failed to check repository health: {str(e)}")
    
    async def get_repository_health_summary_with_refresh(self, db: Session) -> Dict[str, Any]:
        """Get repository health summary; refresh runner/agent status via API if last refresh was > REFRESH_INTERVAL ago."""
        global _last_repository_health_refresh
        now = datetime.utcnow()
        if _last_repository_health_refresh is None or (now - _last_repository_health_refresh) > REPOSITORY_HEALTH_REFRESH_INTERVAL:
            try:
                await self.check_all_repositories(db)
                _last_repository_health_refresh = now
            except Exception as e:
                logger.warning(f"Background runner health refresh failed: {e}")
        return await self.get_repository_health_summary(db)
    
    async def get_repository_health_summary(self, db: Session) -> Dict[str, Any]:
        """Get a summary of repository health status (local runner service and/or API-based remote runner/agent)."""
        try:
            # Include repos that have runner/agent config: local service name OR provider token (API-based health)
            from sqlalchemy import or_, and_
            repositories = db.query(RepositoryDB).filter(
                RepositoryDB.is_active == True,
                or_(
                    and_(
                        RepositoryDB.runner_service_name.isnot(None),
                        RepositoryDB.runner_service_name != ""
                    ),
                    and_(
                        RepositoryDB.azure_agent_service_name.isnot(None),
                        RepositoryDB.azure_agent_service_name != ""
                    ),
                    and_(RepositoryDB.github_token.isnot(None), RepositoryDB.github_token != ""),
                    and_(RepositoryDB.azure_pat.isnot(None), RepositoryDB.azure_pat != "")
                )
            ).all()
            
            total = len(repositories)
            # Healthy = runner_status or (for ADO) azure_agent_status is 'running' (from API or local check)
            healthy = 0
            for r in repositories:
                runner_ok = r.runner_status == "running"
                azure_ok = r.azure_agent_status == "running" if r.provider == "azure_devops" else None
                if runner_ok or azure_ok:
                    healthy += 1
            
            unhealthy = total - healthy
            
            # Error details for repos that are not healthy
            error_repos = []
            for repo in repositories:
                runner_ok = repo.runner_status == "running"
                azure_ok = repo.azure_agent_status == "running" if repo.provider == "azure_devops" else None
                if runner_ok or azure_ok:
                    continue
                status = repo.runner_status or repo.azure_agent_status or "unknown"
                error = repo.runner_error or repo.azure_agent_error
                service_name = repo.runner_service_name or repo.azure_agent_service_name or "API (remote)"
                error_repos.append({
                    "name": repo.name,
                    "status": status,
                    "error": error,
                    "service_name": service_name,
                    "provider": repo.provider,
                })
            
            # If no repositories have runner/agent services configured, that's not an error
            if total == 0:
                return {
                    "total_repos": 0,
                    "healthy_repos": 0,
                    "unhealthy_repos": 0,
                    "error_repos": [],
                    "overall_status": "running",  # No runner/agent services = no problems
                    "message": "No repositories have runner or agent services configured",
                    "last_updated": datetime.utcnow().isoformat()
                }
            
            return {
                "total_repos": total,
                "healthy_repos": healthy,
                "unhealthy_repos": unhealthy,
                "error_repos": error_repos,
                "overall_status": "running" if unhealthy == 0 else "error",
                "last_updated": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            logger.error(f"Error getting repository health summary: {e}")
            return {
                "total_repos": 0,
                "healthy_repos": 0,
                "unhealthy_repos": 0,
                "error_repos": [],
                "overall_status": "error",
                "last_updated": datetime.utcnow().isoformat()
            }
    
    async def check_repository_config(self, db: Session, repo: RepositoryDB) -> Dict[str, Any]:
        """Check if repository has .pr_agent.toml configuration and get effective config"""
        try:
            if repo.provider == "github":
                return await self._check_github_config(repo)
            elif repo.provider == "azure_devops":
                return await self._check_azure_config(repo)
            else:
                return {
                    "has_config": False,
                    "error": f"Unsupported provider: {repo.provider}",
                    "effective_config": None
                }
        except Exception as e:
            logger.error(f"Error checking repository config for {repo.name}: {e}")
            return {
                "has_config": False,
                "error": str(e),
                "effective_config": None
            }
    
    async def _check_github_config(self, repo: RepositoryDB) -> Dict[str, Any]:
        """Check GitHub repository configuration including .pr_agent.toml and workflow files"""
        if not repo.github_token:
            return {
                "has_config": False,
                "error": "GitHub token not configured",
                "config_details": None
            }
        
        try:
            # Extract owner/repo from repo name or URL
            if "/" in repo.name:
                owner, repo_name = repo.name.split("/", 1)
            else:
                # Try to extract from URL
                url_parts = repo.url.rstrip("/").split("/")
                if len(url_parts) >= 2:
                    owner, repo_name = url_parts[-2], url_parts[-1]
                    if repo_name.endswith(".git"):
                        repo_name = repo_name[:-4]
                else:
                    return {
                        "has_config": False,
                        "error": "Cannot parse repository owner/name",
                        "config_details": None
                    }
            
            session = await self._get_session()
            config_details = {
                "pr_agent_toml": None,
                "workflow_config": None,
                "merged_config": None
            }
            
            # Check for .pr_agent.toml file
            pr_agent_config = await self._fetch_github_file(session, repo, owner, repo_name, ".pr_agent.toml")
            if pr_agent_config:
                config_details["pr_agent_toml"] = pr_agent_config
            
            # Check for GitHub Actions workflow files
            workflow_config = await self._analyze_github_workflows(session, repo, owner, repo_name)
            if workflow_config:
                config_details["workflow_config"] = workflow_config
            
            # Merge configurations
            merged_config = await self._merge_github_configs(pr_agent_config, workflow_config)
            config_details["merged_config"] = merged_config
            
            has_config = bool(pr_agent_config or workflow_config)
            
            return {
                "has_config": has_config,
                "has_pr_agent_toml": bool(pr_agent_config),
                "has_workflow_config": bool(workflow_config),
                "error": None,
                "config_details": config_details,
                "effective_config": {
                    "config_details": config_details,
                    "merged_config": merged_config
                }
            }
            
        except Exception as e:
            logger.error(f"Error checking GitHub configuration for {repo.name}: {e}")
            return {
                "has_config": False,
                "error": str(e),
                "config_details": None
            }
    
    async def _analyze_github_workflows(self, session: aiohttp.ClientSession, repo: RepositoryDB, owner: str, repo_name: str) -> Dict[str, Any]:
        """Analyze GitHub Actions workflow files for PR-Agent configuration"""
        try:
            # Look for common PR-Agent workflow file names
            workflow_paths = [
                ".github/workflows/pr_agent.yml",
                ".github/workflows/pr-agent.yml", 
                ".github/workflows/pr_agent.yaml",
                ".github/workflows/pr-agent.yaml",
                ".github/workflows/PRAgent.yml",
                ".github/workflows/prAgent.yml"
            ]
            
            workflow_config = {
                "found_workflows": [],
                "env_variables": {},
                "secrets_used": [],
                "configuration_overrides": {}
            }
            
            for workflow_path in workflow_paths:
                workflow_content = await self._fetch_github_file(session, repo, owner, repo_name, workflow_path)
                if workflow_content:
                    # Parse YAML content
                    import yaml
                    try:
                        workflow_data = yaml.safe_load(workflow_content)
                        workflow_analysis = self._analyze_workflow_yaml(workflow_data, workflow_path)
                        
                        workflow_config["found_workflows"].append({
                            "path": workflow_path,
                            "analysis": workflow_analysis
                        })
                        
                        # Merge environment variables and secrets
                        if workflow_analysis.get("env_variables"):
                            workflow_config["env_variables"].update(workflow_analysis["env_variables"])
                        
                        if workflow_analysis.get("secrets_used"):
                            workflow_config["secrets_used"].extend(workflow_analysis["secrets_used"])
                        
                        if workflow_analysis.get("configuration_overrides"):
                            workflow_config["configuration_overrides"].update(workflow_analysis["configuration_overrides"])
                            
                    except yaml.YAMLError as e:
                        logger.warning(f"Failed to parse workflow YAML {workflow_path}: {e}")
                        continue
            
            # Remove duplicates from secrets list
            workflow_config["secrets_used"] = list(set(workflow_config["secrets_used"]))
            
            return workflow_config if workflow_config["found_workflows"] else None
            
        except Exception as e:
            logger.error(f"Error analyzing GitHub workflows: {e}")
            return None
    
    def _analyze_workflow_yaml(self, workflow_data: Dict[str, Any], workflow_path: str) -> Dict[str, Any]:
        """Analyze workflow YAML for PR-Agent configuration"""
        analysis = {
            "env_variables": {},
            "secrets_used": [],
            "configuration_overrides": {},
            "runner_config": {}
        }
        
        try:
            # Check global env section
            global_env = workflow_data.get("env", {})
            if global_env:
                analysis["env_variables"].update(global_env)
                
                # Extract secrets from environment variables
                for key, value in global_env.items():
                    if isinstance(value, str) and "${{ secrets." in value:
                        secret_name = value.split("secrets.")[1].split(" ")[0].rstrip("})")
                        analysis["secrets_used"].append(secret_name)
                        
                    # Identify PR-Agent configuration overrides
                    if key.startswith(("OPENAI_", "ANTHROPIC_", "GITHUB_", "PR_AGENT_", "CSHARP_CODE_CONTEXT_", "GITHUB_ACTION_CONFIG.")):
                        analysis["configuration_overrides"][key] = {
                            "value": "*** SECRET ***" if "${{ secrets." in str(value) else value,
                            "is_secret": "${{ secrets." in str(value),
                            "secret_name": value.split("secrets.")[1].split(" ")[0].rstrip("})") if "${{ secrets." in str(value) else None
                        }
            
            # Check job-level configurations
            jobs = workflow_data.get("jobs", {})
            for job_name, job_config in jobs.items():
                # Check job env
                job_env = job_config.get("env", {})
                if job_env:
                    analysis["env_variables"].update(job_env)
                    
                    for key, value in job_env.items():
                        if isinstance(value, str) and "${{ secrets." in value:
                            secret_name = value.split("secrets.")[1].split(" ")[0].rstrip("})")
                            analysis["secrets_used"].append(secret_name)
                            
                        if key.startswith(("OPENAI_", "ANTHROPIC_", "GITHUB_", "PR_AGENT_", "CSHARP_CODE_CONTEXT_", "GITHUB_ACTION_CONFIG.")):
                            analysis["configuration_overrides"][key] = {
                                "value": "*** SECRET ***" if "${{ secrets." in str(value) else value,
                                "is_secret": "${{ secrets." in str(value),
                                "secret_name": value.split("secrets.")[1].split(" ")[0].rstrip("})") if "${{ secrets." in str(value) else None
                            }
                
                # Check runner configuration
                runs_on = job_config.get("runs-on")
                if runs_on:
                    analysis["runner_config"]["runs_on"] = runs_on
                    analysis["runner_config"]["is_self_hosted"] = isinstance(runs_on, list) and "self-hosted" in runs_on
                
                # Check steps for dotted variables in PowerShell commands
                steps = job_config.get("steps", [])
                for step in steps:
                    if (step.get("name") == "Export environment variables with dots" and 
                        step.get("shell") == "powershell" and 
                        "run" in step):
                        
                        # Parse the PowerShell commands to extract dotted variables
                        run_script = step["run"]
                        import re
                        for line in run_script.split('\n'):
                            match = re.match(r'^\s*Add-Content\s+\$env:GITHUB_ENV\s+"([^=]+)=([^"]*)"', line)
                            if match:
                                key = match.group(1)
                                value = match.group(2)
                                
                                # Add to env_variables
                                analysis["env_variables"][key] = value
                                
                                # Add to configuration_overrides if it's a PR-Agent config
                                if key.startswith(("OPENAI_", "ANTHROPIC_", "GITHUB_", "PR_AGENT_", "CSHARP_CODE_CONTEXT_", "GITHUB_ACTION_CONFIG.")):
                                    analysis["configuration_overrides"][key] = {
                                        "value": "*** SECRET ***" if "${{ secrets." in str(value) else value,
                                        "is_secret": "${{ secrets." in str(value),
                                        "secret_name": value.split("secrets.")[1].split(" ")[0].rstrip("})") if "${{ secrets." in str(value) else None
                                    }
        
        except Exception as e:
            logger.error(f"Error analyzing workflow YAML structure: {e}")
        
        return analysis
    
    async def _merge_github_configs(self, pr_agent_config: str, workflow_config: Dict[str, Any]) -> Dict[str, Any]:
        """Merge .pr_agent.toml and workflow environment variable configurations"""
        merged = {
            "sources": [],
            "final_config": {},
            "overrides": {}
        }
        
        try:
            # Parse .pr_agent.toml if present
            if pr_agent_config:
                import toml
                try:
                    toml_config = toml.loads(pr_agent_config)
                    merged["sources"].append("pr_agent.toml")
                    merged["final_config"].update(toml_config)
                except Exception as e:
                    logger.warning(f"Failed to parse .pr_agent.toml: {e}")
            
            # Apply workflow environment variable overrides
            if workflow_config and workflow_config.get("configuration_overrides"):
                merged["sources"].append("github_workflows")
                
                for env_key, env_info in workflow_config["configuration_overrides"].items():
                    # Convert environment variable names to TOML-style config keys
                    config_key = self._env_to_config_key(env_key)
                    if config_key:
                        merged["overrides"][config_key] = {
                            "env_var": env_key,
                            "value": env_info["value"],
                            "is_secret": env_info["is_secret"],
                            "secret_name": env_info.get("secret_name")
                        }
                        
                        # Don't include actual secret values in final config
                        if not env_info["is_secret"]:
                            merged["final_config"][config_key] = env_info["value"]
        
        except Exception as e:
            logger.error(f"Error merging GitHub configurations: {e}")
        
        return merged
    
    def _env_to_config_key(self, env_key: str) -> str:
        """Convert environment variable name to PR-Agent config key format"""
        # Common environment variable to config mappings
        env_mappings = {
            "OPENAI_KEY": "openai.key",
            "ANTHROPIC_KEY": "anthropic.key", 
            "ANTHROPIC__KEY": "anthropic.key",
            "GITHUB_TOKEN": "github.user_token",
            "PR_AGENT_CONFIG.AUTO_IMPROVE": "pr_code_suggestions.auto_improve",
            "GITHUB_ACTION_CONFIG.AUTO_IMPROVE": "pr_code_suggestions.auto_improve",
            "CSHARP_CODE_CONTEXT_SERVICE__BASE_URL": "code_context.base_url",
            "CSHARP_CODE_CONTEXT_SERVICE__USERNAME": "code_context.username",
            "CSHARP_CODE_CONTEXT_SERVICE__PASSWORD": "code_context.password"
        }
        
        return env_mappings.get(env_key, env_key.lower().replace("__", ".").replace("_", "."))
    
    async def _fetch_github_file(self, session: aiohttp.ClientSession, repo: RepositoryDB, owner: str, repo_name: str, file_path: str) -> str:
        """Fetch a file from GitHub repository"""
        try:
            # Construct the full URL for the file
            url = f"https://api.github.com/repos/{owner}/{repo_name}/contents/{file_path}"
            headers = {
                "Authorization": f"Bearer {repo.github_token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "PR-Agent-Dashboard/1.0"
            }
            
            async with session.get(url, headers=headers) as response:
                if response.status == 404:
                    return None
                elif response.status == 401:
                    return None
                elif response.status == 403:
                    return None
                elif response.status != 200:
                    return None
                
                data = await response.json()
                content_b64 = data.get("content", "")
                
                if not content_b64:
                    return None
                
                # Decode base64 content
                content = base64.b64decode(content_b64).decode('utf-8')
                
                return content
        
        except aiohttp.ClientError as e:
            logger.error(f"Network error: {str(e)}")
            return None
        
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            return None
    
    async def _check_azure_config(self, repo: RepositoryDB) -> Dict[str, Any]:
        """Check Azure DevOps repository for .pr_agent.toml configuration"""
        if not repo.azure_pat:
            return {
                "has_config": False,
                "error": "Azure DevOps PAT not configured",
                "effective_config": None
            }
        
        try:
            # Extract organization and project from repo URL or config
            organization = None
            project = None
            repo_name = None
            
            # Try to get from repo config first
            if repo.config and isinstance(repo.config, dict):
                organization = repo.config.get("azure_organization")
                project = repo.config.get("azure_project")
                repo_name = repo.config.get("azure_repository")
            
            # If not in config, try to parse from URL
            if not all([organization, project, repo_name]):
                # Azure DevOps URLs: https://dev.azure.com/org/project/_git/repo
                if "dev.azure.com" in repo.url:
                    url_parts = repo.url.split("/")
                    if len(url_parts) >= 6:
                        organization = url_parts[3]
                        project = url_parts[4]
                        repo_name = url_parts[6] if url_parts[5] == "_git" else url_parts[5]
                elif ".visualstudio.com" in repo.url:
                    # Legacy format: https://org.visualstudio.com/project/_git/repo
                    url_parts = repo.url.split("/")
                    if len(url_parts) >= 5:
                        organization = url_parts[2].split(".")[0]
                        project = url_parts[3]
                        repo_name = url_parts[5] if url_parts[4] == "_git" else url_parts[4]
            
            if not all([organization, project, repo_name]):
                return {
                    "has_config": False,
                    "error": "Cannot determine Azure organization/project/repository from URL or config",
                    "effective_config": None
                }
            
            session = await self._get_session()
            
            # Check for .pr_agent.toml file in the repository
            url = f"https://dev.azure.com/{organization}/{project}/_apis/git/repositories/{repo_name}/items?path=/.pr_agent.toml&api-version=7.0"
            headers = {
                "Authorization": f"Basic {base64.b64encode(f':{repo.azure_pat}'.encode()).decode()}",
                "Content-Type": "application/json"
            }
            
            async with session.get(url, headers=headers) as response:
                if response.status == 404:
                    return {
                        "has_config": False,
                        "error": None,
                        "effective_config": None
                    }
                elif response.status == 401:
                    return {
                        "has_config": False,
                        "error": "Azure DevOps PAT is invalid or expired",
                        "effective_config": None
                    }
                elif response.status == 403:
                    return {
                        "has_config": False,
                        "error": "Azure DevOps PAT lacks required permissions",
                        "effective_config": None
                    }
                elif response.status != 200:
                    return {
                        "has_config": False,
                        "error": f"Azure DevOps API error: {response.status}",
                        "effective_config": None
                    }
                
                # File exists, get its content
                content = await response.text()
                
                try:
                    # Parse TOML
                    repo_config = toml.loads(content)
                    
                    # Get system config to merge
                    effective_config = await self._merge_configs(repo_config)
                    
                    return {
                        "has_config": True,
                        "error": None,
                        "effective_config": effective_config,
                        "repo_config": repo_config
                    }
                    
                except Exception as e:
                    return {
                        "has_config": True,
                        "error": f"Failed to parse .pr_agent.toml: {str(e)}",
                        "effective_config": None
                    }
        
        except aiohttp.ClientError as e:
            return {
                "has_config": False,
                "error": f"Network error: {str(e)}",
                "effective_config": None
            }
        except Exception as e:
            return {
                "has_config": False,
                "error": f"Unexpected error: {str(e)}",
                "effective_config": None
            }
    
    async def _merge_configs(self, repo_config: Dict[str, Any]) -> Dict[str, Any]:
        """Merge repository config with system config, highlighting overrides"""
        try:
            # Get system configuration
            from services.config_service import ConfigService
            from database import DatabaseManager
            
            db_manager = DatabaseManager()
            config_service = ConfigService(db_manager)
            system_config = await config_service.get_config()
            
            # Create effective config by merging
            effective_config = {
                "system_config": system_config,
                "repository_overrides": repo_config,
                "merged_config": {},
                "override_keys": []
            }
            
            # Deep merge configs with tracking of overrides
            def merge_dict(base, override, path=""):
                merged = base.copy() if isinstance(base, dict) else base
                
                if isinstance(override, dict) and isinstance(merged, dict):
                    for key, value in override.items():
                        current_path = f"{path}.{key}" if path else key
                        if key in merged and isinstance(merged[key], dict) and isinstance(value, dict):
                            merged[key] = merge_dict(merged[key], value, current_path)
                        else:
                            if key in merged and merged[key] != value:
                                effective_config["override_keys"].append(current_path)
                            merged[key] = value
                else:
                    merged = override
                    if path and base != override:
                        effective_config["override_keys"].append(path)
                
                return merged
            
            effective_config["merged_config"] = merge_dict(system_config, repo_config)
            
            return effective_config
            
        except Exception as e:
            logger.error(f"Error merging configs: {e}")
            return {
                "system_config": {},
                "repository_overrides": repo_config,
                "merged_config": repo_config,
                "override_keys": [],
                "error": f"Failed to load system config: {str(e)}"
            }
    
    async def update_all_repository_configs(self, db: Session) -> Dict[str, Any]:
        """Update configuration status for all active repositories"""
        try:
            repositories = db.query(RepositoryDB).filter(RepositoryDB.is_active == True).all()
            
            results = {
                "total_repos": len(repositories),
                "repos_with_config": 0,
                "repos_without_config": 0,
                "config_errors": [],
                "last_updated": datetime.utcnow().isoformat()
            }
            
            # Check each repository
            for repo in repositories:
                config_result = await self.check_repository_config(db, repo)
                
                # Update repository with config status
                repo.has_pr_agent_config = config_result.get("has_pr_agent_toml", False)
                repo.has_workflow_config = config_result.get("has_workflow_config", False)
                repo.config_last_checked = datetime.utcnow()
                repo.effective_config = config_result.get("effective_config")
                
                # Update counters
                if config_result["has_config"]:
                    results["repos_with_config"] += 1
                else:
                    results["repos_without_config"] += 1
                
                # Track errors
                if config_result.get("error"):
                    results["config_errors"].append({
                        "name": repo.name,
                        "error": config_result["error"]
                    })
            
            # Commit all updates
            db.commit()
            
            return results
            
        except Exception as e:
            logger.error(f"Error updating repository configs: {e}")
            db.rollback()
            raise Exception(f"Failed to update repository configs: {str(e)}") 