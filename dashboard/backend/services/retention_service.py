import os
import sqlite3
import json
import gzip
import shutil
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from pathlib import Path
import subprocess

logger = logging.getLogger(__name__)

class RetentionService:
    """
    Database retention and management service with industry best practices
    """
    
    def __init__(self, database_manager, db_path: str = "dashboard.db"):
        self.database_manager = database_manager
        self.db_path = db_path
        
        # Get configurable backup directory
        backup_dir = self.database_manager.get_system_setting("backup_directory")
        if backup_dir:
            self.backup_dir = Path(backup_dir)
        else:
            # Default to a backups folder in the same directory as the database
            self.backup_dir = Path(self.db_path).parent / "backups"
        
        # Ensure backup directory exists
        self.backup_dir.mkdir(exist_ok=True)
        
        # Industry standard defaults for SQLite databases
        self.default_config = {
            # Size limits (in MB)
            "max_db_size_mb": 500,  # 500MB is reasonable for SQLite
            "warning_db_size_mb": 400,  # Warn at 80% capacity
            
            # Record count limits
            "max_logs": 50000,  # Keep last 50k logs
            "max_jobs": 10000,   # Keep last 10k jobs
            "max_operations": 25000,  # Keep last 25k operations
            "max_notification_events": 5000,  # Keep last 5k notification events
            
            # Time-based retention (in days)
            "log_retention_days": 30,      # 30 days of logs
            "job_retention_days": 90,      # 90 days of jobs
            "operation_retention_days": 60, # 60 days of operations
            "notification_retention_days": 30, # 30 days of notifications
            
            # Cleanup strategy
            "cleanup_strategy": "hybrid",  # "time", "count", "hybrid"
            "cleanup_batch_size": 1000,   # Delete in batches to avoid locks
            "auto_cleanup_enabled": True,
            "cleanup_schedule_hours": 24, # Run cleanup every 24 hours
            
            # Backup settings
            "auto_backup_enabled": True,
            "backup_schedule_hours": 168,  # Weekly backups (24 * 7)
            "backup_before_cleanup": True,
            "max_backup_files": 10,
            "backup_compression": True,
            
            # Performance settings
            "vacuum_after_cleanup": True,  # Reclaim space after deletion
            "analyze_after_cleanup": True, # Update statistics
        }
        
        # Note: backup directory already initialized above - this section is redundant and removed to avoid Path variable conflicts
        
        # Note: System startup logging moved to be called after server is running
    
    def _log_system_startup(self):
        """Log backup system startup with configuration summary"""
        try:
            config = self.get_retention_config()
            config_summary = {
                'auto_backup_enabled': config.get('auto_backup_enabled', False),
                'backup_schedule_hours': config.get('backup_schedule_hours', 168),
                'backup_compression': config.get('backup_compression', True),
                'max_backup_files': config.get('max_backup_files', 10),
                'backup_directory': str(self.backup_dir) if self.backup_dir else 'default'
            }
            
            if config.get('auto_backup_enabled', False):
                interval_desc = f"every {config.get('backup_schedule_hours', 168)} hours"
                self._log_to_system('INFO', 
                    f"Backup system started - Automatic backups enabled ({interval_desc}, compression: {config.get('backup_compression', True)}, max files: {config.get('max_backup_files', 10)})",
                    {'config': config_summary, 'system_event': 'backup_system_start'}
                )
            else:
                self._log_to_system('INFO', 
                    f"Backup system started - Automatic backups disabled (manual backups only)",
                    {'config': config_summary, 'system_event': 'backup_system_start'}
                )
        except Exception as e:
            logger.warning(f"Failed to log backup system startup: {e}")
    
    def _log_system_shutdown(self):
        """Log backup system shutdown"""
        try:
            self._log_to_system('INFO', 
                "Backup system stopped - Automatic backup scheduler shutdown",
                {'system_event': 'backup_system_stop'}
            )
        except Exception as e:
            # Use basic logging if system logging fails during shutdown
            logger.error(f"Failed to log backup system shutdown: {e}")
    
    def get_retention_config(self) -> Dict[str, Any]:
        """Get current retention configuration"""
        try:
            # Try to load from database first
            config = self.database_manager.get_system_setting("retention_config")
            if config:
                # Merge with defaults to ensure all keys exist
                merged_config = self.default_config.copy()
                merged_config.update(json.loads(config))
                return merged_config
            return self.default_config.copy()
        except Exception as e:
            logger.error(f"Failed to load retention config: {e}")
            return self.default_config.copy()
    
    def update_retention_config(self, config: Dict[str, Any]) -> bool:
        """Update retention configuration"""
        try:
            # Get current config to compare changes
            old_config = self.get_retention_config()
            
            # Validate new configuration
            validated_config = self._validate_config(config)
            
            # Check for important changes to log
            self._log_config_changes(old_config, validated_config)
            
            # Save to database
            self.database_manager.set_system_setting(
                "retention_config", 
                json.dumps(validated_config)
            )
            
            logger.info("Retention configuration updated successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to update retention config: {e}")
            return False
    
    def _validate_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Validate and sanitize retention configuration"""
        validated = self.default_config.copy()
        
        # Validate numeric values
        numeric_fields = [
            "max_db_size_mb", "warning_db_size_mb", "max_logs", "max_jobs", 
            "max_operations", "max_notification_events", "log_retention_days",
            "job_retention_days", "operation_retention_days", "notification_retention_days",
            "cleanup_batch_size", "cleanup_schedule_hours", "backup_schedule_hours", "max_backup_files"
        ]
        
        for field in numeric_fields:
            if field in config and isinstance(config[field], (int, float)) and config[field] > 0:
                validated[field] = int(config[field])
        
        # Validate string fields
        if config.get("cleanup_strategy") in ["time", "count", "hybrid"]:
            validated["cleanup_strategy"] = config["cleanup_strategy"]
        
        # Validate boolean fields
        boolean_fields = [
            "auto_cleanup_enabled", "auto_backup_enabled", "backup_before_cleanup",
            "backup_compression", "vacuum_after_cleanup", "analyze_after_cleanup"
        ]
        
        for field in boolean_fields:
            if field in config and isinstance(config[field], bool):
                validated[field] = config[field]
        
        # Ensure warning size is less than max size
        if validated["warning_db_size_mb"] >= validated["max_db_size_mb"]:
            validated["warning_db_size_mb"] = int(validated["max_db_size_mb"] * 0.8)
        
        return validated
    
    def _log_config_changes(self, old_config: Dict[str, Any], new_config: Dict[str, Any]):
        """Log important configuration changes, especially backup scheduling changes"""
        try:
            # Check for backup scheduling changes
            old_backup_enabled = old_config.get('auto_backup_enabled', False)
            new_backup_enabled = new_config.get('auto_backup_enabled', False)
            
            if old_backup_enabled != new_backup_enabled:
                if new_backup_enabled:
                    schedule_hours = new_config.get('backup_schedule_hours', 168)
                    compression = new_config.get('backup_compression', True)
                    self._log_to_system('INFO', 
                        f"Automatic backup scheduling enabled - Backups will run every {schedule_hours} hours (compression: {compression})",
                        {
                            'system_event': 'backup_scheduling_enabled',
                            'config_change': True,
                            'schedule_hours': schedule_hours,
                            'compression': compression,
                            'max_backup_files': new_config.get('max_backup_files', 10)
                        }
                    )
                else:
                    self._log_to_system('INFO', 
                        "Automatic backup scheduling disabled - Only manual backups will be available",
                        {
                            'system_event': 'backup_scheduling_disabled',
                            'config_change': True
                        }
                    )
            elif new_backup_enabled:
                # Check for schedule changes while backup is enabled
                old_schedule = old_config.get('backup_schedule_hours', 168)
                new_schedule = new_config.get('backup_schedule_hours', 168)
                old_compression = old_config.get('backup_compression', True)
                new_compression = new_config.get('backup_compression', True)
                
                if old_schedule != new_schedule or old_compression != new_compression:
                    self._log_to_system('INFO', 
                        f"Automatic backup schedule updated - Every {new_schedule} hours (compression: {new_compression})",
                        {
                            'system_event': 'backup_schedule_updated',
                            'config_change': True,
                            'old_schedule_hours': old_schedule,
                            'new_schedule_hours': new_schedule,
                            'old_compression': old_compression,
                            'new_compression': new_compression
                        }
                    )
            
            # Check for cleanup changes
            old_cleanup_enabled = old_config.get('auto_cleanup_enabled', True)
            new_cleanup_enabled = new_config.get('auto_cleanup_enabled', True)
            
            if old_cleanup_enabled != new_cleanup_enabled:
                if new_cleanup_enabled:
                    cleanup_hours = new_config.get('cleanup_schedule_hours', 24)
                    self._log_to_system('INFO', 
                        f"Automatic database cleanup enabled - Cleanup will run every {cleanup_hours} hours",
                        {
                            'system_event': 'cleanup_scheduling_enabled',
                            'config_change': True,
                            'cleanup_hours': cleanup_hours
                        }
                    )
                else:
                    self._log_to_system('INFO', 
                        "Automatic database cleanup disabled - Only manual cleanup will be available",
                        {
                            'system_event': 'cleanup_scheduling_disabled',
                            'config_change': True
                        }
                    )
                    
        except Exception as e:
            logger.warning(f"Failed to log configuration changes: {e}")
    
    def _log_to_system(self, level: str, message: str, context: dict = None):
        """Create a system log entry for retention/backup events"""
        try:
            # Import requests to send log directly to dashboard
            import requests
            
            # Create a system log entry
            log_data = {
                'timestamp': datetime.utcnow().isoformat(),
                'level': level,
                'message': f"[RETENTION] {message}",
                'source': 'retention_system',
                'job_id': None,  # System logs don't have job IDs  
                'operation_id': None,  # System logs don't have operation IDs
                'repository': None,
                'status': None
            }
            
            # Add context to log data
            if context:
                log_data.update(context)
            
            # Send directly to dashboard backend
            try:
                requests.post('http://localhost:8000/logs/immediate', json=log_data, timeout=2)
            except Exception:
                # If dashboard is not available, log normally - but don't fail
                try:
                    getattr(logger, level.lower(), logger.info)(message)
                except Exception:
                    pass  # Don't let logging failures cascade
                
        except Exception:
            # Don't let logging errors break the retention service
            pass
    
    def should_perform_automatic_backup(self) -> bool:
        """Check if automatic backup should be performed based on schedule"""
        try:
            config = self.get_retention_config()
            
            # Check if auto backup is enabled
            if not config.get("auto_backup_enabled", True):
                return False
            
            # Get last backup time
            last_backup = self.database_manager.get_system_setting("last_backup_time")
            
            # If no previous backup, create one now
            if not last_backup:
                return True
            
            # Check if enough time has passed
            try:
                last_backup_dt = datetime.fromisoformat(last_backup.replace('Z', '+00:00'))
                schedule_hours = config.get("backup_schedule_hours", 168)  # Default weekly
                next_backup_dt = last_backup_dt + timedelta(hours=schedule_hours)
                return datetime.utcnow() >= next_backup_dt.replace(tzinfo=None)
            except Exception as e:
                logger.warning(f"Could not parse last backup time: {e}")
                return True  # Perform backup if time parsing fails
                
        except Exception as e:
            logger.error(f"Error checking backup schedule: {e}")
            return False
    
    def perform_automatic_backup(self) -> Dict[str, Any]:
        """Perform automatic backup if enabled and due"""
        try:
            config = self.get_retention_config()
            
            if not config.get('auto_backup_enabled', False):
                return {"success": False, "reason": "Auto backup disabled"}
            
            # Check if backup is due
            schedule_hours = config.get('backup_schedule_hours', 168)  # default weekly
            if self.last_backup_time:
                hours_since_last = (datetime.utcnow() - self.last_backup_time).total_seconds() / 3600
                if hours_since_last < schedule_hours:
                    return {"success": False, "reason": f"Backup not due for {schedule_hours - hours_since_last:.1f} hours"}
            
            # Perform automatic backup
            if not self.backup_dir.exists():
                self.backup_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"dashboard_backup_auto_{timestamp}.db"
            
            compression_enabled = config.get('backup_compression', True)
            if compression_enabled:
                backup_filename += ".gz"
            
            backup_path = self.backup_dir / backup_filename
            
            # Log automatic backup start
            self._log_to_system('INFO', 
                f"Starting automatic database backup - {backup_filename} (scheduled every {schedule_hours}h, compression: {compression_enabled})",
                {
                    'backup_type': 'automatic',
                    'compressed': compression_enabled,
                    'filename': backup_filename,
                    'schedule_hours': schedule_hours,
                    'system_event': 'backup_start'
                }
            )
            
            # Create backup
            if compression_enabled:
                with gzip.open(backup_path, 'wb') as f:
                    subprocess.run(['sqlite3', self.db_path, '.dump'], stdout=f, check=True)
            else:
                shutil.copy2(self.db_path, backup_path)
            
            # Get file info
            file_size = backup_path.stat().st_size
            file_size_mb = round(file_size / (1024 * 1024), 2)
            
            # Update last backup time
            self.last_backup_time = datetime.utcnow()
            
            # Log automatic backup completion
            self._log_to_system('INFO', 
                f"Automatic database backup completed - {backup_filename} ({file_size_mb} MB) - Next backup in {schedule_hours}h",
                {
                    'backup_type': 'automatic',
                    'compressed': compression_enabled,
                    'filename': backup_filename,
                    'file_size_mb': file_size_mb,
                    'file_size_bytes': file_size,
                    'schedule_hours': schedule_hours,
                    'next_backup_due': (datetime.utcnow() + timedelta(hours=schedule_hours)).isoformat(),
                    'system_event': 'backup_completed'
                }
            )
            
            # Cleanup old backups
            self._cleanup_old_backups()
            
            return {
                "success": True,
                "filename": backup_filename,
                "path": str(backup_path),
                "size": file_size,
                "size_mb": file_size_mb,
                "compressed": compression_enabled,
                "type": "automatic",
                "created_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            error_msg = f"Automatic backup failed: {str(e)}"
            self._log_to_system('ERROR', error_msg, {
                'backup_type': 'automatic',
                'error': str(e),
                'system_event': 'backup_failed'
            })
            return {"success": False, "error": error_msg}
    
    def get_database_stats(self) -> Dict[str, Any]:
        """Get comprehensive database statistics"""
        try:
            stats = {
                "size_bytes": 0,
                "size_mb": 0,
                "jobs_count": 0,
                "logs_count": 0,
                "operations_count": 0,
                "notification_events_count": 0,
                "table_stats": {},
                "last_cleanup": None,
                "next_cleanup": None,
                "warnings": []
            }
            
            # Get file size
            if os.path.exists(self.db_path):
                file_size = os.path.getsize(self.db_path)
                stats["size_bytes"] = file_size
                stats["size_mb"] = round(file_size / (1024 * 1024), 2)
            
            # Get table statistics
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Map table names to actual database tables and their timestamp columns
            table_mappings = {
                "jobs": ("jobs", "started_at"),
                "logs": ("log_entries", "timestamp"),
                "operations": ("operations", "started_at"),
                "notification_events": ("notification_events", "created_at")
            }
            
            for logical_name, (actual_table, timestamp_col) in table_mappings.items():
                try:
                    # Get count
                    cursor.execute(f"SELECT COUNT(*) FROM {actual_table}")
                    count = cursor.fetchone()[0]
                    
                    # Set the count in the main stats
                    stats[f"{logical_name}_count"] = count
                    
                    # Get oldest and newest records
                    try:
                        cursor.execute(f"SELECT MIN({timestamp_col}), MAX({timestamp_col}) FROM {actual_table}")
                        min_time, max_time = cursor.fetchone()
                    except sqlite3.OperationalError:
                        # Column might not exist
                        min_time, max_time = None, None
                    
                    stats["table_stats"][logical_name] = {
                        "count": count,
                        "oldest_record": min_time,
                        "newest_record": max_time,
                        "actual_table": actual_table,
                        "timestamp_column": timestamp_col
                    }
                except sqlite3.OperationalError as e:
                    # Table might not exist
                    logger.warning(f"Table {actual_table} not found: {e}")
                    stats[f"{logical_name}_count"] = 0
                    stats["table_stats"][logical_name] = {
                        "count": 0,
                        "oldest_record": None,
                        "newest_record": None,
                        "actual_table": actual_table,
                        "timestamp_column": timestamp_col
                    }
            
            conn.close()
            
            # Check for warnings
            config = self.get_retention_config()
            
            if stats["size_mb"] > config.get("warning_db_size_mb", 400):
                stats["warnings"].append({
                    "type": "size_warning",
                    "message": f"Database size ({stats['size_mb']}MB) exceeds warning threshold ({config.get('warning_db_size_mb', 400)}MB)"
                })
            
            # Check count warnings for each table type
            count_limits = {
                "jobs": config.get("max_jobs", 10000),
                "logs": config.get("max_logs", 50000),
                "operations": config.get("max_operations", 25000),
                "notification_events": config.get("max_notification_events", 5000)
            }
            
            for table_type, limit in count_limits.items():
                count = stats.get(f"{table_type}_count", 0)
                if count > limit:
                    stats["warnings"].append({
                        "type": "count_warning",
                        "message": f"Table {table_type} has {count} records, exceeding limit of {limit}"
                    })
            
            # Get cleanup history
            try:
                last_cleanup = self.database_manager.get_system_setting("last_cleanup_time")
                if last_cleanup:
                    stats["last_cleanup"] = last_cleanup
                    
                    if config["auto_cleanup_enabled"]:
                        last_cleanup_dt = datetime.fromisoformat(last_cleanup)
                        next_cleanup_dt = last_cleanup_dt + timedelta(hours=config["cleanup_schedule_hours"])
                        stats["next_cleanup"] = next_cleanup_dt.isoformat()
            except:
                pass
            
            return stats
            
        except Exception as e:
            logger.error(f"Failed to get database stats: {e}")
            return {"error": str(e)}
    
    def perform_cleanup(self, dry_run: bool = False) -> Dict[str, Any]:
        """Perform database cleanup based on retention policy"""
        config = self.get_retention_config()
        results = {
            "dry_run": dry_run,
            "tables_processed": {},
            "total_deleted": 0,
            "space_reclaimed_mb": 0,
            "errors": []
        }
        
        try:
            # Backup before cleanup if enabled
            if config["backup_before_cleanup"] and not dry_run:
                backup_result = self.create_backup()
                if not backup_result["success"]:
                    results["errors"].append(f"Backup failed: {backup_result['error']}")
                    return results
            
            initial_size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
            
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Define cleanup rules for each table with correct column mappings
            cleanup_rules = {
                "log_entries": {  # Actual table name
                    "time_field": "timestamp",
                    "retention_days": config["log_retention_days"],
                    "max_records": config["max_logs"],
                    "logical_name": "logs"
                },
                "jobs": {  # Actual table name
                    "time_field": "started_at",  # Correct column name
                    "retention_days": config["job_retention_days"],
                    "max_records": config["max_jobs"],
                    "logical_name": "jobs"
                },
                "operations": {  # Actual table name
                    "time_field": "started_at",  # Correct column name
                    "retention_days": config["operation_retention_days"],
                    "max_records": config["max_operations"],
                    "logical_name": "operations"
                },
                "notification_events": {  # Actual table name
                    "time_field": "timestamp",  # Correct column name
                    "retention_days": config["notification_retention_days"],
                    "max_records": config["max_notification_events"],
                    "logical_name": "notification_events"
                }
            }
            
            for table, rules in cleanup_rules.items():
                try:
                    deleted_count = self._cleanup_table(
                        cursor, table, rules, config, dry_run
                    )
                    logical_name = rules.get("logical_name", table)
                    results["tables_processed"][logical_name] = deleted_count
                    results["total_deleted"] += deleted_count
                except Exception as e:
                    logical_name = rules.get("logical_name", table)
                    results["errors"].append(f"Error cleaning {logical_name}: {str(e)}")
            
            if not dry_run:
                conn.commit()
                
                # Vacuum and analyze if enabled
                if config["vacuum_after_cleanup"]:
                    cursor.execute("VACUUM")
                
                if config["analyze_after_cleanup"]:
                    cursor.execute("ANALYZE")
                
                # Record cleanup time
                self.database_manager.set_system_setting(
                    "last_cleanup_time", 
                    datetime.utcnow().isoformat()
                )
            
            conn.close()
            
            # Calculate space reclaimed
            if not dry_run:
                final_size = os.path.getsize(self.db_path) if os.path.exists(self.db_path) else 0
                space_reclaimed = max(0, initial_size - final_size)
                results["space_reclaimed_mb"] = round(space_reclaimed / (1024 * 1024), 2)
            
            logger.info(f"Cleanup completed: {results['total_deleted']} records deleted")
            
            # Log system activity
            if not dry_run:
                self._log_to_system("INFO", f"Database cleanup completed: {results['total_deleted']} records deleted, {results['space_reclaimed_mb']} MB reclaimed")
            
        except Exception as e:
            results["errors"].append(f"Cleanup failed: {str(e)}")
            logger.error(f"Database cleanup failed: {e}")
            self._log_to_system("ERROR", f"Database cleanup failed: {str(e)}")
        
        return results
    
    def _cleanup_table(self, cursor, table: str, rules: Dict[str, Any], 
                      config: Dict[str, Any], dry_run: bool) -> int:
        """Clean up a specific table based on rules"""
        strategy = config["cleanup_strategy"]
        batch_size = config["cleanup_batch_size"]
        deleted_count = 0
        time_field = rules["time_field"]
        
        # Check if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table,))
        if not cursor.fetchone():
            return 0
        
        # Check if the timestamp column exists
        cursor.execute(f"PRAGMA table_info({table})")
        columns = [col[1] for col in cursor.fetchall()]
        if time_field not in columns:
            logger.warning(f"Table {table} does not have column {time_field}, skipping time-based cleanup")
            time_field = None
        
        if strategy in ["time", "hybrid"] and time_field:
            # Time-based cleanup (only if timestamp column exists)
            cutoff_date = datetime.utcnow() - timedelta(days=rules["retention_days"])
            cutoff_str = cutoff_date.isoformat()
            
            if dry_run:
                cursor.execute(
                    f"SELECT COUNT(*) FROM {table} WHERE {time_field} < ?",
                    (cutoff_str,)
                )
                time_based_count = cursor.fetchone()[0]
                deleted_count += time_based_count
            else:
                # Delete in batches to avoid long locks
                while True:
                    cursor.execute(
                        f"DELETE FROM {table} WHERE id IN ("
                        f"SELECT id FROM {table} WHERE {time_field} < ? LIMIT ?"
                        f")",
                        (cutoff_str, batch_size)
                    )
                    batch_deleted = cursor.rowcount
                    deleted_count += batch_deleted
                    if batch_deleted < batch_size:
                        break
        
        if strategy in ["count", "hybrid"]:
            # Count-based cleanup
            cursor.execute(f"SELECT COUNT(*) FROM {table}")
            current_count = cursor.fetchone()[0]
            
            if current_count > rules["max_records"]:
                excess_count = current_count - rules["max_records"]
                
                if dry_run:
                    deleted_count += excess_count
                else:
                    # Delete oldest records beyond the limit
                    if time_field:
                        # Use timestamp for ordering if available
                        cursor.execute(
                            f"DELETE FROM {table} WHERE id IN ("
                            f"SELECT id FROM {table} ORDER BY {time_field} ASC LIMIT ?"
                            f")",
                            (excess_count,)
                        )
                    else:
                        # Fall back to ID ordering if no timestamp
                        cursor.execute(
                            f"DELETE FROM {table} WHERE id IN ("
                            f"SELECT id FROM {table} ORDER BY id ASC LIMIT ?"
                            f")",
                            (excess_count,)
                        )
                    deleted_count += cursor.rowcount
        
        return deleted_count
    
    def create_backup(self, compressed: bool = True) -> Dict[str, Any]:
        """Create a manual database backup"""
        try:
            if not self.backup_dir.exists():
                self.backup_dir.mkdir(parents=True, exist_ok=True)
            
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"dashboard_backup_manual_{timestamp}.db"
            
            if compressed:
                backup_filename += ".gz"
            
            backup_path = self.backup_dir / backup_filename
            
            # Log backup start
            self._log_to_system('INFO', 
                f"Starting manual database backup - {backup_filename} (compression: {compressed})",
                {
                    'backup_type': 'manual',
                    'compressed': compressed,
                    'filename': backup_filename,
                    'system_event': 'backup_start'
                }
            )
            
            # Create backup
            if compressed:
                with gzip.open(backup_path, 'wt') as f:
                    # Use Python's sqlite3 module instead of subprocess for cross-platform compatibility
                    conn = sqlite3.connect(self.db_path)
                    for line in conn.iterdump():
                        f.write(f'{line}\n')
                    conn.close()
            else:
                shutil.copy2(self.db_path, backup_path)
            
            # Get file info
            file_size = backup_path.stat().st_size
            file_size_mb = round(file_size / (1024 * 1024), 2)
            
            # Log backup completion
            self._log_to_system('INFO', 
                f"Manual database backup completed - {backup_filename} ({file_size_mb} MB)",
                {
                    'backup_type': 'manual',
                    'compressed': compressed,
                    'filename': backup_filename,
                    'file_size_mb': file_size_mb,
                    'file_size_bytes': file_size,
                    'system_event': 'backup_completed'
                }
            )
            
            # Cleanup old manual backups if needed
            self._cleanup_old_backups()
            
            return {
                "success": True,
                "filename": backup_filename,
                "path": str(backup_path),
                "size": file_size,
                "size_mb": file_size_mb,
                "compressed": compressed,
                "type": "manual",
                "created_at": datetime.utcnow().isoformat()
            }
            
        except Exception as e:
            error_msg = f"Manual backup failed: {str(e)}"
            self._log_to_system('ERROR', error_msg, {
                'backup_type': 'manual',
                'error': str(e),
                'system_event': 'backup_failed'
            })
            return {"success": False, "error": error_msg}
    
    def _cleanup_old_backups(self):
        """Remove old backup files to maintain the specified limit"""
        try:
            backup_files = list(self.backup_dir.glob("dashboard_backup_*.db*"))
            
            # Filter by backup type if specified
            backup_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
            
            # Remove excess files
            for old_backup in backup_files[self.default_config["max_backup_files"]:]:
                try:
                    size_mb = round(old_backup.stat().st_size / (1024 * 1024), 2)
                    old_backup.unlink()
                    logger.info(f"Removed old backup: {old_backup}")
                    self._log_to_system("INFO", f"Old backup removed: {old_backup.name} ({size_mb} MB)")
                except Exception as e:
                    logger.warning(f"Failed to remove backup {old_backup}: {e}")
                
        except Exception as e:
            logger.error(f"Failed to cleanup old backups: {e}")
            self._log_to_system("ERROR", f"Failed to cleanup old backups: {str(e)}")
    
    def export_data(self, format: str = "json", table_filter: List[str] = None) -> Dict[str, Any]:
        """Export database data - returns data for download instead of writing to file"""
        try:
            if table_filter is None:
                table_filter = []
                
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            
            if format.lower() == "json":
                return self._export_json_data(timestamp, table_filter)
            elif format.lower() == "csv":
                return self._export_csv_data(timestamp, table_filter)
            else:
                return {"success": False, "error": f"Unsupported format: {format}"}
                
        except Exception as e:
            logger.error(f"Data export failed: {e}")
            return {"success": False, "error": str(e)}
    
    def _export_json_data(self, timestamp: str, table_filter: List[str]) -> Dict[str, Any]:
        """Export data to JSON format - returns data for download"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        export_data = {}
        
        # Map logical table names to actual database tables
        table_mappings = {
            "jobs": "jobs",
            "logs": "log_entries", 
            "operations": "operations",
            "notification_events": "notification_events",
            "notification_configs": "notification_configs"
        }
        
        tables_to_export = table_filter if table_filter else list(table_mappings.keys())
        
        for logical_table in tables_to_export:
            actual_table = table_mappings.get(logical_table, logical_table)
            try:
                cursor.execute(f"SELECT * FROM {actual_table}")
                rows = cursor.fetchall()
                export_data[logical_table] = [dict(row) for row in rows]
            except sqlite3.OperationalError:
                # Table doesn't exist
                export_data[logical_table] = []
        
        conn.close()
        
        # Convert to JSON string
        json_content = json.dumps(export_data, indent=2, default=str)
        filename = f"dashboard_export_{timestamp}.json"
        
        return {
            "success": True,
            "filename": filename,
            "content": json_content,
            "content_type": "application/json",
            "size_bytes": len(json_content.encode('utf-8')),
            "format": "json",
            "tables_exported": len([t for t in tables_to_export if export_data.get(t)])
        }
    
    def _export_csv_data(self, timestamp: str, table_filter: List[str]) -> Dict[str, Any]:
        """Export data to CSV format - returns data for download"""
        import csv
        import io
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Map logical table names to actual database tables
        table_mappings = {
            "jobs": "jobs",
            "logs": "log_entries", 
            "operations": "operations",
            "notification_events": "notification_events",
            "notification_configs": "notification_configs"
        }
        
        tables_to_export = table_filter if table_filter else list(table_mappings.keys())
        csv_content = io.StringIO()
        
        tables_exported = 0
        for logical_table in tables_to_export:
            actual_table = table_mappings.get(logical_table, logical_table)
            try:
                cursor.execute(f"SELECT * FROM {actual_table}")
                rows = cursor.fetchall()
                
                if rows:
                    # Add table header
                    csv_content.write(f"\n# Table: {logical_table}\n")
                    
                    # Write CSV data
                    writer = csv.DictWriter(csv_content, fieldnames=rows[0].keys())
                    writer.writeheader()
                    for row in rows:
                        writer.writerow(dict(row))
                    
                    tables_exported += 1
                    
            except sqlite3.OperationalError as e:
                # Table doesn't exist
                csv_content.write(f"\n# Table: {logical_table} - Error: {e}\n")
        
        conn.close()
        
        csv_string = csv_content.getvalue()
        filename = f"dashboard_export_{timestamp}.csv"
        
        return {
            "success": True,
            "filename": filename,
            "content": csv_string,
            "content_type": "text/csv",
            "size_bytes": len(csv_string.encode('utf-8')),
            "format": "csv",
            "tables_exported": tables_exported
        }
    
    def get_backup_list(self) -> List[Dict[str, Any]]:
        """Get list of available backups"""
        try:
            if not self.backup_dir.exists():
                return []
            
            backups = []
            for backup_file in self.backup_dir.glob("dashboard_backup_*.db*"):
                try:
                    stat = backup_file.stat()
                    size_bytes = stat.st_size
                    
                    # Extract backup type from filename
                    backup_type = "manual"  # default
                    if "_auto_" in backup_file.name:
                        backup_type = "auto"
                    elif "_manual_" in backup_file.name:
                        backup_type = "manual"
                    
                    backups.append({
                        "filename": backup_file.name,
                        "path": str(backup_file),
                        "size": size_bytes,  # Keep size in bytes for frontend formatting
                        "size_mb": round(size_bytes / (1024 * 1024), 2) if size_bytes > 0 else 0,
                        "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                        "compressed": backup_file.suffix == ".gz",
                        "type": backup_type
                    })
                except Exception as e:
                    logger.warning(f"Failed to get stats for backup {backup_file}: {e}")
            
            # Sort by creation time, newest first
            backups.sort(key=lambda x: x["created_at"], reverse=True)
            return backups
            
        except Exception as e:
            logger.error(f"Failed to get backup list: {e}")
            return []
    
    def delete_backup(self, filename: str) -> Dict[str, Any]:
        """Delete a specific backup file"""
        try:
            backup_path = self.backup_dir / filename
            
            # Security check - ensure the file is in the backup directory and is a backup file
            if not backup_path.exists():
                return {"success": False, "error": "Backup file not found"}
            
            if not backup_path.name.startswith("dashboard_backup_"):
                return {"success": False, "error": "Invalid backup file"}
            
            # Get file info before deletion for logging
            file_size = backup_path.stat().st_size
            size_mb = round(file_size / (1024 * 1024), 2)
            
            # Delete the file
            backup_path.unlink()
            
            # Log system activity
            self._log_to_system("INFO", f"Backup deleted: {filename} ({size_mb} MB)")
            
            return {
                "success": True,
                "message": f"Backup {filename} deleted successfully"
            }
            
        except Exception as e:
            logger.error(f"Failed to delete backup {filename}: {e}")
            self._log_to_system("ERROR", f"Failed to delete backup {filename}: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def delete_all_backups(self) -> Dict[str, Any]:
        """Delete all backup files"""
        try:
            if not self.backup_dir.exists():
                return {"success": True, "message": "No backups to delete", "deleted_count": 0}
            
            backup_files = list(self.backup_dir.glob("dashboard_backup_*.db*"))
            deleted_count = 0
            total_size = 0
            errors = []
            
            for backup_file in backup_files:
                try:
                    file_size = backup_file.stat().st_size
                    total_size += file_size
                    backup_file.unlink()
                    deleted_count += 1
                except Exception as e:
                    errors.append(f"Failed to delete {backup_file.name}: {str(e)}")
            
            # Log system activity
            size_mb = round(total_size / (1024 * 1024), 2)
            if deleted_count > 0:
                self._log_to_system("INFO", f"All backups deleted: {deleted_count} files ({size_mb} MB)")
            
            return {
                "success": True,
                "message": f"Deleted {deleted_count} backup files",
                "deleted_count": deleted_count,
                "total_size_mb": size_mb,
                "errors": errors
            }
            
        except Exception as e:
            logger.error(f"Failed to delete all backups: {e}")
            self._log_to_system("ERROR", f"Failed to delete all backups: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            }
    
    def restore_backup(self, filename: str) -> Dict[str, Any]:
        """Restore database from a backup file with safety backup creation"""
        try:
            backup_path = self.backup_dir / filename
            
            # Security check - ensure the file exists and is a backup file
            if not backup_path.exists():
                return {"success": False, "error": "Backup file not found"}
            
            if not backup_path.name.startswith("dashboard_backup_"):
                return {"success": False, "error": "Invalid backup file"}
            
            # Check if current database exists
            if not os.path.exists(self.db_path):
                return {"success": False, "error": "Current database not found"}
            
            # Step 1: Create a safety backup of current database
            self._log_to_system("INFO", f"Creating safety backup before restore from {filename}")
            safety_backup_result = self.create_backup(backup_type="safety")
            
            if not safety_backup_result["success"]:
                return {
                    "success": False, 
                    "error": f"Failed to create safety backup: {safety_backup_result['error']}"
                }
            
            # Step 2: Restore from the selected backup
            try:
                # Check if the backup is compressed
                is_compressed = backup_path.suffix == ".gz"
                
                # Create temporary file for restoration
                temp_restore_path = f"{self.db_path}.restore_temp"
                
                if is_compressed:
                    # Decompress the backup
                    import gzip
                    with gzip.open(backup_path, 'rb') as f_in:
                        with open(temp_restore_path, 'wb') as f_out:
                            shutil.copyfileobj(f_in, f_out)
                else:
                    # Copy uncompressed backup
                    shutil.copy2(backup_path, temp_restore_path)
                
                # Verify the restored database is valid SQLite
                try:
                    test_conn = sqlite3.connect(temp_restore_path)
                    test_conn.execute("SELECT COUNT(*) FROM sqlite_master")
                    test_conn.close()
                except sqlite3.Error as e:
                    os.remove(temp_restore_path)
                    return {"success": False, "error": f"Restored backup is not a valid SQLite database: {e}"}
                
                # Replace current database with restored one
                if os.path.exists(self.db_path):
                    os.remove(self.db_path)
                os.rename(temp_restore_path, self.db_path)
                
                # Get backup info for logging
                backup_size = backup_path.stat().st_size
                backup_size_mb = round(backup_size / (1024 * 1024), 2)
                
                # Log successful restoration
                self._log_to_system("INFO", f"Database restored from {filename} ({backup_size_mb} MB)")
                
                return {
                    "success": True,
                    "message": f"Database successfully restored from {filename}",
                    "safety_backup": safety_backup_result["backup_path"],
                    "restored_from": filename,
                    "restored_size_mb": backup_size_mb
                }
                
            except Exception as restore_error:
                # Clean up temporary file if it exists
                temp_restore_path = f"{self.db_path}.restore_temp"
                if os.path.exists(temp_restore_path):
                    os.remove(temp_restore_path)
                
                self._log_to_system("ERROR", f"Database restore failed: {str(restore_error)}")
                return {
                    "success": False,
                    "error": f"Restore operation failed: {str(restore_error)}",
                    "safety_backup": safety_backup_result["backup_path"]
                }
                
        except Exception as e:
            logger.error(f"Failed to restore backup {filename}: {e}")
            self._log_to_system("ERROR", f"Failed to restore backup {filename}: {str(e)}")
            return {
                "success": False,
                "error": str(e)
            } 