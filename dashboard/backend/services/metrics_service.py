"""
Metrics Service - Manages AI/LLM metrics aggregation and cost calculation
"""
from datetime import datetime
from typing import Dict, Any, Optional
from sqlalchemy.orm import Session
from models import MetricsAggregateDB, MetricsConfigDB, MetricsAggregate, MetricsConfig, MetricsSummary, OperationDB
import logging

logger = logging.getLogger(__name__)

class MetricsService:
    """Service for managing AI/LLM metrics and cost calculation"""
    
    def __init__(self, websocket_manager=None):
        self.websocket_manager = websocket_manager
        self.default_model_costs = {
            # OpenAI Models (per 1K tokens)
            "gpt-4": {"input": 0.03, "output": 0.06},
            "gpt-4-turbo": {"input": 0.01, "output": 0.03},
            "gpt-4o": {"input": 0.005, "output": 0.015},
            "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
            "gpt-3.5-turbo": {"input": 0.0015, "output": 0.002},
            
            # Anthropic Models (per 1K tokens)
            "claude-3-opus": {"input": 0.015, "output": 0.075},
            "claude-3-sonnet": {"input": 0.003, "output": 0.015},
            "claude-3-haiku": {"input": 0.00025, "output": 0.00125},
            "claude-3-5-sonnet": {"input": 0.003, "output": 0.015},
            "claude-3-5-sonnet-20241022": {"input": 0.003, "output": 0.015},
            
            # Google Models (per 1K tokens)
            "gemini-pro": {"input": 0.0005, "output": 0.0015},
            "gemini-1.5-pro": {"input": 0.0035, "output": 0.0105},
            "gemini-1.5-flash": {"input": 0.000075, "output": 0.0003},
        }
    
    async def get_or_create_config(self, db: Session) -> MetricsConfig:
        """Get or create metrics configuration"""
        try:
            config = db.query(MetricsConfigDB).first()
            if not config:
                config = MetricsConfigDB(
                    model_costs=self.default_model_costs,
                    developer_hourly_rate=75.0,
                    hours_multiplier=1.0
                )
                db.add(config)
                db.commit()
                db.refresh(config)
            
            return MetricsConfig(
                id=config.id,
                model_costs=config.model_costs or {},
                developer_hourly_rate=config.developer_hourly_rate,
                hours_multiplier=config.hours_multiplier,
                created_at=config.created_at.isoformat() if config.created_at else None,
                updated_at=config.updated_at.isoformat() if config.updated_at else None
            )
        except Exception as e:
            logger.error(f"Error getting metrics config: {e}")
            raise
    
    async def update_config(self, db: Session, config_data: Dict[str, Any]) -> MetricsConfig:
        """Update metrics configuration"""
        try:
            config = db.query(MetricsConfigDB).first()
            if not config:
                config = MetricsConfigDB()
                db.add(config)
            
            if 'model_costs' in config_data:
                config.model_costs = config_data['model_costs']
            if 'developer_hourly_rate' in config_data:
                config.developer_hourly_rate = config_data['developer_hourly_rate']
            if 'hours_multiplier' in config_data:
                config.hours_multiplier = config_data['hours_multiplier']
            
            config.updated_at = datetime.utcnow()
            db.commit()
            db.refresh(config)
            
            return MetricsConfig(
                id=config.id,
                model_costs=config.model_costs or {},
                developer_hourly_rate=config.developer_hourly_rate,
                hours_multiplier=config.hours_multiplier,
                created_at=config.created_at.isoformat() if config.created_at else None,
                updated_at=config.updated_at.isoformat() if config.updated_at else None
            )
        except Exception as e:
            logger.error(f"Error updating metrics config: {e}")
            db.rollback()
            raise
    
    async def get_or_create_aggregate(self, db: Session) -> MetricsAggregate:
        """Get or create metrics aggregate"""
        try:
            aggregate = db.query(MetricsAggregateDB).first()
            if not aggregate:
                aggregate = MetricsAggregateDB()
                db.add(aggregate)
                db.commit()
                db.refresh(aggregate)
            
            return MetricsAggregate(
                id=aggregate.id,
                total_jobs=aggregate.total_jobs,
                total_operations=aggregate.total_operations,
                total_input_tokens=aggregate.total_input_tokens,
                total_output_tokens=aggregate.total_output_tokens,
                total_estimated_dev_hours=aggregate.total_estimated_dev_hours,
                model_usage=aggregate.model_usage or {},
                last_updated=aggregate.last_updated.isoformat() if aggregate.last_updated else None
            )
        except Exception as e:
            logger.error(f"Error getting metrics aggregate: {e}")
            raise
    
    async def update_metrics_from_operation(self, db: Session, operation_data: Dict[str, Any]):
        """Update metrics aggregate from operation data"""
        try:
            # Extract multi-model metrics first (preferred)
            ai_models_used = operation_data.get('ai_models_used')
            total_input_tokens = operation_data.get('total_input_tokens', 0)
            total_output_tokens = operation_data.get('total_output_tokens', 0)
            
            # Fall back to legacy single-model metrics if multi-model data unavailable
            model_used = operation_data.get('model_used')
            input_tokens = operation_data.get('input_tokens', 0) 
            output_tokens = operation_data.get('output_tokens', 0)
            
            # Use multi-model totals if available, otherwise use legacy data
            final_input_tokens = total_input_tokens if total_input_tokens else input_tokens
            final_output_tokens = total_output_tokens if total_output_tokens else output_tokens
            
            estimated_dev_hours = operation_data.get('estimated_dev_hours_saved', 0.0)
            job_id = operation_data.get('job_id')
            
            # Skip if no metrics data at all
            if not any([ai_models_used, model_used, final_input_tokens, final_output_tokens, estimated_dev_hours]):
                return
            
            # Get or create aggregate
            aggregate = db.query(MetricsAggregateDB).first()
            if not aggregate:
                aggregate = MetricsAggregateDB()
                db.add(aggregate)
            
            # Ensure all aggregate fields have default values (handle None values)
            if aggregate.total_operations is None:
                aggregate.total_operations = 0
            if aggregate.total_input_tokens is None:
                aggregate.total_input_tokens = 0
            if aggregate.total_output_tokens is None:
                aggregate.total_output_tokens = 0
            if aggregate.total_estimated_dev_hours is None:
                aggregate.total_estimated_dev_hours = 0.0
            if aggregate.total_jobs is None:
                aggregate.total_jobs = 0
            
            # Update totals
            aggregate.total_operations += 1
            if final_input_tokens:
                aggregate.total_input_tokens += final_input_tokens
            if final_output_tokens:
                aggregate.total_output_tokens += final_output_tokens
            if estimated_dev_hours:
                aggregate.total_estimated_dev_hours += estimated_dev_hours
            
            # Update job count (count distinct job_ids)
            if job_id:
                from models import OperationDB
                total_jobs = db.query(OperationDB.job_id).distinct().count()
                aggregate.total_jobs = total_jobs
            
            # Update model usage breakdown - handle both multi-model and legacy data
            model_usage = aggregate.model_usage or {}
            
            # Handle multi-model data (preferred) - track each model separately for cost calculations
            if ai_models_used and isinstance(ai_models_used, dict):
                # Each model gets tracked separately with its own operation count and tokens
                for model_name, model_tokens in ai_models_used.items():
                    if model_name not in model_usage:
                        model_usage[model_name] = {
                            'operations_count': 0,
                            'input_tokens': 0,
                            'output_tokens': 0,
                            'estimated_dev_hours': 0.0
                        }
                    
                    # Each model gets +1 operation count since it participated in this operation
                    model_usage[model_name]['operations_count'] += 1
                    model_usage[model_name]['input_tokens'] += model_tokens.get('input_tokens', 0)
                    model_usage[model_name]['output_tokens'] += model_tokens.get('output_tokens', 0)
                
                # Dev hours are attributed to the operation as a whole, not per model
                # Add dev hours to the first model to avoid duplication but maintain attribution
                if estimated_dev_hours and ai_models_used:
                    first_model = list(ai_models_used.keys())[0]
                    model_usage[first_model]['estimated_dev_hours'] += estimated_dev_hours
            
            # Handle legacy single-model data (fallback)
            elif model_used:
                if model_used not in model_usage:
                    model_usage[model_used] = {
                        'operations_count': 0,
                        'input_tokens': 0,
                        'output_tokens': 0,
                        'estimated_dev_hours': 0.0
                    }
                
                model_usage[model_used]['operations_count'] += 1
                model_usage[model_used]['input_tokens'] += final_input_tokens or 0
                model_usage[model_used]['output_tokens'] += final_output_tokens or 0
                model_usage[model_used]['estimated_dev_hours'] += estimated_dev_hours or 0.0
            
            aggregate.model_usage = model_usage
            
            aggregate.last_updated = datetime.utcnow()
            db.commit()
            
        except Exception as e:
            logger.error(f"Error updating metrics from operation: {e}")
            db.rollback()
            raise

    async def update_aggregates_from_operation(self, db: Session, operation: OperationDB):
        """Update metrics aggregates from a completed operation"""
        try:
            # Skip if no metrics data
            if not any([operation.model_used, operation.input_tokens, operation.output_tokens, operation.estimated_dev_hours_saved]):
                return
            
            # Get or create aggregate
            aggregate = db.query(MetricsAggregateDB).first()
            if not aggregate:
                aggregate = MetricsAggregateDB()
                db.add(aggregate)
            
            # Ensure all aggregate fields have default values (handle None values)
            if aggregate.total_operations is None:
                aggregate.total_operations = 0
            if aggregate.total_input_tokens is None:
                aggregate.total_input_tokens = 0
            if aggregate.total_output_tokens is None:
                aggregate.total_output_tokens = 0
            if aggregate.total_estimated_dev_hours is None:
                aggregate.total_estimated_dev_hours = 0.0
            if aggregate.total_jobs is None:
                aggregate.total_jobs = 0
            
            # Use multi-model data if available, otherwise fall back to legacy
            final_input_tokens = operation.total_input_tokens if operation.total_input_tokens else (operation.input_tokens or 0)
            final_output_tokens = operation.total_output_tokens if operation.total_output_tokens else (operation.output_tokens or 0)
            
            # Update totals
            aggregate.total_operations += 1
            if final_input_tokens:
                aggregate.total_input_tokens += final_input_tokens
            if final_output_tokens:
                aggregate.total_output_tokens += final_output_tokens
            if operation.estimated_dev_hours_saved:
                aggregate.total_estimated_dev_hours += operation.estimated_dev_hours_saved
            
            # Update job count (count distinct job_ids)
            if operation.job_id:
                total_jobs = db.query(OperationDB.job_id).distinct().count()
                aggregate.total_jobs = total_jobs
            
            # Update model usage breakdown - handle both multi-model and legacy data
            model_usage = aggregate.model_usage or {}
            
            # Handle multi-model data (preferred) - track each model separately for cost calculations
            if operation.ai_models_used and isinstance(operation.ai_models_used, dict):
                # Each model gets tracked separately with its own operation count and tokens
                for model_name, model_tokens in operation.ai_models_used.items():
                    if model_name not in model_usage:
                        model_usage[model_name] = {
                            'operations_count': 0,
                            'input_tokens': 0,
                            'output_tokens': 0,
                            'estimated_dev_hours': 0.0
                        }
                    
                    # Each model gets +1 operation count since it participated in this operation
                    model_usage[model_name]['operations_count'] += 1
                    model_usage[model_name]['input_tokens'] += model_tokens.get('input_tokens', 0)
                    model_usage[model_name]['output_tokens'] += model_tokens.get('output_tokens', 0)
                
                # Dev hours are attributed to the operation as a whole, not per model
                # Add dev hours to the first model to avoid duplication but maintain attribution
                if operation.estimated_dev_hours_saved and operation.ai_models_used:
                    first_model = list(operation.ai_models_used.keys())[0]
                    model_usage[first_model]['estimated_dev_hours'] += operation.estimated_dev_hours_saved
            
            # Handle legacy single-model data (fallback)
            elif operation.model_used:
                if operation.model_used not in model_usage:
                    model_usage[operation.model_used] = {
                        'operations_count': 0,
                        'input_tokens': 0,
                        'output_tokens': 0,
                        'estimated_dev_hours': 0.0
                    }
                
                model_usage[operation.model_used]['operations_count'] += 1
                model_usage[operation.model_used]['input_tokens'] += final_input_tokens
                model_usage[operation.model_used]['output_tokens'] += final_output_tokens
                model_usage[operation.model_used]['estimated_dev_hours'] += operation.estimated_dev_hours_saved or 0.0
            
            aggregate.model_usage = model_usage
            
            aggregate.last_updated = datetime.utcnow()
            # Don't commit here - let the calling function handle the transaction
            
            # Send WebSocket update if available
            if self.websocket_manager:
                try:
                    await self._broadcast_metrics_update(db)
                except Exception as e:
                    logger.warning(f"Failed to broadcast metrics update: {e}")
            
        except Exception as e:
            logger.error(f"Error updating aggregates from operation: {e}")
            raise
    
    async def recalculate_metrics_from_operations(self, db: Session):
        """Recalculate all metrics from existing operations (for data migration/correction)"""
        try:
            # Get all operations with metrics data (both legacy and multi-model)
            operations = db.query(OperationDB).filter(
                (OperationDB.model_used.is_not(None)) |
                (OperationDB.input_tokens.is_not(None)) |
                (OperationDB.output_tokens.is_not(None)) |
                (OperationDB.ai_models_used.is_not(None)) |
                (OperationDB.total_input_tokens.is_not(None)) |
                (OperationDB.total_output_tokens.is_not(None)) |
                (OperationDB.estimated_dev_hours_saved.is_not(None))
            ).all()
            
            # Build new values in memory first (atomic approach - no intermediate zeros in DB)
            new_total_operations = 0
            new_total_input_tokens = 0
            new_total_output_tokens = 0
            new_total_estimated_dev_hours = 0.0
            new_model_usage = {}
            
            # Process each operation to build complete new values
            for operation in operations:
                # Use multi-model data if available, otherwise fall back to legacy
                final_input_tokens = operation.total_input_tokens if operation.total_input_tokens else (operation.input_tokens or 0)
                final_output_tokens = operation.total_output_tokens if operation.total_output_tokens else (operation.output_tokens or 0)
                estimated_dev_hours = operation.estimated_dev_hours_saved or 0.0
                
                # Update totals
                new_total_operations += 1
                new_total_input_tokens += final_input_tokens
                new_total_output_tokens += final_output_tokens
                new_total_estimated_dev_hours += estimated_dev_hours
                
                # Update model usage - handle both multi-model and legacy data
                # Handle multi-model data (preferred) - track each model separately for cost calculations
                if operation.ai_models_used and isinstance(operation.ai_models_used, dict):
                    # Each model gets tracked separately with its own operation count and tokens
                    for model_name, model_tokens in operation.ai_models_used.items():
                        if model_name not in new_model_usage:
                            new_model_usage[model_name] = {
                                'operations_count': 0,
                                'input_tokens': 0,
                                'output_tokens': 0,
                                'estimated_dev_hours': 0.0
                            }
                        
                        # Each model gets +1 operation count since it participated in this operation
                        new_model_usage[model_name]['operations_count'] += 1
                        new_model_usage[model_name]['input_tokens'] += model_tokens.get('input_tokens', 0)
                        new_model_usage[model_name]['output_tokens'] += model_tokens.get('output_tokens', 0)
                    
                    # Dev hours are attributed to the operation as a whole, not per model
                    # Add dev hours to the first model to avoid duplication but maintain attribution
                    if estimated_dev_hours and operation.ai_models_used:
                        first_model = list(operation.ai_models_used.keys())[0]
                        new_model_usage[first_model]['estimated_dev_hours'] += estimated_dev_hours
                
                # Handle legacy single-model data (fallback)
                elif operation.model_used:
                    if operation.model_used not in new_model_usage:
                        new_model_usage[operation.model_used] = {
                            'operations_count': 0,
                            'input_tokens': 0,
                            'output_tokens': 0,
                            'estimated_dev_hours': 0.0
                        }
                    
                    new_model_usage[operation.model_used]['operations_count'] += 1
                    new_model_usage[operation.model_used]['input_tokens'] += final_input_tokens
                    new_model_usage[operation.model_used]['output_tokens'] += final_output_tokens
                    new_model_usage[operation.model_used]['estimated_dev_hours'] += estimated_dev_hours
            
            # Count total jobs
            new_total_jobs = db.query(OperationDB.job_id).distinct().count()
            
            # Now atomically update the aggregate with all new values at once
            aggregate = db.query(MetricsAggregateDB).first()
            if not aggregate:
                aggregate = MetricsAggregateDB()
                db.add(aggregate)
            
            # Apply all new values atomically (no intermediate state with zeros)
            aggregate.total_operations = new_total_operations
            aggregate.total_input_tokens = new_total_input_tokens
            aggregate.total_output_tokens = new_total_output_tokens
            aggregate.total_estimated_dev_hours = new_total_estimated_dev_hours
            aggregate.total_jobs = new_total_jobs
            aggregate.model_usage = new_model_usage
            
            aggregate.last_updated = datetime.utcnow()
            db.commit()
            
            logger.info(f"Recalculated metrics: {aggregate.total_operations} operations, {aggregate.total_jobs} jobs")
            
            # Send WebSocket update if available
            if self.websocket_manager:
                try:
                    await self._broadcast_metrics_update(db)
                except Exception as e:
                    logger.warning(f"Failed to broadcast metrics update: {e}")
            
        except Exception as e:
            logger.error(f"Error recalculating metrics: {e}")
            db.rollback()
            raise
    
    async def get_operation_breakdown(self, db: Session) -> Dict[str, Any]:
        """Get operation breakdown with cost calculations"""
        try:
            # Get config for cost calculations
            config = await self.get_or_create_config(db)
            
            # Query operations with metrics data
            operations = db.query(OperationDB).filter(
                (OperationDB.model_used.is_not(None)) |
                (OperationDB.input_tokens.is_not(None)) |
                (OperationDB.output_tokens.is_not(None)) |
                (OperationDB.estimated_dev_hours_saved.is_not(None))
            ).all()
            
            # Aggregate by operation type
            operation_breakdown = {}
            total_cost = 0.0
            total_operations = 0
            total_input_tokens = 0
            total_output_tokens = 0
            total_dev_hours = 0.0
            
            for operation in operations:
                op_type = operation.operation_type or "unknown"
                input_tokens = operation.input_tokens or 0
                output_tokens = operation.output_tokens or 0
                estimated_dev_hours = operation.estimated_dev_hours_saved or 0.0
                model_used = operation.model_used
                
                # Calculate operation cost
                operation_cost = 0.0
                if model_used and (input_tokens > 0 or output_tokens > 0):
                    model_costs = config.model_costs.get(model_used, self.default_model_costs.get(model_used, {'input': 0.01, 'output': 0.03}))
                    input_cost = (input_tokens / 1000) * model_costs.get('input', 0.01)
                    output_cost = (output_tokens / 1000) * model_costs.get('output', 0.03)
                    operation_cost = input_cost + output_cost
                
                # Initialize operation type if not exists
                if op_type not in operation_breakdown:
                    operation_breakdown[op_type] = {
                        'operations_count': 0,
                        'input_tokens': 0,
                        'output_tokens': 0,
                        'estimated_dev_hours': 0.0,
                        'total_cost': 0.0,
                        'avg_duration': 0.0,
                        'success_rate': 0.0,
                        'total_duration': 0.0,
                        'successful_operations': 0,
                        'models_used': set()
                    }
                
                # Update breakdown
                operation_breakdown[op_type]['operations_count'] += 1
                operation_breakdown[op_type]['input_tokens'] += input_tokens
                operation_breakdown[op_type]['output_tokens'] += output_tokens
                operation_breakdown[op_type]['estimated_dev_hours'] += estimated_dev_hours
                operation_breakdown[op_type]['total_cost'] += operation_cost
                
                # Track duration and success
                if operation.duration:
                    operation_breakdown[op_type]['total_duration'] += operation.duration
                
                if operation.status in ['completed', 'published']:
                    operation_breakdown[op_type]['successful_operations'] += 1
                
                if model_used:
                    operation_breakdown[op_type]['models_used'].add(model_used)
                
                # Update totals
                total_operations += 1
                total_input_tokens += input_tokens
                total_output_tokens += output_tokens
                total_dev_hours += estimated_dev_hours
                total_cost += operation_cost
            
            # Calculate derived metrics for each operation type
            for op_type, data in operation_breakdown.items():
                # Convert set to list for JSON serialization
                data['models_used'] = list(data['models_used'])
                
                # Calculate averages
                ops_count = data['operations_count']
                if ops_count > 0:
                    data['avg_duration'] = round(data['total_duration'] / ops_count, 2) if data['total_duration'] > 0 else 0.0
                    data['success_rate'] = round((data['successful_operations'] / ops_count) * 100, 1)
                    data['cost_per_operation'] = round(data['total_cost'] / ops_count, 4)
                    data['avg_input_tokens'] = round(data['input_tokens'] / ops_count, 0)
                    data['avg_output_tokens'] = round(data['output_tokens'] / ops_count, 0)
                    data['avg_dev_hours'] = round(data['estimated_dev_hours'] / ops_count, 3)
                else:
                    data['cost_per_operation'] = 0.0
                    data['avg_input_tokens'] = 0
                    data['avg_output_tokens'] = 0
                    data['avg_dev_hours'] = 0.0
                
                # Round cost to 4 decimal places
                data['total_cost'] = round(data['total_cost'], 4)
                
                # Remove helper fields
                del data['total_duration']
                del data['successful_operations']
            
            return {
                'operation_breakdown': operation_breakdown,
                'totals': {
                    'total_operations': total_operations,
                    'total_input_tokens': total_input_tokens,
                    'total_output_tokens': total_output_tokens,
                    'total_estimated_dev_hours': round(total_dev_hours, 2),
                    'total_cost': round(total_cost, 2)
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting operation breakdown: {e}")
            raise

    async def get_repository_breakdown(self, db: Session) -> Dict[str, Any]:
        """Get repository breakdown with cost calculations"""
        try:
            # Get config for cost calculations
            config = await self.get_or_create_config(db)
            
            # Query operations with metrics data
            operations = db.query(OperationDB).filter(
                (OperationDB.model_used.is_not(None)) |
                (OperationDB.input_tokens.is_not(None)) |
                (OperationDB.output_tokens.is_not(None)) |
                (OperationDB.estimated_dev_hours_saved.is_not(None))
            ).all()
            
            # Aggregate by repository
            repository_breakdown = {}
            total_cost = 0.0
            total_operations = 0
            total_input_tokens = 0
            total_output_tokens = 0
            total_dev_hours = 0.0
            
            for operation in operations:
                repo = operation.repo or "unknown"
                input_tokens = operation.input_tokens or 0
                output_tokens = operation.output_tokens or 0
                estimated_dev_hours = operation.estimated_dev_hours_saved or 0.0
                model_used = operation.model_used
                
                # Calculate operation cost
                operation_cost = 0.0
                if model_used and (input_tokens > 0 or output_tokens > 0):
                    model_costs = config.model_costs.get(model_used, self.default_model_costs.get(model_used, {'input': 0.01, 'output': 0.03}))
                    input_cost = (input_tokens / 1000) * model_costs.get('input', 0.01)
                    output_cost = (output_tokens / 1000) * model_costs.get('output', 0.03)
                    operation_cost = input_cost + output_cost
                
                # Initialize repository if not exists
                if repo not in repository_breakdown:
                    repository_breakdown[repo] = {
                        'operations_count': 0,
                        'input_tokens': 0,
                        'output_tokens': 0,
                        'estimated_dev_hours': 0.0,
                        'total_cost': 0.0,
                        'avg_duration': 0.0,
                        'success_rate': 0.0,
                        'total_duration': 0.0,
                        'successful_operations': 0,
                        'operation_types': set(),
                        'models_used': set(),
                        'unique_jobs': set()
                    }
                
                # Update breakdown
                repository_breakdown[repo]['operations_count'] += 1
                repository_breakdown[repo]['input_tokens'] += input_tokens
                repository_breakdown[repo]['output_tokens'] += output_tokens
                repository_breakdown[repo]['estimated_dev_hours'] += estimated_dev_hours
                repository_breakdown[repo]['total_cost'] += operation_cost
                
                # Track duration and success
                if operation.duration:
                    repository_breakdown[repo]['total_duration'] += operation.duration
                
                if operation.status in ['completed', 'published']:
                    repository_breakdown[repo]['successful_operations'] += 1
                
                if operation.operation_type:
                    repository_breakdown[repo]['operation_types'].add(operation.operation_type)
                
                if model_used:
                    repository_breakdown[repo]['models_used'].add(model_used)
                
                if operation.job_id:
                    repository_breakdown[repo]['unique_jobs'].add(operation.job_id)
                
                # Update totals
                total_operations += 1
                total_input_tokens += input_tokens
                total_output_tokens += output_tokens
                total_dev_hours += estimated_dev_hours
                total_cost += operation_cost
            
            # Calculate derived metrics for each repository
            for repo, data in repository_breakdown.items():
                # Convert sets to lists for JSON serialization
                data['operation_types'] = list(data['operation_types'])
                data['models_used'] = list(data['models_used'])
                data['unique_jobs_count'] = len(data['unique_jobs'])
                del data['unique_jobs']  # Remove the set itself
                
                # Calculate averages
                ops_count = data['operations_count']
                if ops_count > 0:
                    data['avg_duration'] = round(data['total_duration'] / ops_count, 2) if data['total_duration'] > 0 else 0.0
                    data['success_rate'] = round((data['successful_operations'] / ops_count) * 100, 1)
                    data['cost_per_operation'] = round(data['total_cost'] / ops_count, 4)
                    data['avg_input_tokens'] = round(data['input_tokens'] / ops_count, 0)
                    data['avg_output_tokens'] = round(data['output_tokens'] / ops_count, 0)
                    data['avg_dev_hours'] = round(data['estimated_dev_hours'] / ops_count, 3)
                    data['ops_per_job'] = round(ops_count / max(data['unique_jobs_count'], 1), 1)
                else:
                    data['cost_per_operation'] = 0.0
                    data['avg_input_tokens'] = 0
                    data['avg_output_tokens'] = 0
                    data['avg_dev_hours'] = 0.0
                    data['ops_per_job'] = 0.0
                
                # Round cost to 4 decimal places
                data['total_cost'] = round(data['total_cost'], 4)
                
                # Remove helper fields
                del data['total_duration']
                del data['successful_operations']
            
            return {
                'repository_breakdown': repository_breakdown,
                'totals': {
                    'total_operations': total_operations,
                    'total_input_tokens': total_input_tokens,
                    'total_output_tokens': total_output_tokens,
                    'total_estimated_dev_hours': round(total_dev_hours, 2),
                    'total_cost': round(total_cost, 2)
                }
            }
            
        except Exception as e:
            logger.error(f"Error getting repository breakdown: {e}")
            raise

    async def get_metrics_summary(self, db: Session) -> MetricsSummary:
        """Get complete metrics summary with cost calculations"""
        try:
            # Get config and aggregate
            config = await self.get_or_create_config(db)
            aggregate = await self.get_or_create_aggregate(db)
            
            # Calculate costs
            total_token_cost = 0.0
            model_breakdown = {}
            
            for model_name, usage in (aggregate.model_usage or {}).items():
                input_tokens = usage.get('input_tokens', 0)
                output_tokens = usage.get('output_tokens', 0)
                
                # Get model costs (use defaults if not configured)
                model_costs = config.model_costs.get(model_name, self.default_model_costs.get(model_name, {'input': 0.01, 'output': 0.03}))
                
                # Calculate cost (per 1K tokens)
                input_cost = (input_tokens / 1000) * model_costs.get('input', 0.01)
                output_cost = (output_tokens / 1000) * model_costs.get('output', 0.03)
                model_cost = input_cost + output_cost
                
                total_token_cost += model_cost
                
                model_breakdown[model_name] = {
                    'operations_count': usage.get('operations_count', 0),
                    'input_tokens': input_tokens,
                    'output_tokens': output_tokens,
                    'estimated_dev_hours': usage.get('estimated_dev_hours', 0.0),
                    'input_cost': round(input_cost, 4),
                    'output_cost': round(output_cost, 4),
                    'total_cost': round(model_cost, 4),
                    'cost_per_operation': round(model_cost / max(usage.get('operations_count', 1), 1), 4)
                }
            
            # Calculate developer savings
            adjusted_dev_hours = aggregate.total_estimated_dev_hours * config.hours_multiplier
            total_dev_cost_saved = adjusted_dev_hours * config.developer_hourly_rate
            total_savings = total_dev_cost_saved - total_token_cost
            
            return MetricsSummary(
                total_jobs=aggregate.total_jobs,
                total_operations=aggregate.total_operations,
                total_input_tokens=aggregate.total_input_tokens,
                total_output_tokens=aggregate.total_output_tokens,
                total_token_cost=round(total_token_cost, 2),
                total_dev_hours_saved=round(adjusted_dev_hours, 2),
                total_dev_cost_saved=round(total_dev_cost_saved, 2),
                total_savings=round(total_savings, 2),
                model_breakdown=model_breakdown,
                config=config
            )
            
        except Exception as e:
            logger.error(f"Error getting metrics summary: {e}")
            raise

    async def _broadcast_metrics_update(self, db: Session):
        """Broadcast metrics update via WebSocket"""
        try:
            if not self.websocket_manager:
                return
            
            # Get latest metrics data
            summary = await self.get_metrics_summary(db)
            operations = await self.get_operation_breakdown(db)
            repositories = await self.get_repository_breakdown(db)
            
            # Convert summary to dict if it's a Pydantic model
            summary_dict = summary.dict() if hasattr(summary, 'dict') else summary
            
            # Broadcast using the standard format
            await self.websocket_manager.broadcast({
                "type": "metrics_update",
                "data": {
                    "summary": summary_dict,
                    "operations": operations,
                    "repositories": repositories
                }
            })
            logger.debug("Broadcasted metrics update via WebSocket")
            
        except Exception as e:
            logger.warning(f"Failed to broadcast metrics update: {e}") 