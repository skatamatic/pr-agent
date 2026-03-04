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

# Database configuration - prefer DATABASE_URL or DASHBOARD_DATABASE_URL (Cloud SQL, etc.)
DATABASE_URL = os.getenv("DATABASE_URL") or os.getenv("DASHBOARD_DATABASE_URL") or settings.database_url

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
    except Exception as e:
        # Only rollback if there's an active transaction
        try:
            if db.in_transaction():
                db.rollback()
        except Exception as rollback_error:
            # Log rollback error but don't raise it
            print(f"Warning: Rollback failed: {rollback_error}")
        raise e
    finally:
        # Safely close the session
        try:
            db.close()
        except Exception as close_error:
            # Log close error but don't raise it
            print(f"Warning: Session close failed: {close_error}")

def check_column_exists(engine, table_name, column_name):
    """Check if a column exists in a table"""
    inspector = inspect(engine)
    columns = [col['name'] for col in inspector.get_columns(table_name)]
    return column_name in columns

def check_table_exists(engine, table_name):
    """Check if a table exists"""
    inspector = inspect(engine)
    return table_name in inspector.get_table_names()

def _datetime_type():
    """Return dialect-appropriate datetime column type (SQLite vs PostgreSQL/Cloud SQL)."""
    dialect = getattr(engine.dialect, "name", "sqlite")
    return "TIMESTAMP" if dialect == "postgresql" else "DATETIME"


def migrate_database():
    """Perform automatic database migrations (SQLite and PostgreSQL/Cloud SQL compatible)."""
    print("Checking database schema and performing migrations if needed...")
    _dt = _datetime_type()
    
    # Check if jobs table exists
    if not check_table_exists(engine, 'jobs'):
        print("Creating jobs table...")
        with engine.connect() as conn:
            conn.execute(text(f"""
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
                    started_at {_dt} DEFAULT CURRENT_TIMESTAMP,
                    completed_at {_dt},
                    last_updated {_dt} DEFAULT CURRENT_TIMESTAMP,
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
        
        # NEW: Multi-model AI/LLM Metrics columns
        if not check_column_exists(engine, 'operations', 'current_step'):
            print("Adding current_step column to operations table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE operations ADD COLUMN current_step VARCHAR"))
                conn.commit()
            print("Added current_step column to operations table")
        
        if not check_column_exists(engine, 'operations', 'ai_models_used'):
            print("Adding ai_models_used column to operations table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE operations ADD COLUMN ai_models_used JSON"))
                conn.commit()
            print("Added ai_models_used column to operations table")
        
        if not check_column_exists(engine, 'operations', 'total_input_tokens'):
            print("Adding total_input_tokens column to operations table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE operations ADD COLUMN total_input_tokens INTEGER"))
                conn.commit()
            print("Added total_input_tokens column to operations table")
        
        if not check_column_exists(engine, 'operations', 'total_output_tokens'):
            print("Adding total_output_tokens column to operations table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE operations ADD COLUMN total_output_tokens INTEGER"))
                conn.commit()
            print("Added total_output_tokens column to operations table")
        
        # CRITICAL: AI Insights column for analytics data
        if not check_column_exists(engine, 'operations', 'insights'):
            print("Adding insights column to operations table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE operations ADD COLUMN insights JSON"))
                conn.commit()
            print("Added insights column to operations table")
    
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
    
    if not check_table_exists(engine, 'action_runner_connections'):
        print("Creating action_runner_connections table...")
        with engine.connect() as conn:
            conn.execute(text(f"""
                CREATE TABLE action_runner_connections (
                    id INTEGER PRIMARY KEY,
                    provider VARCHAR NOT NULL,
                    organization VARCHAR NOT NULL,
                    project VARCHAR,
                    display_name VARCHAR,
                    created_at {_dt} DEFAULT CURRENT_TIMESTAMP,
                    updated_at {_dt} DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
        print("Created action_runner_connections table")

    if check_table_exists(engine, 'action_runner_connections'):
        if not check_column_exists(engine, 'action_runner_connections', 'gcp_instance_name'):
            print("Adding gcp_instance_name column to action_runner_connections table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE action_runner_connections ADD COLUMN gcp_instance_name VARCHAR"))
                conn.commit()
            print("Added gcp_instance_name column to action_runner_connections table")
        if not check_column_exists(engine, 'action_runner_connections', 'gcp_zone'):
            print("Adding gcp_zone column to action_runner_connections table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE action_runner_connections ADD COLUMN gcp_zone VARCHAR"))
                conn.commit()
            print("Added gcp_zone column to action_runner_connections table")
    
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
                conn.execute(text(f"ALTER TABLE repositories ADD COLUMN runner_last_seen {_dt}"))
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
                conn.execute(text(f"ALTER TABLE repositories ADD COLUMN config_last_checked {_dt}"))
                conn.commit()
            print("Added config_last_checked column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'effective_config'):
            print("Adding effective_config column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN effective_config JSON"))
                conn.commit()
            print("Added effective_config column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'has_workflow_config'):
            print("Adding has_workflow_config column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN has_workflow_config BOOLEAN DEFAULT FALSE"))
                conn.commit()
            print("Added has_workflow_config column to repositories table")
        
        # Azure Pipeline config tracking columns
        if not check_column_exists(engine, 'repositories', 'azure_pipeline_config_pr_url'):
            print("Adding azure_pipeline_config_pr_url column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN azure_pipeline_config_pr_url VARCHAR"))
                conn.commit()
            print("Added azure_pipeline_config_pr_url column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'azure_pipeline_config_pr_number'):
            print("Adding azure_pipeline_config_pr_number column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN azure_pipeline_config_pr_number INTEGER"))
                conn.commit()
            print("Added azure_pipeline_config_pr_number column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'azure_pipeline_config_pr_branch'):
            print("Adding azure_pipeline_config_pr_branch column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN azure_pipeline_config_pr_branch VARCHAR"))
                conn.commit()
            print("Added azure_pipeline_config_pr_branch column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'azure_pipeline_config_pr_status'):
            print("Adding azure_pipeline_config_pr_status column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN azure_pipeline_config_pr_status VARCHAR"))
                conn.commit()
            print("Added azure_pipeline_config_pr_status column to repositories table")
        
        # Runner service monitoring columns
        if not check_column_exists(engine, 'repositories', 'runner_service_name'):
            print("Adding runner_service_name column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN runner_service_name VARCHAR"))
                conn.commit()
            print("Added runner_service_name column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'runner_service_last_checked'):
            print("Adding runner_service_last_checked column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE repositories ADD COLUMN runner_service_last_checked {_dt}"))
                conn.commit()
            print("Added runner_service_last_checked column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'runner_service_details'):
            print("Adding runner_service_details column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN runner_service_details JSON"))
                conn.commit()
            print("Added runner_service_details column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'runner_service_status'):
            print("Adding runner_service_status column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN runner_service_status VARCHAR"))
                conn.commit()
            print("Added runner_service_status column to repositories table")
        
        # Azure agent service monitoring columns
        if not check_column_exists(engine, 'repositories', 'azure_agent_service_name'):
            print("Adding azure_agent_service_name column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN azure_agent_service_name VARCHAR"))
                conn.commit()
            print("Added azure_agent_service_name column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'azure_agent_service_status'):
            print("Adding azure_agent_service_status column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN azure_agent_service_status VARCHAR"))
                conn.commit()
            print("Added azure_agent_service_status column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'azure_agent_service_last_checked'):
            print("Adding azure_agent_service_last_checked column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE repositories ADD COLUMN azure_agent_service_last_checked {_dt}"))
                conn.commit()
            print("Added azure_agent_service_last_checked column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'azure_agent_service_details'):
            print("Adding azure_agent_service_details column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN azure_agent_service_details JSON"))
                conn.commit()
            print("Added azure_agent_service_details column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'azure_agent_status'):
            print("Adding azure_agent_status column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN azure_agent_status VARCHAR"))
                conn.commit()
            print("Added azure_agent_status column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'azure_agent_error'):
            print("Adding azure_agent_error column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN azure_agent_error VARCHAR"))
                conn.commit()
            print("Added azure_agent_error column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'action_runner_connection_id'):
            print("Adding action_runner_connection_id column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN action_runner_connection_id INTEGER"))
                conn.commit()
            print("Added action_runner_connection_id column to repositories table")
        
        # Best practices tracking columns
        if not check_column_exists(engine, 'repositories', 'has_best_practices'):
            print("Adding has_best_practices column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN has_best_practices BOOLEAN DEFAULT FALSE"))
                conn.commit()
            print("Added has_best_practices column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'best_practices_content'):
            print("Adding best_practices_content column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN best_practices_content TEXT"))
                conn.commit()
            print("Added best_practices_content column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'best_practices_last_fetched'):
            print("Adding best_practices_last_fetched column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE repositories ADD COLUMN best_practices_last_fetched {_dt}"))
                conn.commit()
            print("Added best_practices_last_fetched column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'best_practices_pr_url'):
            print("Adding best_practices_pr_url column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN best_practices_pr_url VARCHAR"))
                conn.commit()
            print("Added best_practices_pr_url column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'best_practices_pr_number'):
            print("Adding best_practices_pr_number column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN best_practices_pr_number INTEGER"))
                conn.commit()
            print("Added best_practices_pr_number column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'best_practices_pr_branch'):
            print("Adding best_practices_pr_branch column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN best_practices_pr_branch VARCHAR"))
                conn.commit()
            print("Added best_practices_pr_branch column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'best_practices_pr_status'):
            print("Adding best_practices_pr_status column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN best_practices_pr_status VARCHAR"))
                conn.commit()
            print("Added best_practices_pr_status column to repositories table")
        
        # PR-Agent config tracking columns
        if not check_column_exists(engine, 'repositories', 'pr_agent_config_content'):
            print("Adding pr_agent_config_content column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN pr_agent_config_content TEXT"))
                conn.commit()
            print("Added pr_agent_config_content column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'pr_agent_config_last_fetched'):
            print("Adding pr_agent_config_last_fetched column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE repositories ADD COLUMN pr_agent_config_last_fetched {_dt}"))
                conn.commit()
            print("Added pr_agent_config_last_fetched column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'pr_agent_config_pr_url'):
            print("Adding pr_agent_config_pr_url column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN pr_agent_config_pr_url VARCHAR"))
                conn.commit()
            print("Added pr_agent_config_pr_url column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'pr_agent_config_pr_number'):
            print("Adding pr_agent_config_pr_number column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN pr_agent_config_pr_number INTEGER"))
                conn.commit()
            print("Added pr_agent_config_pr_number column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'pr_agent_config_pr_branch'):
            print("Adding pr_agent_config_pr_branch column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN pr_agent_config_pr_branch VARCHAR"))
                conn.commit()
            print("Added pr_agent_config_pr_branch column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'pr_agent_config_pr_status'):
            print("Adding pr_agent_config_pr_status column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN pr_agent_config_pr_status VARCHAR"))
                conn.commit()
            print("Added pr_agent_config_pr_status column to repositories table")
        
        # GitHub Action config tracking columns
        if not check_column_exists(engine, 'repositories', 'github_action_config_pr_url'):
            print("Adding github_action_config_pr_url column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN github_action_config_pr_url VARCHAR"))
                conn.commit()
            print("Added github_action_config_pr_url column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'github_action_config_pr_number'):
            print("Adding github_action_config_pr_number column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN github_action_config_pr_number INTEGER"))
                conn.commit()
            print("Added github_action_config_pr_number column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'github_action_config_pr_branch'):
            print("Adding github_action_config_pr_branch column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN github_action_config_pr_branch VARCHAR"))
                conn.commit()
            print("Added github_action_config_pr_branch column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'github_action_config_pr_status'):
            print("Adding github_action_config_pr_status column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN github_action_config_pr_status VARCHAR"))
                conn.commit()
            print("Added github_action_config_pr_status column to repositories table")
        
        # Monitoring settings columns
        if not check_column_exists(engine, 'repositories', 'monitor_prs'):
            print("Adding monitor_prs column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN monitor_prs BOOLEAN DEFAULT TRUE"))
                conn.commit()
            print("Added monitor_prs column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'monitor_issues'):
            print("Adding monitor_issues column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN monitor_issues BOOLEAN DEFAULT FALSE"))
                conn.commit()
            print("Added monitor_issues column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'auto_review'):
            print("Adding auto_review column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN auto_review BOOLEAN DEFAULT TRUE"))
                conn.commit()
            print("Added auto_review column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'auto_describe'):
            print("Adding auto_describe column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN auto_describe BOOLEAN DEFAULT TRUE"))
                conn.commit()
            print("Added auto_describe column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'auto_improve'):
            print("Adding auto_improve column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN auto_improve BOOLEAN DEFAULT FALSE"))
                conn.commit()
            print("Added auto_improve column to repositories table")
        
        # Metadata columns
        if not check_column_exists(engine, 'repositories', 'last_activity'):
            print("Adding last_activity column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE repositories ADD COLUMN last_activity {_dt}"))
                conn.commit()
            print("Added last_activity column to repositories table")
        
        if not check_column_exists(engine, 'repositories', 'description'):
            print("Adding description column to repositories table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE repositories ADD COLUMN description TEXT"))
                conn.commit()
            print("Added description column to repositories table")
    
    # Check and fix metrics_aggregate table
    if check_table_exists(engine, 'metrics_aggregate'):
        print("Checking metrics_aggregate table for proper defaults...")
        with engine.connect() as conn:
            # Check if there are any rows with NULL values and fix them
            result = conn.execute(text("""
                SELECT COUNT(*) as count FROM metrics_aggregate 
                WHERE total_jobs IS NULL 
                   OR total_operations IS NULL 
                   OR total_input_tokens IS NULL 
                   OR total_output_tokens IS NULL 
                   OR total_estimated_dev_hours IS NULL
            """))
            null_count = result.scalar()
            
            if null_count > 0:
                print(f"Found {null_count} rows with NULL values, fixing...")
                conn.execute(text("""
                    UPDATE metrics_aggregate 
                    SET total_jobs = COALESCE(total_jobs, 0),
                        total_operations = COALESCE(total_operations, 0),
                        total_input_tokens = COALESCE(total_input_tokens, 0),
                        total_output_tokens = COALESCE(total_output_tokens, 0),
                        total_estimated_dev_hours = COALESCE(total_estimated_dev_hours, 0.0),
                        model_usage = COALESCE(model_usage, '{}')
                    WHERE total_jobs IS NULL 
                       OR total_operations IS NULL 
                       OR total_input_tokens IS NULL 
                       OR total_output_tokens IS NULL 
                       OR total_estimated_dev_hours IS NULL
                       OR model_usage IS NULL
                """))
                conn.commit()
                print("Fixed NULL values in metrics_aggregate table")
    else:
        print("Creating metrics_aggregate table with proper defaults...")
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE metrics_aggregate (
                    id INTEGER PRIMARY KEY,
                    total_jobs INTEGER DEFAULT 0,
                    total_operations INTEGER DEFAULT 0,
                    total_input_tokens INTEGER DEFAULT 0,
                    total_output_tokens INTEGER DEFAULT 0,
                    total_estimated_dev_hours FLOAT DEFAULT 0.0,
                    model_usage JSON DEFAULT '{}',
                    last_updated {_dt} DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
        print("Created metrics_aggregate table with proper defaults")
    
    # Similarly check metrics_config table
    if not check_table_exists(engine, 'metrics_config'):
        print("Creating metrics_config table...")
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE metrics_config (
                    id INTEGER PRIMARY KEY,
                    model_costs JSON DEFAULT '{}',
                    developer_hourly_rate FLOAT DEFAULT 75.0,
                    hours_multiplier FLOAT DEFAULT 1.0,
                    created_at {_dt} DEFAULT CURRENT_TIMESTAMP,
                    updated_at {_dt} DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
        print("Created metrics_config table")
    
    # Check for additional tables that might be missing
    if not check_table_exists(engine, 'health_cache'):
        print("Creating health_cache table...")
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE health_cache (
                    id INTEGER PRIMARY KEY,
                    service_name VARCHAR UNIQUE,
                    status VARCHAR,
                    message TEXT,
                    details JSON,
                    last_checked {_dt} DEFAULT CURRENT_TIMESTAMP,
                    updated_at {_dt} DEFAULT CURRENT_TIMESTAMP
                )
            """))
            conn.commit()
        print("Created health_cache table")
    
    if not check_table_exists(engine, 'users'):
        print("Creating users table...")
        with engine.connect() as conn:
            conn.execute(text(f"""
                CREATE TABLE users (
                    id INTEGER PRIMARY KEY,
                    username VARCHAR UNIQUE NOT NULL,
                    email VARCHAR UNIQUE,
                    password_hash VARCHAR NOT NULL,
                    is_active BOOLEAN DEFAULT TRUE,
                    is_admin BOOLEAN DEFAULT FALSE,
                    created_at {_dt} DEFAULT CURRENT_TIMESTAMP,
                    updated_at {_dt} DEFAULT CURRENT_TIMESTAMP,
                    last_login {_dt}
                )
            """))
            conn.commit()
        print("Created users table")
    else:
        # Check for missing columns in existing users table
        if not check_column_exists(engine, 'users', 'email'):
            print("Adding email column to users table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR"))
                conn.commit()
            print("Added email column to users table")
        
        if not check_column_exists(engine, 'users', 'is_admin'):
            print("Adding is_admin column to users table...")
            with engine.connect() as conn:
                conn.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE"))
                conn.commit()
            print("Added is_admin column to users table")
        
        if not check_column_exists(engine, 'users', 'updated_at'):
            print("Adding updated_at column to users table...")
            with engine.connect() as conn:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN updated_at {_dt}"))
                conn.commit()
            print("Added updated_at column to users table")
    
    if not check_table_exists(engine, 'notification_configs'):
        print("Creating notification_configs table...")
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE notification_configs (
                    id INTEGER PRIMARY KEY,
                    service_type VARCHAR NOT NULL,
                    name VARCHAR NOT NULL,
                    enabled BOOLEAN DEFAULT TRUE,
                    webhook_url VARCHAR,
                    channel VARCHAR,
                    smtp_server VARCHAR,
                    smtp_port INTEGER,
                    email_username VARCHAR,
                    email_password VARCHAR,
                    recipient_emails JSON,
                    event_types JSON,
                    repository_filter JSON,
                    created_at {_dt} DEFAULT CURRENT_TIMESTAMP,
                    updated_at {_dt} DEFAULT CURRENT_TIMESTAMP,
                    last_test {_dt},
                    test_status VARCHAR
                )
            """))
            conn.commit()
        print("Created notification_configs table")
    
    if not check_table_exists(engine, 'notification_events'):
        print("Creating notification_events table...")
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE notification_events (
                    id INTEGER PRIMARY KEY,
                    event_type VARCHAR NOT NULL,
                    message TEXT NOT NULL,
                    context JSON,
                    repository VARCHAR,
                    job_id VARCHAR,
                    operation_id VARCHAR,
                    created_at {_dt} DEFAULT CURRENT_TIMESTAMP,
                    sent_at {_dt},
                    status VARCHAR DEFAULT 'pending',
                    error_message TEXT,
                    config_id INTEGER,
                    retry_count INTEGER DEFAULT 0
                )
            """))
            conn.commit()
        print("Created notification_events table")
    else:
        # Check for missing columns in existing notification_events table
        missing_event_columns = [
            ('message', 'TEXT'),
            ('context', 'JSON'),
            ('repository', 'VARCHAR'),
            ('job_id', 'VARCHAR'),
            ('operation_id', 'VARCHAR'),
            ('created_at', _dt),
            ('sent_at', _dt),
            ('status', 'VARCHAR'),
            ('error_message', 'TEXT'),
            ('config_id', 'INTEGER'),
            ('retry_count', 'INTEGER')
        ]
        
        for column_name, column_def in missing_event_columns:
            if not check_column_exists(engine, 'notification_events', column_name):
                print(f"Adding {column_name} column to notification_events table...")
                with engine.connect() as conn:
                    conn.execute(text(f"ALTER TABLE notification_events ADD COLUMN {column_name} {column_def}"))
                    conn.commit()
                print(f"Added {column_name} column to notification_events table")
    
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
        """Set a system setting value (SQLite and PostgreSQL compatible)"""
        try:
            dialect_name = engine.dialect.name if hasattr(engine, 'dialect') else 'sqlite'
            with self.SessionLocal() as db:
                # Create system_settings table if it doesn't exist
                if dialect_name == 'sqlite':
                    db.execute(text("""
                        CREATE TABLE IF NOT EXISTS system_settings (
                            key TEXT PRIMARY KEY,
                            value TEXT,
                            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                        )
                    """))
                    db.execute(text("""
                        INSERT OR REPLACE INTO system_settings (key, value, updated_at)
                        VALUES (:key, :value, CURRENT_TIMESTAMP)
                    """), {"key": key, "value": value})
                else:
                    # PostgreSQL and other dialects
                    db.execute(text("""
                        CREATE TABLE IF NOT EXISTS system_settings (
                            key VARCHAR PRIMARY KEY,
                            value TEXT,
                            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """))
                    db.execute(text("""
                        INSERT INTO system_settings (key, value, updated_at)
                        VALUES (:key, :value, CURRENT_TIMESTAMP)
                        ON CONFLICT (key) DO UPDATE SET value = :value, updated_at = CURRENT_TIMESTAMP
                    """), {"key": key, "value": value})
                db.commit()
                return True
        except Exception as e:
            logger.error(f"Failed to set system setting {key}: {e}")
            return False

# Initialize the database manager instance
database_manager = DatabaseManager() 