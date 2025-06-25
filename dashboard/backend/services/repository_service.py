from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
import logging

from models import RepositoryDB, Repository, RepositoryCreate, RepositoryUpdate, APIResponse

logger = logging.getLogger(__name__)

class RepositoryService:
    """Service for managing repository monitoring configuration"""
    
    async def get_repositories(self, db: Session, limit: int = 100, provider: Optional[str] = None, active_only: bool = False) -> APIResponse:
        """Get all repositories with optional filtering"""
        try:
            query = db.query(RepositoryDB)
            
            # Apply filters
            if provider:
                query = query.filter(RepositoryDB.provider == provider)
            
            if active_only:
                query = query.filter(RepositoryDB.is_active == True)
            
            # Order by most recently updated
            query = query.order_by(desc(RepositoryDB.updated_at))
            
            # Apply limit
            repositories = query.limit(limit).all()
            
            # Convert to Pydantic models
            repo_list = []
            for repo in repositories:
                repo_dict = {
                    "id": repo.id,
                    "name": repo.name,
                    "provider": repo.provider,
                    "url": repo.url,
                    "is_active": repo.is_active,
                    "config": repo.config,
                    # Access tokens are never exposed in API responses for security
                    "runner_status": repo.runner_status,
                    "runner_last_seen": repo.runner_last_seen.isoformat() if repo.runner_last_seen else None,
                    "runner_error": repo.runner_error,
                    "has_pr_agent_config": repo.has_pr_agent_config,
                    "config_last_checked": repo.config_last_checked.isoformat() if repo.config_last_checked else None,
                    "effective_config": repo.effective_config,
                    "monitor_prs": repo.monitor_prs,
                    "monitor_issues": repo.monitor_issues,
                    "auto_review": repo.auto_review,
                    "auto_describe": repo.auto_describe,
                    "auto_improve": repo.auto_improve,
                    "created_at": repo.created_at.isoformat() if repo.created_at else None,
                    "updated_at": repo.updated_at.isoformat() if repo.updated_at else None,
                    "last_activity": repo.last_activity.isoformat() if repo.last_activity else None
                }
                repo_list.append(Repository(**repo_dict))
            
            return APIResponse(
                data=repo_list,
                total=len(repo_list),
                message=f"Found {len(repo_list)} repositories"
            )
            
        except Exception as e:
            logger.error(f"Error fetching repositories: {e}")
            raise Exception(f"Failed to fetch repositories: {str(e)}")
    
    async def get_repository(self, db: Session, repo_id: int) -> Optional[Repository]:
        """Get a specific repository by ID"""
        try:
            repo = db.query(RepositoryDB).filter(RepositoryDB.id == repo_id).first()
            if not repo:
                return None
            
            return Repository(
                id=repo.id,
                name=repo.name,
                provider=repo.provider,
                url=repo.url,
                is_active=repo.is_active,
                config=repo.config,
                runner_status=repo.runner_status,
                runner_last_seen=repo.runner_last_seen.isoformat() if repo.runner_last_seen else None,
                runner_error=repo.runner_error,
                has_pr_agent_config=repo.has_pr_agent_config,
                config_last_checked=repo.config_last_checked.isoformat() if repo.config_last_checked else None,
                effective_config=repo.effective_config,
                monitor_prs=repo.monitor_prs,
                monitor_issues=repo.monitor_issues,
                auto_review=repo.auto_review,
                auto_describe=repo.auto_describe,
                auto_improve=repo.auto_improve,
                created_at=repo.created_at.isoformat() if repo.created_at else None,
                updated_at=repo.updated_at.isoformat() if repo.updated_at else None,
                last_activity=repo.last_activity.isoformat() if repo.last_activity else None
            )
            
        except Exception as e:
            logger.error(f"Error fetching repository {repo_id}: {e}")
            raise Exception(f"Failed to fetch repository: {str(e)}")
    
    async def create_repository(self, db: Session, repo_data: RepositoryCreate) -> Repository:
        """Create a new repository"""
        try:
            # Check if repository already exists
            existing = db.query(RepositoryDB).filter(RepositoryDB.name == repo_data.name).first()
            if existing:
                raise Exception(f"Repository '{repo_data.name}' already exists")
            
            # Create new repository
            db_repo = RepositoryDB(
                name=repo_data.name,
                provider=repo_data.provider.value,
                url=repo_data.url,
                is_active=repo_data.is_active,
                config=repo_data.config,
                github_token=repo_data.github_token,
                azure_pat=repo_data.azure_pat,
                runner_status="unknown",  # Will be updated by health checks
                monitor_prs=repo_data.monitor_prs,
                monitor_issues=repo_data.monitor_issues,
                auto_review=repo_data.auto_review,
                auto_describe=repo_data.auto_describe,
                auto_improve=repo_data.auto_improve,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow()
            )
            
            db.add(db_repo)
            db.commit()
            db.refresh(db_repo)
            
            return Repository(
                id=db_repo.id,
                name=db_repo.name,
                provider=db_repo.provider,
                url=db_repo.url,
                is_active=db_repo.is_active,
                config=db_repo.config,
                runner_status=db_repo.runner_status,
                runner_last_seen=db_repo.runner_last_seen.isoformat() if db_repo.runner_last_seen else None,
                runner_error=db_repo.runner_error,
                has_pr_agent_config=db_repo.has_pr_agent_config,
                config_last_checked=db_repo.config_last_checked.isoformat() if db_repo.config_last_checked else None,
                effective_config=db_repo.effective_config,
                monitor_prs=db_repo.monitor_prs,
                monitor_issues=db_repo.monitor_issues,
                auto_review=db_repo.auto_review,
                auto_describe=db_repo.auto_describe,
                auto_improve=db_repo.auto_improve,
                created_at=db_repo.created_at.isoformat(),
                updated_at=db_repo.updated_at.isoformat(),
                last_activity=db_repo.last_activity.isoformat() if db_repo.last_activity else None
            )
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error creating repository: {e}")
            raise Exception(f"Failed to create repository: {str(e)}")
    
    async def update_repository(self, db: Session, repo_id: int, repo_update: RepositoryUpdate) -> Optional[Repository]:
        """Update an existing repository"""
        try:
            repo = db.query(RepositoryDB).filter(RepositoryDB.id == repo_id).first()
            if not repo:
                return None
            
            # Update fields that are provided
            update_data = repo_update.dict(exclude_unset=True)
            for field, value in update_data.items():
                if hasattr(repo, field):
                    if field == 'provider' and value:
                        setattr(repo, field, value.value)
                    else:
                        setattr(repo, field, value)
            
            repo.updated_at = datetime.utcnow()
            
            db.commit()
            db.refresh(repo)
            
            return Repository(
                id=repo.id,
                name=repo.name,
                provider=repo.provider,
                url=repo.url,
                is_active=repo.is_active,
                config=repo.config,
                runner_status=repo.runner_status,
                runner_last_seen=repo.runner_last_seen.isoformat() if repo.runner_last_seen else None,
                runner_error=repo.runner_error,
                has_pr_agent_config=repo.has_pr_agent_config,
                config_last_checked=repo.config_last_checked.isoformat() if repo.config_last_checked else None,
                effective_config=repo.effective_config,
                monitor_prs=repo.monitor_prs,
                monitor_issues=repo.monitor_issues,
                auto_review=repo.auto_review,
                auto_describe=repo.auto_describe,
                auto_improve=repo.auto_improve,
                created_at=repo.created_at.isoformat() if repo.created_at else None,
                updated_at=repo.updated_at.isoformat() if repo.updated_at else None,
                last_activity=repo.last_activity.isoformat() if repo.last_activity else None
            )
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error updating repository {repo_id}: {e}")
            raise Exception(f"Failed to update repository: {str(e)}")
    
    async def delete_repository(self, db: Session, repo_id: int) -> bool:
        """Delete a repository"""
        try:
            repo = db.query(RepositoryDB).filter(RepositoryDB.id == repo_id).first()
            if not repo:
                return False
            
            db.delete(repo)
            db.commit()
            return True
            
        except Exception as e:
            db.rollback()
            logger.error(f"Error deleting repository {repo_id}: {e}")
            raise Exception(f"Failed to delete repository: {str(e)}")
    
    async def get_repository_names(self, db: Session, active_only: bool = True) -> List[str]:
        """Get list of repository names for filtering"""
        try:
            query = db.query(RepositoryDB.name)
            
            if active_only:
                query = query.filter(RepositoryDB.is_active == True)
            
            repositories = query.distinct().all()
            return [repo.name for repo in repositories]
            
        except Exception as e:
            logger.error(f"Error fetching repository names: {e}")
            return []
    
    async def update_repository_activity(self, db: Session, repo_name: str) -> None:
        """Update the last activity timestamp for a repository"""
        try:
            repo = db.query(RepositoryDB).filter(RepositoryDB.name == repo_name).first()
            if repo:
                repo.last_activity = datetime.utcnow()
                db.commit()
                
        except Exception as e:
            logger.error(f"Error updating repository activity for {repo_name}: {e}") 