"""
Operation Service - Responsible for managing PR-Agent operations and logs
Follows Single Responsibility Principle and Open/Closed Principle
"""
import json
from datetime import datetime
from typing import Dict, Any, List, Optional
from sqlalchemy.orm import Session
from models import OperationDB, LogEntryDB, APIResponse


class OperationService:
    """Service for managing PR-Agent operations and their lifecycle"""
    
    def __init__(self):
        self.operation_handlers = {}
    
    async def get_operations(
        self, 
        db: Session,
        limit: int = 100,
        status: Optional[str] = None,
        repo: Optional[str] = None
    ) -> APIResponse:
        """Get list of operations with optional filtering"""
        query = db.query(OperationDB)
        
        if status and status != "all":
            query = query.filter(OperationDB.status == status)
            
        if repo and repo != "all":
            query = query.filter(OperationDB.repo == repo)
        
        operations = query.order_by(OperationDB.started_at.desc()).limit(limit).all()
        
        # Convert to API format
        operation_list = []
        for op in operations:
            operation_list.append({
                "id": op.id,
                "operation_id": op.operation_id,
                "request_id": op.request_id,
                "command": op.command,
                "repo": op.repo,
                "pr_url": op.pr_url,
                "status": op.status,
                "started_at": op.started_at.isoformat() if op.started_at else None,
                "last_updated": op.last_updated.isoformat() if op.last_updated else None,
                "completed_at": op.completed_at.isoformat() if op.completed_at else None,
                "operation_type": op.command,  # For compatibility
                "duration": op.duration,
                "error_details": op.error_details
            })
        
        return APIResponse(data={"operations": operation_list}, total=len(operation_list))
    
    async def get_operation(self, db: Session, operation_id: str) -> Optional[OperationDB]:
        """Get specific operation details"""
        return db.query(OperationDB).filter(OperationDB.operation_id == operation_id).first()
    
    async def update_operation_status(self, db: Session, log_data: Dict[str, Any]) -> None:
        """Update or create operation with enhanced tracking and metrics"""
        try:
            # Create more robust operation ID
            operation_id = f"{log_data.get('repo', 'unknown')}_{log_data.get('command', 'unknown')}_{hash(log_data.get('pr_url', 'no-url'))}"
            
            # Find existing operation
            existing_op = db.query(OperationDB).filter(OperationDB.operation_id == operation_id).first()
            
            if existing_op:
                # Update existing operation with duration calculation
                existing_op.status = log_data.get('status')
                existing_op.last_updated = datetime.utcnow()
                
                # Calculate duration for completed operations
                if log_data.get('status') in ["completed", "failed"] and not existing_op.completed_at:
                    existing_op.completed_at = datetime.utcnow()
                    if existing_op.started_at:
                        duration = (existing_op.completed_at - existing_op.started_at).total_seconds()
                        existing_op.duration = duration
                        
                # Track error information
                if log_data.get('status') == "failed" and log_data.get('error'):
                    existing_op.error_details = json.dumps(log_data.get('error'))
                    
            else:
                # Create new operation with comprehensive tracking
                operation = OperationDB(
                    operation_id=operation_id,
                    command=log_data.get('command'),
                    repo=log_data.get('repo'),
                    pr_url=log_data.get('pr_url'),
                    status=log_data.get('status'),
                    started_at=datetime.fromisoformat(log_data.get('timestamp', datetime.utcnow().isoformat()).replace('Z', '+00:00')),
                    last_updated=datetime.utcnow(),
                    error_details=json.dumps(log_data.get('error')) if log_data.get('error') else None
                )
                db.add(operation)
            
            db.commit()
            
        except Exception as e:
            db.rollback()
            raise Exception(f"Failed to update operation status: {str(e)}")
    
    def register_operation_handler(self, operation_type: str, handler):
        """Register a handler for specific operation types (Open/Closed Principle)"""
        self.operation_handlers[operation_type] = handler
    
    async def process_operation_event(self, operation_type: str, event_data: Dict[str, Any]):
        """Process operation events using registered handlers"""
        if operation_type in self.operation_handlers:
            return await self.operation_handlers[operation_type](event_data)
        else:
            # Default handler
            return await self._default_operation_handler(event_data)
    
    async def _default_operation_handler(self, event_data: Dict[str, Any]):
        """Default operation event handler"""
        return {"status": "processed", "data": event_data}


class LogService:
    """Service for managing logs and log entries"""
    
    def __init__(self):
        self.log_processors = []
    
    async def get_logs(
        self,
        db: Session,
        limit: int = 1000,
        level: Optional[str] = None,
        search: Optional[str] = None,
        repo: Optional[str] = None,
        job_id: Optional[str] = None,
        operation_id: Optional[str] = None
    ) -> APIResponse:
        """Get list of logs with optional filtering"""
        query = db.query(LogEntryDB)
        
        if level and level != "all":
            query = query.filter(LogEntryDB.level == level)
        
        if search:
            query = query.filter(LogEntryDB.message.contains(search))
            
        if repo and repo != "all":
            query = query.filter(LogEntryDB.repo == repo)
        
        if job_id:
            query = query.filter(LogEntryDB.job_id == job_id)
        
        if operation_id:
            query = query.filter(LogEntryDB.operation_id == operation_id)
        
        logs = query.order_by(LogEntryDB.timestamp.desc()).limit(limit).all()
        
        # Convert to API format
        log_list = []
        for log in logs:
            log_list.append({
                "id": log.id,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                "level": log.level,
                "message": log.message,
                "module": log.module,
                "function": log.function,
                "pr_url": log.pr_url,
                "command": log.command,
                "repo": log.repo,
                "request_id": log.request_id,
                "job_id": getattr(log, 'job_id', None),  # Safe access for backward compatibility
                "operation_id": getattr(log, 'operation_id', None),  # Safe access for backward compatibility
                "status": log.status,
                "error": log.error,
                "artifact": log.artifact
            })
        
        return APIResponse(data={"logs": log_list}, total=len(log_list))
    
    async def get_logs_by_job(self, db: Session, job_id: str) -> APIResponse:
        """Get logs for specific job"""
        logs = db.query(LogEntryDB).filter(
            LogEntryDB.job_id == job_id
        ).order_by(LogEntryDB.timestamp.desc()).all()
        
        # Convert to API format
        log_list = []
        for log in logs:
            log_list.append({
                "id": log.id,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                "level": log.level,
                "message": log.message,
                "module": log.module,
                "function": log.function,
                "pr_url": log.pr_url,
                "command": log.command,
                "repo": log.repo,
                "request_id": log.request_id,
                "job_id": getattr(log, 'job_id', None),
                "operation_id": getattr(log, 'operation_id', None),
                "status": log.status,
                "error": log.error,
                "artifact": log.artifact
            })
        
        return APIResponse(data={"logs": log_list}, total=len(log_list))
    
    async def get_logs_by_operation(self, db: Session, operation_id: str) -> APIResponse:
        """Get logs for specific operation using request_id for linking"""
        # First, try to find the operation to get its request_id
        operation = db.query(OperationDB).filter(OperationDB.operation_id == operation_id).first()
        
        if operation and operation.request_id:
            # Filter logs by request_id for proper linking
            logs = db.query(LogEntryDB).filter(
                LogEntryDB.request_id == operation.request_id
            ).order_by(LogEntryDB.timestamp.desc()).all()
        else:
            # Fallback to empty list if operation not found
            logs = []
        
        # Convert to API format
        log_list = []
        for log in logs:
            log_list.append({
                "id": log.id,
                "timestamp": log.timestamp.isoformat() if log.timestamp else None,
                "level": log.level,
                "message": log.message,
                "module": log.module,
                "function": log.function,
                "pr_url": log.pr_url,
                "command": log.command,
                "repo": log.repo,
                "request_id": log.request_id,
                "status": log.status,
                "error": log.error,
                "artifact": log.artifact
            })
        
        return APIResponse(data={"logs": log_list}, total=len(log_list))
    
    async def create_log_entry(self, db: Session, log_data: Dict[str, Any]) -> LogEntryDB:
        """Create a new log entry"""
        log_entry = LogEntryDB(
            timestamp=datetime.fromisoformat(log_data.get('timestamp', datetime.utcnow().isoformat()).replace('Z', '+00:00')),
            level=log_data.get('level'),
            message=log_data.get('message'),
            module=log_data.get('module'),
            function=log_data.get('function'),
            line=log_data.get('line'),
            
            # FIXED: Set job_id and operation_id fields
            job_id=log_data.get('job_id'),
            operation_id=log_data.get('operation_id'),
            
            # Context information
            pr_url=log_data.get('pr_url'),
            command=log_data.get('command'),
            installation_id=log_data.get('installation_id'),
            repo=log_data.get('repo'),
            sender=log_data.get('sender'),
            request_id=log_data.get('request_id'),
            sub_feature=log_data.get('sub_feature'),
            
            # Status and analytics
            status=log_data.get('status'),
            analytics=log_data.get('analytics', False),
            
            # Artifacts and error info
            artifact=log_data.get('artifact'),
            artifacts=log_data.get('artifacts'),
            error=log_data.get('error'),
            
            # Application metadata
            app_name=log_data.get('app_name'),
            build_number=log_data.get('build_number'),
            git_provider=log_data.get('git_provider'),
            received_at=datetime.utcnow().isoformat()
        )
        
        try:
            db.add(log_entry)
            db.flush()  # Flush to get the ID without committing
            db.refresh(log_entry)  # Refresh to get the generated ID
            db.commit()  # Now commit the transaction
        except Exception as e:
            db.rollback()
            raise e
        
        # Process log with registered processors
        for processor in self.log_processors:
            await processor(log_entry)
        
        return log_entry
    
    def register_log_processor(self, processor):
        """Register a log processor (Open/Closed Principle)"""
        self.log_processors.append(processor)
    
    async def process_batch_logs(self, db: Session, logs_data: List[Dict[str, Any]]) -> List[LogEntryDB]:
        """Process a batch of log entries"""
        created_logs = []
        
        for log_data in logs_data:
            log_entry = await self.create_log_entry(db, log_data)
            created_logs.append(log_entry)
        
        return created_logs 