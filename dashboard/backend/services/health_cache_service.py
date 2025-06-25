"""
Health Cache Service - Manages persistent health state caching
"""
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from models import HealthCacheDB, HealthCache
import logging

logger = logging.getLogger(__name__)

class HealthCacheService:
    """Service for managing health status caching"""
    
    def __init__(self):
        pass
    
    async def get_cached_health_status(self, db: Session, service_name: str) -> Optional[HealthCache]:
        """Get cached health status for a service"""
        try:
            cached = db.query(HealthCacheDB).filter(HealthCacheDB.service_name == service_name).first()
            if cached:
                return HealthCache(
                    id=cached.id,
                    service_name=cached.service_name,
                    status=cached.status,
                    message=cached.message,
                    error_details=cached.error_details,
                    endpoint=cached.endpoint,
                    last_checked=cached.last_checked.isoformat() if cached.last_checked else None,
                    is_checking=cached.is_checking,
                    check_count=cached.check_count,
                    details=cached.details,
                    created_at=cached.created_at.isoformat() if cached.created_at else None,
                    updated_at=cached.updated_at.isoformat() if cached.updated_at else None
                )
            return None
        except Exception as e:
            logger.error(f"Error getting cached health status for {service_name}: {e}")
            return None
    
    async def get_all_cached_health_status(self, db: Session) -> Dict[str, HealthCache]:
        """Get all cached health statuses"""
        try:
            cached_statuses = db.query(HealthCacheDB).all()
            result = {}
            for status in cached_statuses:
                result[status.service_name] = HealthCache(
                    id=status.id,
                    service_name=status.service_name,
                    status=status.status,
                    message=status.message,
                    error_details=status.error_details,
                    endpoint=status.endpoint,
                    last_checked=status.last_checked.isoformat() if status.last_checked else None,
                    is_checking=status.is_checking,
                    check_count=status.check_count,
                    details=status.details,
                    created_at=status.created_at.isoformat() if status.created_at else None,
                    updated_at=status.updated_at.isoformat() if status.updated_at else None
                )
            return result
        except Exception as e:
            logger.error(f"Error getting all cached health statuses: {e}")
            return {}
    
    async def update_health_cache(self, db: Session, service_name: str, health_data: Dict[str, Any]) -> HealthCache:
        """Update cached health status for a service"""
        try:
            # Get or create cache entry
            cached = db.query(HealthCacheDB).filter(HealthCacheDB.service_name == service_name).first()
            
            if not cached:
                cached = HealthCacheDB(service_name=service_name)
                db.add(cached)
            
            # Update fields
            cached.status = health_data.get('status', 'unknown')
            cached.message = health_data.get('message', '')
            cached.error_details = health_data.get('error_details')
            cached.endpoint = health_data.get('endpoint')
            cached.details = health_data.get('details', {})
            cached.last_checked = datetime.utcnow()
            cached.is_checking = False
            cached.check_count += 1
            cached.updated_at = datetime.utcnow()
            
            db.commit()
            db.refresh(cached)
            
            return HealthCache(
                id=cached.id,
                service_name=cached.service_name,
                status=cached.status,
                message=cached.message,
                error_details=cached.error_details,
                endpoint=cached.endpoint,
                last_checked=cached.last_checked.isoformat() if cached.last_checked else None,
                is_checking=cached.is_checking,
                check_count=cached.check_count,
                details=cached.details,
                created_at=cached.created_at.isoformat() if cached.created_at else None,
                updated_at=cached.updated_at.isoformat() if cached.updated_at else None
            )
            
        except Exception as e:
            logger.error(f"Error updating health cache for {service_name}: {e}")
            db.rollback()
            raise
    
    async def set_checking_status(self, db: Session, service_name: str, is_checking: bool = True):
        """Set the checking status for a service"""
        try:
            cached = db.query(HealthCacheDB).filter(HealthCacheDB.service_name == service_name).first()
            
            if not cached:
                cached = HealthCacheDB(
                    service_name=service_name,
                    status='checking' if is_checking else 'unknown',
                    message='Initial health check...' if is_checking else 'No data available'
                )
                db.add(cached)
            
            cached.is_checking = is_checking
            cached.updated_at = datetime.utcnow()
            
            db.commit()
            db.refresh(cached)
            
            return HealthCache(
                id=cached.id,
                service_name=cached.service_name,
                status=cached.status,
                message=cached.message,
                error_details=cached.error_details,
                endpoint=cached.endpoint,
                last_checked=cached.last_checked.isoformat() if cached.last_checked else None,
                is_checking=cached.is_checking,
                check_count=cached.check_count,
                details=cached.details,
                created_at=cached.created_at.isoformat() if cached.created_at else None,
                updated_at=cached.updated_at.isoformat() if cached.updated_at else None
            )
            
        except Exception as e:
            logger.error(f"Error setting checking status for {service_name}: {e}")
            db.rollback()
            raise
    
    async def initialize_default_services(self, db: Session):
        """Initialize default service entries in cache"""
        default_services = [
            'database',
            'context_service', 
            'repositories',
            'pr_agent_config'
        ]
        
        for service_name in default_services:
            try:
                existing = db.query(HealthCacheDB).filter(HealthCacheDB.service_name == service_name).first()
                if not existing:
                    cache_entry = HealthCacheDB(
                        service_name=service_name,
                        status='unknown',
                        message='Waiting for initial health check...',
                        is_checking=False,
                        check_count=0
                    )
                    db.add(cache_entry)
            except Exception as e:
                logger.error(f"Error initializing default service {service_name}: {e}")
        
        try:
            db.commit()
        except Exception as e:
            logger.error(f"Error committing default services: {e}")
            db.rollback() 