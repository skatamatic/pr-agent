"""
Metrics Service - Responsible for collecting and calculating system metrics
Follows Single Responsibility Principle
"""
from datetime import datetime, timedelta
from typing import Dict, Any
from sqlalchemy.orm import Session
from models import OperationDB, LogEntryDB


class MetricsService:
    """Service for collecting and calculating system performance metrics"""
    
    def __init__(self):
        self.cache_duration = timedelta(minutes=5)
        self.cached_metrics = {}
        self.last_calculation = None
    
    async def get_system_metrics(self, db: Session) -> Dict[str, Any]:
        """Get real system metrics from database"""
        try:
            # Get operation counts
            total_ops = db.query(OperationDB).count()
            active_ops = db.query(OperationDB).filter(
                OperationDB.status.in_(["processing", "fetching_context", "preparing"])
            ).count()
            completed_ops = db.query(OperationDB).filter(OperationDB.status == "completed").count()
            failed_ops = db.query(OperationDB).filter(OperationDB.status == "failed").count()
            
            # Get recent operations for success rate calculation
            recent_ops = db.query(OperationDB).filter(
                OperationDB.started_at >= datetime.utcnow() - timedelta(hours=24)
            ).all()
            
            success_rate = 0
            if recent_ops:
                successful = len([op for op in recent_ops if op.status == "completed"])
                success_rate = (successful / len(recent_ops)) * 100
            
            # Get average response time
            completed_with_duration = db.query(OperationDB).filter(
                OperationDB.status == "completed",
                OperationDB.duration.isnot(None)
            ).limit(100).all()
            
            avg_response_time = 0
            if completed_with_duration:
                total_time = sum(op.duration for op in completed_with_duration if op.duration)
                avg_response_time = total_time / len(completed_with_duration)
            
            return {
                "total_operations": total_ops,
                "active_operations": active_ops,
                "completed_operations": completed_ops,
                "failed_operations": failed_ops,
                "success_rate": round(success_rate, 1),
                "avg_response_time": round(avg_response_time, 2),
                "operations_last_24h": len(recent_ops)
            }
        except Exception as e:
            return {
                "total_operations": 0,
                "active_operations": 0,
                "completed_operations": 0,
                "failed_operations": 0,
                "success_rate": 0,
                "avg_response_time": 0,
                "operations_last_24h": 0,
                "error": str(e)
            }
    
    async def get_realtime_status(self, db: Session) -> Dict[str, Any]:
        """Get real-time system status with comprehensive health checks"""
        metrics = await self.get_system_metrics(db)
        
        # Get recent operations for activity feed (limit to 5)
        recent_ops = db.query(OperationDB).order_by(OperationDB.started_at.desc()).limit(5).all()
        recent_operations = []
        for op in recent_ops:
            recent_operations.append({
                "id": op.operation_id,
                "command": op.command,
                "repo": op.repo,
                "status": op.status,
                "started_at": op.started_at.isoformat() if op.started_at else None,
                "duration": op.duration
            })
        
        # Determine overall system health based on metrics
        system_health = "healthy"
        if metrics["failed_operations"] > metrics["completed_operations"] * 0.2:  # >20% failure rate
            system_health = "degraded"
        elif metrics["active_operations"] == 0 and metrics["total_operations"] == 0:
            system_health = "idle"
        
        # Get last activity
        last_op = db.query(OperationDB).order_by(OperationDB.started_at.desc()).first()
        last_activity = last_op.started_at.isoformat() if last_op else None
        
        return {
            "timestamp": datetime.utcnow().isoformat(),
            "system_health": system_health,
            "last_activity": last_activity,
            "operations": {
                "total": metrics["total_operations"],
                "active": metrics["active_operations"],
                "completed": metrics["completed_operations"],
                "failed": metrics["failed_operations"],
                "success_rate": metrics["success_rate"],
                "avg_response_time": metrics["avg_response_time"],
                "last_24h": metrics["operations_last_24h"]
            },
            "services": {
                "database": "online",  # This would come from health service
                "api": "online",
                "context_service": "unknown"  # This would come from health service
            },
            "recent_operations": recent_operations,
            "queue_size": 0  # We don't have a queue system yet
        }
    
    async def get_performance_metrics(self, db: Session) -> Dict[str, Any]:
        """Get system performance metrics for the last 24 hours"""
        try:
            # Get performance data for last 24 hours
            day_ago = datetime.utcnow() - timedelta(hours=24)
            recent_ops = db.query(OperationDB).filter(OperationDB.started_at >= day_ago).all()
            
            # Calculate performance metrics
            total_ops = len(recent_ops)
            completed_ops = len([op for op in recent_ops if op.status == "completed"])
            failed_ops = len([op for op in recent_ops if op.status == "failed"])
            active_ops = len([op for op in recent_ops if op.status in ["processing", "fetching_context", "preparing"]])
            
            # Calculate average response time
            completed_with_duration = [op for op in recent_ops if op.status == "completed" and op.duration]
            avg_response_time = 0
            if completed_with_duration:
                avg_response_time = sum(op.duration for op in completed_with_duration) / len(completed_with_duration)
            
            # Calculate success rate
            success_rate = (completed_ops / total_ops * 100) if total_ops > 0 else 0
            
            # Get hourly breakdown
            hourly_stats = {}
            for i in range(24):
                hour_start = datetime.utcnow() - timedelta(hours=i+1)
                hour_end = datetime.utcnow() - timedelta(hours=i)
                hour_ops = [op for op in recent_ops if hour_start <= op.started_at < hour_end]
                
                hourly_stats[f"hour_{i}"] = {
                    "total": len(hour_ops),
                    "completed": len([op for op in hour_ops if op.status == "completed"]),
                    "failed": len([op for op in hour_ops if op.status == "failed"]),
                    "timestamp": hour_start.isoformat()
                }
            
            return {
                "summary": {
                    "total_operations": total_ops,
                    "completed_operations": completed_ops,
                    "failed_operations": failed_ops,
                    "active_operations": active_ops,
                    "success_rate": round(success_rate, 1),
                    "avg_response_time": round(avg_response_time, 2)
                },
                "hourly_breakdown": hourly_stats,
                "period": "24h",
                "timestamp": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            raise Exception(f"Failed to get performance metrics: {str(e)}")
    
    async def get_system_alerts(self, db: Session) -> Dict[str, Any]:
        """Get current system alerts and warnings"""
        alerts = []
        
        try:
            # Check for stuck operations
            stuck_cutoff = datetime.utcnow() - timedelta(minutes=30)
            stuck_ops = db.query(OperationDB).filter(
                OperationDB.status.in_(["processing", "fetching_context", "preparing"]),
                OperationDB.started_at < stuck_cutoff
            ).count()
            
            if stuck_ops > 0:
                alerts.append({
                    "type": "warning",
                    "message": f"{stuck_ops} operations may be stuck (running > 30 minutes)",
                    "severity": "medium",
                    "timestamp": datetime.utcnow().isoformat()
                })
            
            # Check error rate
            hour_ago = datetime.utcnow() - timedelta(hours=1)
            recent_ops = db.query(OperationDB).filter(OperationDB.started_at >= hour_ago).all()
            
            if recent_ops:
                failed_ops = [op for op in recent_ops if op.status == "failed"]
                error_rate = len(failed_ops) / len(recent_ops) * 100
                
                if error_rate > 20:
                    alerts.append({
                        "type": "error",
                        "message": f"High error rate: {error_rate:.1f}% ({len(failed_ops)}/{len(recent_ops)} operations failed)",
                        "severity": "high",
                        "timestamp": datetime.utcnow().isoformat()
                    })
            
            # Check recent error logs
            error_logs = db.query(LogEntryDB).filter(
                LogEntryDB.level == "ERROR",
                LogEntryDB.timestamp >= hour_ago
            ).count()
            
            if error_logs > 50:
                alerts.append({
                    "type": "error",
                    "message": f"High error frequency: {error_logs} error logs in last hour",
                    "severity": "high",
                    "timestamp": datetime.utcnow().isoformat()
                })
            
            return {"alerts": alerts, "total": len(alerts)}
            
        except Exception as e:
            return {"alerts": [], "total": 0, "error": str(e)} 