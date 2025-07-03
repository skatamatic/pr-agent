"""
Timezone utilities for ensuring all timestamps are stored in UTC and displayed properly
"""
from datetime import datetime, timezone
from typing import Optional, Any, Dict
import logging

logger = logging.getLogger(__name__)

def ensure_utc_timestamp(dt_input: Any) -> Optional[datetime]:
    """
    Convert various timestamp formats to UTC datetime object.
    
    Args:
        dt_input: Can be datetime object, ISO string, or None
        
    Returns:
        UTC datetime object or None if input is invalid
    """
    if dt_input is None:
        return None
        
    try:
        # If it's already a datetime object
        if isinstance(dt_input, datetime):
            # If it's naive (no timezone info), assume it's already UTC
            if dt_input.tzinfo is None:
                # Database stores UTC time as naive, just add UTC timezone marker
                return dt_input.replace(tzinfo=timezone.utc)
            # If it has timezone info, convert to UTC
            return dt_input.astimezone(timezone.utc)
            
        # If it's a string, parse it
        if isinstance(dt_input, str):
            # Handle common ISO formats
            if dt_input.endswith('Z'):
                # Already UTC
                return datetime.fromisoformat(dt_input.replace('Z', '+00:00'))
            elif '+' in dt_input or '-' in dt_input.split('T')[-1]:
                # Has timezone info
                return datetime.fromisoformat(dt_input).astimezone(timezone.utc)
            else:
                # Naive string - assume it's already UTC time
                logger.debug(f"Naive timestamp string detected, treating as UTC: {dt_input}")
                return datetime.fromisoformat(dt_input).replace(tzinfo=timezone.utc)
                
    except Exception as e:
        logger.error(f"Failed to convert timestamp {dt_input}: {e}")
        return None
        
def utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime"""
    return datetime.now(timezone.utc)

def utc_now_iso() -> str:
    """Get current UTC time as ISO string"""
    return utc_now().isoformat()

def to_utc_iso(dt_input: Any) -> Optional[str]:
    """Convert timestamp to UTC ISO string"""
    utc_dt = ensure_utc_timestamp(dt_input)
    return utc_dt.isoformat() if utc_dt else None

def validate_database_timestamps(db_session) -> Dict[str, Any]:
    """
    Validate that database timestamps are properly stored as UTC.
    Returns a report of any issues found.
    """
    from models import JobDB, OperationDB, LogEntryDB, RepositoryDB
    
    report = {
        'status': 'success',
        'issues_found': 0,
        'tables_checked': 0,
        'recommendations': []
    }
    
    try:
        # Check Jobs table
        report['tables_checked'] += 1
        jobs_count = db_session.query(JobDB).count()
        if jobs_count > 0:
            # Sample some recent jobs to check for timezone issues
            recent_jobs = db_session.query(JobDB).order_by(JobDB.started_at.desc()).limit(10).all()
            for job in recent_jobs:
                if job.started_at and job.started_at.tzinfo is None:
                    report['issues_found'] += 1
                    report['recommendations'].append("Jobs table contains naive timestamps")
                    break
        
        # Check Operations table
        report['tables_checked'] += 1
        ops_count = db_session.query(OperationDB).count()
        if ops_count > 0:
            recent_ops = db_session.query(OperationDB).order_by(OperationDB.started_at.desc()).limit(10).all()
            for op in recent_ops:
                if op.started_at and op.started_at.tzinfo is None:
                    report['issues_found'] += 1
                    report['recommendations'].append("Operations table contains naive timestamps")
                    break
        
        # Check Logs table
        report['tables_checked'] += 1
        logs_count = db_session.query(LogEntryDB).count()
        if logs_count > 0:
            recent_logs = db_session.query(LogEntryDB).order_by(LogEntryDB.timestamp.desc()).limit(10).all()
            for log in recent_logs:
                if log.timestamp and log.timestamp.tzinfo is None:
                    report['issues_found'] += 1
                    report['recommendations'].append("Logs table contains naive timestamps")
                    break
        
        if report['issues_found'] == 0:
            report['status'] = 'success'
            report['message'] = f"All {report['tables_checked']} tables have proper UTC timestamps"
        else:
            report['status'] = 'warning'
            report['message'] = f"Found {report['issues_found']} timezone issues in database"
            report['recommendations'].append("Consider running timezone migration if timestamps are consistently off")
            
    except Exception as e:
        report['status'] = 'error'
        report['message'] = f"Failed to validate timestamps: {e}"
        logger.error(f"Timestamp validation failed: {e}")
        
    return report

def migrate_naive_timestamps_to_utc(db_session, dry_run: bool = True) -> Dict[str, Any]:
    """
    Migration utility to convert naive timestamps to UTC.
    
    WARNING: This assumes naive timestamps were intended to be UTC.
    If they were local time, this could cause incorrect conversions.
    
    Args:
        db_session: Database session
        dry_run: If True, only report what would be changed without making changes
        
    Returns:
        Migration report
    """
    from models import JobDB, OperationDB, LogEntryDB
    
    report = {
        'status': 'success',
        'dry_run': dry_run,
        'tables_processed': 0,
        'records_updated': 0,
        'details': {}
    }
    
    try:
        # Process Jobs table
        jobs = db_session.query(JobDB).all()
        jobs_updated = 0
        for job in jobs:
            updated = False
            if job.started_at and job.started_at.tzinfo is None:
                if not dry_run:
                    job.started_at = job.started_at.replace(tzinfo=timezone.utc)
                updated = True
            if job.completed_at and job.completed_at.tzinfo is None:
                if not dry_run:
                    job.completed_at = job.completed_at.replace(tzinfo=timezone.utc)
                updated = True
            if job.last_updated and job.last_updated.tzinfo is None:
                if not dry_run:
                    job.last_updated = job.last_updated.replace(tzinfo=timezone.utc)
                updated = True
            if updated:
                jobs_updated += 1
        
        report['details']['jobs'] = f"{jobs_updated} jobs {'would be' if dry_run else 'were'} updated"
        report['tables_processed'] += 1
        report['records_updated'] += jobs_updated
        
        # Process Operations table
        operations = db_session.query(OperationDB).all()
        ops_updated = 0
        for op in operations:
            updated = False
            if op.started_at and op.started_at.tzinfo is None:
                if not dry_run:
                    op.started_at = op.started_at.replace(tzinfo=timezone.utc)
                updated = True
            if op.completed_at and op.completed_at.tzinfo is None:
                if not dry_run:
                    op.completed_at = op.completed_at.replace(tzinfo=timezone.utc)
                updated = True
            if op.last_updated and op.last_updated.tzinfo is None:
                if not dry_run:
                    op.last_updated = op.last_updated.replace(tzinfo=timezone.utc)
                updated = True
            if updated:
                ops_updated += 1
        
        report['details']['operations'] = f"{ops_updated} operations {'would be' if dry_run else 'were'} updated"
        report['tables_processed'] += 1
        report['records_updated'] += ops_updated
        
        # Process Logs table
        logs = db_session.query(LogEntryDB).all()
        logs_updated = 0
        for log in logs:
            if log.timestamp and log.timestamp.tzinfo is None:
                if not dry_run:
                    log.timestamp = log.timestamp.replace(tzinfo=timezone.utc)
                logs_updated += 1
        
        report['details']['logs'] = f"{logs_updated} logs {'would be' if dry_run else 'were'} updated"
        report['tables_processed'] += 1
        report['records_updated'] += logs_updated
        
        if not dry_run and report['records_updated'] > 0:
            db_session.commit()
            report['message'] = f"Successfully updated {report['records_updated']} records across {report['tables_processed']} tables"
        elif dry_run:
            report['message'] = f"Dry run: Would update {report['records_updated']} records across {report['tables_processed']} tables"
        else:
            report['message'] = "No timezone issues found"
            
    except Exception as e:
        if not dry_run:
            db_session.rollback()
        report['status'] = 'error'
        report['message'] = f"Migration failed: {e}"
        logger.error(f"Timezone migration failed: {e}")
        
    return report 