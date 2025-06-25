import asyncio
import json
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
import logging
import os
import sqlite3
from pathlib import Path
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
from config import settings

logger = logging.getLogger(__name__)

# Database configuration
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./dashboard.db")

# Create engine with appropriate configuration
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False  # Set to True for SQL debugging
    )
else:
    engine = create_engine(DATABASE_URL, echo=False)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class for models
Base = declarative_base()

# Dependency to get database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def check_column_exists(engine, table_name, column_name):
    """Check if a column exists in a table"""
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns

def check_table_exists(engine, table_name):
    """Check if a table exists"""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()

def migrate_database():
    """Perform automatic database migrations"""
    print("Checking database schema and performing migrations if needed...")
    
    # Check if jobs table exists
    if not check_table_exists(engine, 'jobs'):
        print("Creating jobs table...")
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE jobs (
                    id INTEGER PRIMARY KEY,
                    job_id VARCHAR UNIQUE,
                    job_type VARCHAR,
                    source VARCHAR,
                    status VARCHAR,
                    repository VARCHAR,
                    pr_url VARCHAR,
                    trigger_user VARCHAR,
                    trigger_event VARCHAR,
                    installation_id VARCHAR,
                    request_id VARCHAR,
                    webhook_payload JSON,
                    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    completed_at DATETIME,
                    last_updated DATETIME DEFAULT CURRENT_TIMESTAMP,
                    duration FLOAT,
                    operations_count INTEGER DEFAULT 0,
                    completed_operations INTEGER DEFAULT 0,
                    failed_operations INTEGER DEFAULT 0,
                    total_logs INTEGER DEFAULT 0,
                    error_count INTEGER DEFAULT 0,
                    warning_count INTEGER DEFAULT 0,
                    result_summary JSON,
                    error_details TEXT
                )
            """))
            conn.commit()
        print("Jobs table created successfully")
    
    # Check if operations table needs job_id column
    if check_table_exists(engine, 'operations'):
        if not check_column_exists(engine, 'operations', 'job_id'):
            print("Adding job_id column to operations table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE operations ADD COLUMN job_id VARCHAR"))
                conn.commit()
            print("Added job_id column to operations table")
        
        if not check_column_exists(engine, 'operations', 'operation_type'):
            print("Adding operation_type column to operations table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE operations ADD COLUMN operation_type VARCHAR"))
                conn.commit()
            print("Added operation_type column to operations table")
        
        if not check_column_exists(engine, 'operations', 'result_data'):
            print("Adding result_data column to operations table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE operations ADD COLUMN result_data JSON"))
                conn.commit()
            print("Added result_data column to operations table")
        
        # AI/LLM Metrics columns
        if not check_column_exists(engine, 'operations', 'model_used'):
            print("Adding model_used column to operations table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE operations ADD COLUMN model_used VARCHAR"))
                conn.commit()
            print("Added model_used column to operations table")
        
        if not check_column_exists(engine, 'operations', 'input_tokens'):
            print("Adding input_tokens column to operations table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE operations ADD COLUMN input_tokens INTEGER"))
                conn.commit()
            print("Added input_tokens column to operations table")
        
        if not check_column_exists(engine, 'operations', 'output_tokens'):
            print("Adding output_tokens column to operations table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE operations ADD COLUMN output_tokens INTEGER"))
                conn.commit()
            print("Added output_tokens column to operations table")
        
        if not check_column_exists(engine, 'operations', 'estimated_dev_hours_saved'):
            print("Adding estimated_dev_hours_saved column to operations table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE operations ADD COLUMN estimated_dev_hours_saved FLOAT"))
                conn.commit()
            print("Added estimated_dev_hours_saved column to operations table")
    
    # Check if log_entries table needs job_id and operation_id columns
    if check_table_exists(engine, 'log_entries'):
        if not check_column_exists(engine, 'log_entries', 'job_id'):
            print("Adding job_id column to log_entries table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE log_entries ADD COLUMN job_id VARCHAR"))
                conn.commit()
            print("Added job_id column to log_entries table")
        
        if not check_column_exists(engine, 'log_entries', 'operation_id'):
            print("Adding operation_id column to log_entries table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE log_entries ADD COLUMN operation_id VARCHAR"))
                conn.commit()
            print("Added operation_id column to log_entries table")
    
    # Check if repositories table needs new columns for runner health tracking
    if check_table_exists(engine, 'repositories'):
        if not check_column_exists(engine, 'repositories', 'github_token'):
            print("Adding github_token column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN github_token VARCHAR"))
                conn.commit()
            print("Added github_token column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'azure_pat'):
            print("Adding azure_pat column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN azure_pat VARCHAR"))
                conn.commit()
            print("Added azure_pat column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'runner_status'):
            print("Adding runner_status column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN runner_status VARCHAR"))
                conn.commit()
            print("Added runner_status column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'runner_last_seen'):
            print("Adding runner_last_seen column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN runner_last_seen DATETIME"))
                conn.commit()
            print("Added runner_last_seen column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'runner_error'):
            print("Adding runner_error column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN runner_error VARCHAR"))
                conn.commit()
            print("Added runner_error column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'has_pr_agent_config'):
            print("Adding has_pr_agent_config column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN has_pr_agent_config BOOLEAN DEFAULT FALSE"))
                conn.commit()
            print("Added has_pr_agent_config column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'config_last_checked'):
            print("Adding config_last_checked column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN config_last_checked DATETIME"))
                conn.commit()
            print("Added config_last_checked column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'effective_config'):
            print("Adding effective_config column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN effective_config JSON"))
                conn.commit()
            print("Added effective_config column to repositories table")
    
    print("Database migration completed successfully!")

def initialize_database():
    """Initialize database and perform any necessary migrations"""
    # Import models here to avoid circular imports
    from models import Base
    
    # Create all tables
    Base.metadata.create_all(bind=engine)
    
    # Perform migrations for existing databases
    try:
        migrate_database()
    except Exception as e:
        print(f"Warning: Migration failed: {e}")
        print("Continuing with table creation...")
    
    print("Database initialization completed!")

# Clean database.py - only SQLAlchemy setup, no deprecated in-memory database

class DatabaseManager:
    """Database manager for notification operations"""
    
    def __init__(self):
        self.SessionLocal = SessionLocal
    
    def get_notification_configs(self) -> List[Dict[str, Any]]:
        """Get all notification configurations"""
        from models import NotificationConfigDB
        
        with self.SessionLocal() as db:
            configs = db.query(NotificationConfigDB).all()
            return [
                {
                    'id': config.id,
                    'service_type': config.service_type,
                    'name': config.name,
                    'enabled': config.enabled,
                    'webhook_url': config.webhook_url,
                    'channel': config.channel,
                    'smtp_server': config.smtp_server,
                    'smtp_port': config.smtp_port,
                    'email_username': config.email_username,
                    'email_password': config.email_password,
                    'recipient_emails': config.recipient_emails or [],
                    'event_types': config.event_types or [],
                    'repository_filter': config.repository_filter or [],
                    'created_at': config.created_at.isoformat() if config.created_at else None,
                    'updated_at': config.updated_at.isoformat() if config.updated_at else None,
                    'last_test': config.last_test.isoformat() if config.last_test else None,
                    'test_status': config.test_status
                }
                for config in configs
            ]
    
    def save_notification_config(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save or update notification configuration"""
        from models import NotificationConfigDB
        
        with self.SessionLocal() as db:
            if config_data.get('id'):
                # Update existing config
                config = db.query(NotificationConfigDB).filter(
                    NotificationConfigDB.id == config_data['id']
                ).first()
                if not config:
                    raise ValueError(f"Configuration with id {config_data['id']} not found")
                
                # Update fields
                for key, value in config_data.items():
                    if key != 'id' and hasattr(config, key):
                        setattr(config, key, value)
                config.updated_at = datetime.utcnow()
            else:
                # Create new config
                config = NotificationConfigDB(**{
                    k: v for k, v in config_data.items() 
                    if k != 'id' and hasattr(NotificationConfigDB, k)
                })
            
            db.add(config)
            db.commit()
            db.refresh(config)
            
            return {
                'id': config.id,
                'service_type': config.service_type,
                'name': config.name,
                'enabled': config.enabled,
                'webhook_url': config.webhook_url,
                'channel': config.channel,
                'smtp_server': config.smtp_server,
                'smtp_port': config.smtp_port,
                'email_username': config.email_username,
                'email_password': config.email_password,
                'recipient_emails': config.recipient_emails or [],
                'event_types': config.event_types or [],
                'repository_filter': config.repository_filter or [],
                'created_at': config.created_at.isoformat() if config.created_at else None,
                'updated_at': config.updated_at.isoformat() if config.updated_at else None,
                'last_test': config.last_test.isoformat() if config.last_test else None,
                'test_status': config.test_status
            }
    
    def delete_notification_config(self, config_id: int) -> bool:
        """Delete notification configuration"""
        from models import NotificationConfigDB
        
        with self.SessionLocal() as db:
            config = db.query(NotificationConfigDB).filter(
                NotificationConfigDB.id == config_id
            ).first()
            if config:
                db.delete(config)
                db.commit()
                return True
            return False
    
    def save_notification_event(self, event_data: Dict[str, Any]) -> Dict[str, Any]:
        """Save notification event"""
        from models import NotificationEventDB
        
        with self.SessionLocal() as db:
            event = NotificationEventDB(
                event_type=event_data['event_type'],
                event_data=event_data['event_data'],
                repositories=event_data.get('repositories', []),
                timestamp=datetime.fromisoformat(event_data['timestamp'].replace('Z', '+00:00')) if isinstance(event_data.get('timestamp'), str) else datetime.utcnow()
            )
            
            db.add(event)
            db.commit()
            db.refresh(event)
            
            return {
                'id': event.id,
                'event_type': event.event_type,
                'event_data': event.event_data,
                'repositories': event.repositories or [],
                'timestamp': event.timestamp.isoformat(),
                'processed': event.processed
            }
    
    def get_notification_events(
        self, 
        limit: int = 100, 
        offset: int = 0,
        event_type: str = None,
        repository: str = None
    ) -> List[Dict[str, Any]]:
        """Get notification events with pagination and filtering"""
        from models import NotificationEventDB
        
        with self.SessionLocal() as db:
            query = db.query(NotificationEventDB)
            
            if event_type:
                query = query.filter(NotificationEventDB.event_type == event_type)
            
            if repository:
                # Filter by repository (repositories is a JSON array)
                query = query.filter(
                    NotificationEventDB.repositories.contains(f'"{repository}"')
                )
            
            events = query.order_by(NotificationEventDB.timestamp.desc())\
                         .offset(offset)\
                         .limit(limit)\
                         .all()
            
            return [
                {
                    'id': event.id,
                    'event_type': event.event_type,
                    'event_data': event.event_data,
                    'repositories': event.repositories or [],
                    'sent_to_services': event.sent_to_services or [],
                    'delivery_status': event.delivery_status or {},
                    'timestamp': event.timestamp.isoformat(),
                    'processed': event.processed
                }
                for event in events
            ]

    def get_notification_events_count(
        self, 
        event_type: str = None,
        repository: str = None
    ) -> int:
        """Get total count of notification events with filtering"""
        from models import NotificationEventDB
        
        with self.SessionLocal() as db:
            query = db.query(NotificationEventDB)
            
            if event_type:
                query = query.filter(NotificationEventDB.event_type == event_type)
            
            if repository:
                # Filter by repository (repositories is a JSON array)
                query = query.filter(
                    NotificationEventDB.repositories.contains(f'"{repository}"')
                )
            
            return query.count()
    
    def update_notification_event(self, event_id: int, update_data: Dict[str, Any]) -> bool:
        """Update notification event with processing results"""
        from models import NotificationEventDB
        
        with self.SessionLocal() as db:
            event = db.query(NotificationEventDB).filter(
                NotificationEventDB.id == event_id
            ).first()
            if event:
                for key, value in update_data.items():
                    if hasattr(event, key):
                        setattr(event, key, value)
                db.commit()
                return True
            return False

    def update_notification_test_status(self, config_id: int, status: str) -> bool:
        """Update test status for notification configuration"""
        from models import NotificationConfigDB
        
        with self.SessionLocal() as db:
            config = db.query(NotificationConfigDB).filter(
                NotificationConfigDB.id == config_id
            ).first()
            if config:
                config.last_test = datetime.utcnow()
                config.test_status = status
                db.commit()
                return True
            return False
    
    def get_system_setting(self, key: str) -> Optional[str]:
        """Get a system setting value"""
        try:
            with self.SessionLocal() as db:
                result = db.execute(
                    text("SELECT value FROM system_settings WHERE key = :key"),
                    {"key": key}
                ).fetchone()
                return result[0] if result else None
        except Exception as e:
            logger.error(f"Failed to get system setting {key}: {e}")
            return None
    
    def set_system_setting(self, key: str, value: str) -> bool:
        """Set a system setting value"""
        try:
            with self.SessionLocal() as db:
                # Create system_settings table if it doesn't exist
                db.execute(text("""
                    CREATE TABLE IF NOT EXISTS system_settings (
                        key TEXT PRIMARY KEY,
                        value TEXT,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    )
                """))
                
                # Insert or update the setting
                db.execute(text("""
                    INSERT OR REPLACE INTO system_settings (key, value, updated_at)
                    VALUES (:key, :value, CURRENT_TIMESTAMP)
                """), {"key": key, "value": value})
                
                db.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to set system setting {key}: {e}")
            return False

# Initialize the database manager instance
database_manager = DatabaseManager() 