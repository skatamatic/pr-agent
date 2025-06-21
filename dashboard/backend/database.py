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