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
    
    def __init__(self):
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
            # Extract metrics from operation
            model_used = operation_data.get('model_used')
            input_tokens = operation_data.get('input_tokens', 0)
            output_tokens = operation_data.get('output_tokens', 0)
            estimated_dev_hours = operation_data.get('estimated_dev_hours_saved', 0.0)
            
            # Skip if no metrics data
            if not any([model_used, input_tokens, output_tokens, estimated_dev_hours]):
                return
            
            # Get or create aggregate
            aggregate = db.query(MetricsAggregateDB).first()
            if not aggregate:
                aggregate = MetricsAggregateDB()
                db.add(aggregate)
            
            # Update totals
            aggregate.total_operations += 1
            if input_tokens:
                aggregate.total_input_tokens += input_tokens
            if output_tokens:
                aggregate.total_output_tokens += output_tokens
            if estimated_dev_hours:
                aggregate.total_estimated_dev_hours += estimated_dev_hours
            
            # Update model usage breakdown
            if model_used:
                model_usage = aggregate.model_usage or {}
                if model_used not in model_usage:
                    model_usage[model_used] = {
                        'operations_count': 0,
                        'input_tokens': 0,
                        'output_tokens': 0,
                        'estimated_dev_hours': 0.0
                    }
                
                model_usage[model_used]['operations_count'] += 1
                model_usage[model_used]['input_tokens'] += input_tokens or 0
                model_usage[model_used]['output_tokens'] += output_tokens or 0
                model_usage[model_used]['estimated_dev_hours'] += estimated_dev_hours or 0.0
                
                aggregate.model_usage = model_usage
            
            aggregate.last_updated = datetime.utcnow()
            db.commit()
            
        except Exception as e:
            logger.error(f"Error updating metrics from operation: {e}")
            db.rollback()
            raise
    
    async def recalculate_metrics_from_operations(self, db: Session):
        """Recalculate all metrics from existing operations (for data migration/correction)"""
        try:
            # Get all operations with metrics data
            operations = db.query(OperationDB).filter(
                (OperationDB.model_used.is_not(None)) |
                (OperationDB.input_tokens.is_not(None)) |
                (OperationDB.output_tokens.is_not(None)) |
                (OperationDB.estimated_dev_hours_saved.is_not(None))
            ).all()
            
            # Reset aggregate
            aggregate = db.query(MetricsAggregateDB).first()
            if not aggregate:
                aggregate = MetricsAggregateDB()
                db.add(aggregate)
            
            # Reset values
            aggregate.total_operations = 0
            aggregate.total_input_tokens = 0
            aggregate.total_output_tokens = 0
            aggregate.total_estimated_dev_hours = 0.0
            aggregate.model_usage = {}
            
            # Process each operation
            for operation in operations:
                model_used = operation.model_used
                input_tokens = operation.input_tokens or 0
                output_tokens = operation.output_tokens or 0
                estimated_dev_hours = operation.estimated_dev_hours_saved or 0.0
                
                # Update totals
                aggregate.total_operations += 1
                aggregate.total_input_tokens += input_tokens
                aggregate.total_output_tokens += output_tokens
                aggregate.total_estimated_dev_hours += estimated_dev_hours
                
                # Update model usage
                if model_used:
                    model_usage = aggregate.model_usage or {}
                    if model_used not in model_usage:
                        model_usage[model_used] = {
                            'operations_count': 0,
                            'input_tokens': 0,
                            'output_tokens': 0,
                            'estimated_dev_hours': 0.0
                        }
                    
                    model_usage[model_used]['operations_count'] += 1
                    model_usage[model_used]['input_tokens'] += input_tokens
                    model_usage[model_used]['output_tokens'] += output_tokens
                    model_usage[model_used]['estimated_dev_hours'] += estimated_dev_hours
                    
                    aggregate.model_usage = model_usage
            
            # Count total jobs
            total_jobs = db.query(OperationDB.job_id).distinct().count()
            aggregate.total_jobs = total_jobs
            
            aggregate.last_updated = datetime.utcnow()
            db.commit()
            
            logger.info(f"Recalculated metrics: {aggregate.total_operations} operations, {total_jobs} jobs")
            
        except Exception as e:
            logger.error(f"Error recalculating metrics: {e}")
            db.rollback()
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