import asyncio
import logging
from typing import Dict, List, Optional, Tuple, Any
from datetime import datetime, timedelta
import aiohttp
import subprocess
import json
import os
import base64
import toml
from sqlalchemy.orm import Session

from models import RepositoryDB

logger = logging.getLogger(__name__)

class RunnerHealthService:
    """Service for checking the health of GitHub self-hosted runners and Azure DevOps agents"""
    
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
    
    async def check_repository_runner_health(self, db: Session, repo: RepositoryDB) -> Dict[str, Any]:
        """Check runner health for a specific repository"""
        try:
            if repo.provider == "github":
                return await self._check_github_runner(repo)
            elif repo.provider == "azure_devops":
                return await self._check_azure_agent(repo)
            else:
                return {
                    "status": "unknown",
                    "error": f"Unsupported provider: {repo.provider}",
                    "last_seen": None
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
            
            # Check self-hosted runners for the repository
            url = f"https://api.github.com/repos/{owner}/{repo_name}/actions/runners"
            headers = {
                "Authorization": f"Bearer {repo.github_token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "PR-Agent-Dashboard/1.0"
            }
            
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
                        "error": "GitHub token lacks required permissions",
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
                
                # Find the most recently active runner
                most_recent = None
                for runner in online_runners:
                    if runner.get("status") == "online":
                        # GitHub doesn't provide last_seen, but we can assume online = recent
                        most_recent = datetime.utcnow()
                        break
                
                return {
                    "status": "running",
                    "error": None,
                    "last_seen": most_recent,
                    "details": f"{len(online_runners)}/{len(runners)} runners online"
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
            
            # Get agent pools first
            url = f"https://dev.azure.com/{organization}/_apis/distributedtask/pools?api-version=7.0"
            headers = {
                "Authorization": f"Basic {repo.azure_pat}",
                "Content-Type": "application/json"
            }
            
            async with session.get(url, headers=headers) as response:
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
                elif response.status != 200:
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
    
    async def check_all_repositories(self, db: Session) -> Dict[str, Any]:
        """Check runner health for all active repositories"""
        try:
            repositories = db.query(RepositoryDB).filter(RepositoryDB.is_active == True).all()
            
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
                
                # Update repository with health status
                repo.runner_status = health_result["status"]
                repo.runner_error = health_result["error"]
                if health_result["last_seen"]:
                    repo.runner_last_seen = health_result["last_seen"]
                
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
    
    async def get_repository_health_summary(self, db: Session) -> Dict[str, Any]:
        """Get a summary of repository health status"""
        try:
            repositories = db.query(RepositoryDB).filter(RepositoryDB.is_active == True).all()
            
            total = len(repositories)
            healthy = len([r for r in repositories if r.runner_status == "running"])
            unhealthy = total - healthy
            
            # Get error details
            error_repos = []
            for repo in repositories:
                if repo.runner_status != "running":
                    error_repos.append({
                        "name": repo.name,
                        "status": repo.runner_status or "unknown",
                        "error": repo.runner_error
                    })
            
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
        """Check GitHub repository for .pr_agent.toml configuration"""
        if not repo.github_token:
            return {
                "has_config": False,
                "error": "GitHub token not configured",
                "effective_config": None
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
                        "effective_config": None
                    }
            
            session = await self._get_session()
            
            # Check for .pr_agent.toml file in the repository
            url = f"https://api.github.com/repos/{owner}/{repo_name}/contents/.pr_agent.toml"
            headers = {
                "Authorization": f"Bearer {repo.github_token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "PR-Agent-Dashboard/1.0"
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
                        "error": "GitHub token is invalid or expired",
                        "effective_config": None
                    }
                elif response.status == 403:
                    return {
                        "has_config": False,
                        "error": "GitHub token lacks required permissions",
                        "effective_config": None
                    }
                elif response.status != 200:
                    return {
                        "has_config": False,
                        "error": f"GitHub API error: {response.status}",
                        "effective_config": None
                    }
                
                # File exists, get its content
                data = await response.json()
                content_b64 = data.get("content", "")
                
                try:
                    # Decode base64 content
                    content = base64.b64decode(content_b64).decode('utf-8')
                    
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
                repo.has_pr_agent_config = config_result["has_config"]
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