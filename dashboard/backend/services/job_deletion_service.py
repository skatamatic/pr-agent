"""
Job Deletion Service - Handles deletion of individual jobs and related data
"""
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from models import JobDB, OperationDB, LogEntryDB, MetricsAggregateDB
from services.metrics_service import MetricsService

logger = logging.getLogger(__name__)

class JobDeletionService:
    """Service for deleting individual jobs and their related data"""
    
    def __init__(self, database_manager, metrics_service: MetricsService = None):
        self.database_manager = database_manager
        self.metrics_service = metrics_service or MetricsService()
    
    async def get_job_deletion_preview(self, job_id: str) -> Dict[str, Any]:
        """Get preview of what will be deleted with a specific job"""
        try:
            with self.database_manager.get_session() as db:
                # Get job details
                job = db.query(JobDB).filter(JobDB.job_id == job_id).first()
                if not job:
                    raise ValueError(f"Job {job_id} not found")
                
                # Count related data
                operations_count = db.query(OperationDB).filter(
                    OperationDB.job_id == job_id
                ).count()
                
                logs_count = db.query(LogEntryDB).filter(
                    LogEntryDB.job_id == job_id
                ).count()
                
                # Calculate cost impact
                cost_impact = await self._calculate_job_cost_impact(db, job_id)
                
                return {
                    "job_id": job_id,
                    "job_type": job.job_type,
                    "repository": job.repository,
                    "status": job.status,
                    "started_at": job.started_at.isoformat() if job.started_at else None,
                    "operations_count": operations_count,
                    "logs_count": logs_count,
                    "cost_impact": cost_impact,
                    "can_delete": True
                }
                
        except Exception as e:
            logger.error(f"Error getting job deletion preview for {job_id}: {e}")
            raise
    
    async def delete_job_and_related_data(self, job_id: str) -> Dict[str, Any]:
        """Delete a specific job and all its related data"""
        try:
            with self.database_manager.get_session() as db:
                # Get job details first
                job = db.query(JobDB).filter(JobDB.job_id == job_id).first()
                if not job:
                    raise ValueError(f"Job {job_id} not found")
                
                repository = job.repository
                
                # Calculate cost impact before deletion
                cost_impact = await self._calculate_job_cost_impact(db, job_id)
                
                try:
                    # Delete in order: operations -> logs -> job
                    operations_deleted = db.query(OperationDB).filter(
                        OperationDB.job_id == job_id
                    ).delete(synchronize_session=False)
                    
                    logs_deleted = db.query(LogEntryDB).filter(
                        LogEntryDB.job_id == job_id
                    ).delete(synchronize_session=False)
                    
                    job_deleted = db.query(JobDB).filter(
                        JobDB.job_id == job_id
                    ).delete(synchronize_session=False)
                    
                    db.commit()
                    
                    # Recalculate global metrics after job deletion
                    await self.metrics_service.recalculate_metrics_from_operations(db)
                    
                    logger.info(f"Deleted job {job_id}: {operations_deleted} operations, {logs_deleted} logs")
                    
                    return {
                        "job_id": job_id,
                        "operations_deleted": operations_deleted,
                        "logs_deleted": logs_deleted,
                        "job_deleted": job_deleted,
                        "cost_impact": cost_impact,
                        "repository": repository
                    }
                    
                except Exception as e:
                    db.rollback()
                    logger.error(f"Database error during job deletion {job_id}: {e}")
                    raise
                
        except ValueError:
            # Re-raise ValueError as-is (job not found)
            raise
        except Exception as e:
            logger.error(f"Error deleting job {job_id}: {e}")
            raise
    
    async def _calculate_job_cost_impact(self, db: Session, job_id: str) -> float:
        """Calculate the cost impact of deleting a specific job"""
        try:
            # Get all operations for this job
            operations = db.query(OperationDB).filter(
                OperationDB.job_id == job_id
            ).all()
            
            total_cost = 0.0
            
            for operation in operations:
                # Use multi-model data if available, otherwise fall back to legacy
                final_input_tokens = operation.total_input_tokens if operation.total_input_tokens else (operation.input_tokens or 0)
                final_output_tokens = operation.total_output_tokens if operation.total_output_tokens else (operation.output_tokens or 0)
                
                if final_input_tokens and final_output_tokens:
                    config = await self.metrics_service.get_or_create_config(db)
                    
                    # Handle multi-model data (preferred)
                    if operation.ai_models_used and isinstance(operation.ai_models_used, dict):
                        for model_name, model_tokens in operation.ai_models_used.items():
                            model_costs = config.model_costs.get(model_name, {})
                            if model_costs:
                                input_cost = (model_tokens.get('input_tokens', 0) / 1000) * model_costs.get('input', 0)
                                output_cost = (model_tokens.get('output_tokens', 0) / 1000) * model_costs.get('output', 0)
                                total_cost += input_cost + output_cost
                    # Handle legacy single-model data (fallback)
                    elif operation.model_used:
                        model_costs = config.model_costs.get(operation.model_used, {})
                        if model_costs:
                            input_cost = (final_input_tokens / 1000) * model_costs.get('input', 0)
                            output_cost = (final_output_tokens / 1000) * model_costs.get('output', 0)
                            total_cost += input_cost + output_cost
            
            return round(total_cost, 2)
            
        except Exception as e:
            logger.warning(f"Error calculating cost impact for job {job_id}: {e}")
            return 0.0
    
