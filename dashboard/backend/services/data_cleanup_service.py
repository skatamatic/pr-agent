"""
Data Cleanup Service - Handles bulk cleanup of old data from all systems
"""
import logging
from datetime import datetime
from typing import Dict, Any, Optional, List
from sqlalchemy.orm import Session
from sqlalchemy import and_, func
from models import JobDB, OperationDB, LogEntryDB, NotificationEventDB, MetricsAggregateDB
from services.metrics_service import MetricsService
from services.retention_service import RetentionService

logger = logging.getLogger(__name__)

class DataCleanupService:
    """Service for cleaning up old data from all systems"""
    
    def __init__(self, database_manager, metrics_service: MetricsService = None, retention_service: RetentionService = None, cached_job_service=None):
        self.database_manager = database_manager
        self.metrics_service = metrics_service or MetricsService()
        self.retention_service = retention_service or RetentionService(database_manager)
        self.cached_job_service = cached_job_service
    
    async def get_cleanup_preview(self, cutoff_date: datetime, repository: str = None) -> Dict[str, Any]:
        """Get preview of what will be cleaned up with cost and storage impact"""
        try:
            with self.database_manager.SessionLocal() as db:
                # Count records to be deleted (using correct date fields for each table)
                operations_query = db.query(OperationDB).filter(OperationDB.started_at < cutoff_date)
                if repository:
                    operations_query = operations_query.filter(OperationDB.repo == repository)
                operations_count = operations_query.count()
                
                jobs_query = db.query(JobDB).filter(JobDB.started_at < cutoff_date)
                if repository:
                    jobs_query = jobs_query.filter(JobDB.repository == repository)
                jobs_count = jobs_query.count()
                
                logs_query = db.query(LogEntryDB).filter(LogEntryDB.timestamp < cutoff_date)
                if repository:
                    logs_query = logs_query.filter(LogEntryDB.repo == repository)
                logs_count = logs_query.count()
                
                notification_events_query = db.query(NotificationEventDB).filter(NotificationEventDB.timestamp < cutoff_date)
                if repository:
                    notification_events_query = notification_events_query.filter(NotificationEventDB.repositories.contains([repository]))
                notification_events_count = notification_events_query.count()
                
                # Count remaining records
                remaining_operations_query = db.query(OperationDB).filter(OperationDB.started_at >= cutoff_date)
                if repository:
                    remaining_operations_query = remaining_operations_query.filter(OperationDB.repo == repository)
                remaining_operations = remaining_operations_query.count()
                
                remaining_jobs_query = db.query(JobDB).filter(JobDB.started_at >= cutoff_date)
                if repository:
                    remaining_jobs_query = remaining_jobs_query.filter(JobDB.repository == repository)
                remaining_jobs = remaining_jobs_query.count()
                
                remaining_logs_query = db.query(LogEntryDB).filter(LogEntryDB.timestamp >= cutoff_date)
                if repository:
                    remaining_logs_query = remaining_logs_query.filter(LogEntryDB.repo == repository)
                remaining_logs = remaining_logs_query.count()
                
                remaining_notification_events_query = db.query(NotificationEventDB).filter(NotificationEventDB.timestamp >= cutoff_date)
                if repository:
                    remaining_notification_events_query = remaining_notification_events_query.filter(NotificationEventDB.repositories.contains([repository]))
                remaining_notification_events = remaining_notification_events_query.count()
                
                # Calculate cost impact
                current_cost_savings = await self._get_current_cost_savings(db, repository)
                remaining_cost_savings = await self._get_remaining_cost_savings(db, cutoff_date, repository)
                cost_impact = remaining_cost_savings - current_cost_savings
                
                # Calculate storage impact (rough estimate)
                storage_impact = await self._calculate_storage_impact(db, cutoff_date, repository)
                
                return {
                    "cutoff_date": cutoff_date.isoformat(),
                    "repository": repository,
                    "before_cleanup": {
                        "operations": operations_count + remaining_operations,
                        "jobs": jobs_count + remaining_jobs,
                        "logs": logs_count + remaining_logs,
                        "notification_events": notification_events_count + remaining_notification_events,
                        "cost_savings": current_cost_savings
                    },
                    "after_cleanup": {
                        "operations": remaining_operations,
                        "jobs": remaining_jobs,
                        "logs": remaining_logs,
                        "notification_events": remaining_notification_events,
                        "cost_savings": remaining_cost_savings
                    },
                    "to_be_deleted": {
                        "operations": operations_count,
                        "jobs": jobs_count,
                        "logs": logs_count,
                        "notification_events": notification_events_count
                    },
                    "cost_impact": cost_impact,
                    "storage_impact_mb": storage_impact,
                    "can_cleanup": True
                }
                
        except Exception as e:
            logger.error(f"Error getting cleanup preview: {e}")
            raise
    
    async def execute_cleanup(self, cutoff_date: datetime, repository: str = None, 
                            data_types: List[str] = None) -> Dict[str, Any]:
        """Execute the actual cleanup with automatic backup"""
        try:
            # Create automatic backup before cleanup
            backup_result = await self._create_backup_before_cleanup()
            if not backup_result.get('success'):
                raise Exception(f"Failed to create backup before cleanup: {backup_result.get('error')}")
            
            with self.database_manager.SessionLocal() as db:
                # Track what was deleted
                deleted_counts = {}
                
                try:
                    # Delete in order: notification_events -> logs -> operations -> jobs
                    if not data_types or 'notification_events' in data_types:
                        notification_query = db.query(NotificationEventDB).filter(NotificationEventDB.timestamp < cutoff_date)
                        if repository:
                            notification_query = notification_query.filter(NotificationEventDB.repositories.contains([repository]))
                        deleted_counts['notification_events'] = notification_query.delete(synchronize_session=False)
                    
                    if not data_types or 'logs' in data_types:
                        logs_query = db.query(LogEntryDB).filter(LogEntryDB.timestamp < cutoff_date)
                        if repository:
                            logs_query = logs_query.filter(LogEntryDB.repo == repository)
                        deleted_counts['logs'] = logs_query.delete(synchronize_session=False)
                    
                    if not data_types or 'operations' in data_types:
                        operations_query = db.query(OperationDB).filter(OperationDB.started_at < cutoff_date)
                        if repository:
                            operations_query = operations_query.filter(OperationDB.repo == repository)
                        deleted_counts['operations'] = operations_query.delete(synchronize_session=False)
                    
                    if not data_types or 'jobs' in data_types:
                        jobs_query = db.query(JobDB).filter(JobDB.started_at < cutoff_date)
                        if repository:
                            jobs_query = jobs_query.filter(JobDB.repository == repository)
                        deleted_counts['jobs'] = jobs_query.delete(synchronize_session=False)
                    
                    db.commit()
                    
                    # Recalculate global metrics after cleanup
                    await self.metrics_service.recalculate_metrics_from_operations(db)

                    # Clear caches after cleanup
                    if self.cached_job_service:
                        try:
                            # Clear all caches since cleanup can affect any data type
                            if hasattr(self.cached_job_service.cache, 'jobs_cache'):
                                await self.cached_job_service.cache.jobs_cache.clear()
                            if hasattr(self.cached_job_service.cache, 'operations_cache'):
                                await self.cached_job_service.cache.operations_cache.clear()
                            if hasattr(self.cached_job_service.cache, 'logs_cache'):
                                await self.cached_job_service.cache.logs_cache.clear()
                            if hasattr(self.cached_job_service.cache, 'metrics_cache'):
                                await self.cached_job_service.cache.metrics_cache.clear()

                            # Clear indexes
                            if hasattr(self.cached_job_service.cache, 'logs_by_job'):
                                self.cached_job_service.cache.logs_by_job.clear()
                            if hasattr(self.cached_job_service.cache, 'operations_by_job'):
                                self.cached_job_service.cache.operations_by_job.clear()

                            logger.info("Cleared all caches after data cleanup")
                        except Exception as e:
                            logger.warning(f"Failed to clear caches after cleanup: {e}")

                except Exception as e:
                    db.rollback()
                    logger.error(f"Database error during cleanup: {e}")
                    raise
                
                logger.info(f"Cleanup completed: {deleted_counts}")
                
                return {
                    "cutoff_date": cutoff_date.isoformat(),
                    "repository": repository,
                    "deleted_counts": deleted_counts,
                    "backup_created": backup_result.get('success', False),
                    "backup_path": backup_result.get('backup_path'),
                    "metrics_recalculated": True,
                    "message": "Data cleanup completed successfully"
                }
                
        except Exception as e:
            logger.error(f"Error executing cleanup: {e}")
            raise
    
    
    async def _get_current_cost_savings(self, db: Session, repository: str = None) -> float:
        """Get current cost savings from metrics aggregate"""
        try:
            aggregate = db.query(MetricsAggregateDB).first()
            if not aggregate:
                return 0.0
            
            # Calculate cost savings from current metrics
            config = await self.metrics_service.get_or_create_config(db)
            total_cost = 0.0
            
            # Calculate cost from operations (only load necessary columns for performance)
            operations_query = db.query(
                OperationDB.total_input_tokens,
                OperationDB.total_output_tokens,
                OperationDB.input_tokens,
                OperationDB.output_tokens,
                OperationDB.ai_models_used,
                OperationDB.model_used,
                OperationDB.estimated_dev_hours_saved
            )
            if repository:
                operations_query = operations_query.filter(OperationDB.repo == repository)
            operations = operations_query.all()

            for op_data in operations:
                # Use multi-model data if available, otherwise fall back to legacy
                final_input_tokens = op_data.total_input_tokens if op_data.total_input_tokens else (op_data.input_tokens or 0)
                final_output_tokens = op_data.total_output_tokens if op_data.total_output_tokens else (op_data.output_tokens or 0)

                if final_input_tokens and final_output_tokens:
                    # Handle multi-model data (preferred)
                    if op_data.ai_models_used and isinstance(op_data.ai_models_used, dict):
                        for model_name, model_tokens in op_data.ai_models_used.items():
                            model_costs = config.model_costs.get(model_name, {})
                            if model_costs:
                                input_cost = (model_tokens.get('input_tokens', 0) / 1000) * model_costs.get('input', 0)
                                output_cost = (model_tokens.get('output_tokens', 0) / 1000) * model_costs.get('output', 0)
                                total_cost += input_cost + output_cost
                    # Handle legacy single-model data (fallback)
                    elif op_data.model_used:
                        model_costs = config.model_costs.get(op_data.model_used, {})
                        if model_costs:
                            input_cost = (final_input_tokens / 1000) * model_costs.get('input', 0)
                            output_cost = (final_output_tokens / 1000) * model_costs.get('output', 0)
                            total_cost += input_cost + output_cost

            # Calculate dev hours savings
            dev_hours_saved = sum(op.estimated_dev_hours_saved or 0 for op in operations)
            dev_cost_savings = dev_hours_saved * config.developer_hourly_rate * config.hours_multiplier
            
            return round(total_cost + dev_cost_savings, 2)
            
        except Exception as e:
            logger.warning(f"Error calculating current cost savings: {e}")
            return 0.0
    
    async def _get_remaining_cost_savings(self, db: Session, cutoff_date: datetime, repository: str = None) -> float:
        """Get cost savings after cleanup (remaining data only)"""
        try:
            config = await self.metrics_service.get_or_create_config(db)
            total_cost = 0.0
            
            # Calculate cost from remaining operations (after cutoff date, only load necessary columns)
            operations_query = db.query(
                OperationDB.total_input_tokens,
                OperationDB.total_output_tokens,
                OperationDB.input_tokens,
                OperationDB.output_tokens,
                OperationDB.ai_models_used,
                OperationDB.model_used,
                OperationDB.estimated_dev_hours_saved
            ).filter(OperationDB.started_at >= cutoff_date)
            if repository:
                operations_query = operations_query.filter(OperationDB.repo == repository)
            operations = operations_query.all()

            for op_data in operations:
                # Use multi-model data if available, otherwise fall back to legacy
                final_input_tokens = op_data.total_input_tokens if op_data.total_input_tokens else (op_data.input_tokens or 0)
                final_output_tokens = op_data.total_output_tokens if op_data.total_output_tokens else (op_data.output_tokens or 0)

                if final_input_tokens and final_output_tokens:
                    # Handle multi-model data (preferred)
                    if op_data.ai_models_used and isinstance(op_data.ai_models_used, dict):
                        for model_name, model_tokens in op_data.ai_models_used.items():
                            model_costs = config.model_costs.get(model_name, {})
                            if model_costs:
                                input_cost = (model_tokens.get('input_tokens', 0) / 1000) * model_costs.get('input', 0)
                                output_cost = (model_tokens.get('output_tokens', 0) / 1000) * model_costs.get('output', 0)
                                total_cost += input_cost + output_cost
                    # Handle legacy single-model data (fallback)
                    elif op_data.model_used:
                        model_costs = config.model_costs.get(op_data.model_used, {})
                        if model_costs:
                            input_cost = (final_input_tokens / 1000) * model_costs.get('input', 0)
                            output_cost = (final_output_tokens / 1000) * model_costs.get('output', 0)
                            total_cost += input_cost + output_cost

            # Calculate dev hours savings from remaining operations
            dev_hours_saved = sum(op.estimated_dev_hours_saved or 0 for op in operations)
            dev_cost_savings = dev_hours_saved * config.developer_hourly_rate * config.hours_multiplier
            
            return round(total_cost + dev_cost_savings, 2)
            
        except Exception as e:
            logger.warning(f"Error calculating remaining cost savings: {e}")
            return 0.0
    
    async def _calculate_storage_impact(self, db: Session, cutoff_date: datetime, repository: str = None) -> float:
        """Calculate approximate storage space that will be freed (in MB)"""
        try:
            # Rough estimation based on record counts and average sizes
            operations_query = db.query(OperationDB).filter(OperationDB.started_at < cutoff_date)
            if repository:
                operations_query = operations_query.filter(OperationDB.repo == repository)
            operations_count = operations_query.count()
            
            jobs_query = db.query(JobDB).filter(JobDB.started_at < cutoff_date)
            if repository:
                jobs_query = jobs_query.filter(JobDB.repository == repository)
            jobs_count = jobs_query.count()
            
            logs_query = db.query(LogEntryDB).filter(LogEntryDB.timestamp < cutoff_date)
            if repository:
                logs_query = logs_query.filter(LogEntryDB.repo == repository)
            logs_count = logs_query.count()
            
            # Rough size estimates (in bytes)
            operation_size = 2000  # ~2KB per operation
            job_size = 1000       # ~1KB per job
            log_size = 500        # ~500B per log entry
            
            total_bytes = (operations_count * operation_size + 
                          jobs_count * job_size + 
                          logs_count * log_size)
            
            # Convert to MB
            return round(total_bytes / (1024 * 1024), 2)
            
        except Exception as e:
            logger.warning(f"Error calculating storage impact: {e}")
            return 0.0
    
    async def _create_backup_before_cleanup(self) -> Dict[str, Any]:
        """Create automatic backup before cleanup"""
        try:
            if self.retention_service:
                backup_result = self.retention_service.create_backup()
                return {
                    "success": True,
                    "backup_path": backup_result.get("path"),
                    "backup_size": backup_result.get("size")
                }
            else:
                logger.warning("No retention service available for backup")
                return {
                    "success": False,
                    "error": "No retention service available"
                }
        except Exception as e:
            logger.error(f"Error creating backup: {e}")
            return {
                "success": False,
                "error": str(e)
            }
    
