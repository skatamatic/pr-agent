from sqlalchemy import Column, String, DateTime, Text, JSON, Integer, Float, Boolean, ForeignKey
from sqlalchemy.orm import relationship
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from database import Base, engine, get_db

# Database Models
class JobDB(Base):
    __tablename__ = "jobs"
    
    id = Column(Integer, primary_key=True, index=True)
    job_id = Column(String, unique=True, index=True)
    job_type = Column(String)  # "webhook", "cli", "manual", "api"
    source = Column(String, nullable=True)  # "github", "azure", "cli", etc.
    status = Column(String)  # "running", "completed", "failed"
    
    # Job metadata
    repository = Column(String, nullable=True)
    pr_url = Column(String, nullable=True)
    trigger_user = Column(String, nullable=True)
    trigger_event = Column(String, nullable=True)  # "pull_request", "manual", etc.
    
    # Context information
    installation_id = Column(String, nullable=True)
    request_id = Column(String, nullable=True)
    webhook_payload = Column(JSON, nullable=True)
    
    # Timing
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    duration = Column(Float, nullable=True)  # in seconds
    
    # Summary metrics
    operations_count = Column(Integer, default=0)
    completed_operations = Column(Integer, default=0)
    failed_operations = Column(Integer, default=0)
    total_logs = Column(Integer, default=0)
    error_count = Column(Integer, default=0)
    warning_count = Column(Integer, default=0)
    
    # Results summary
    result_summary = Column(JSON, nullable=True)
    error_details = Column(Text, nullable=True)

class OperationDB(Base):
    __tablename__ = "operations"
    
    id = Column(Integer, primary_key=True, index=True)
    operation_id = Column(String, unique=True, index=True)
    job_id = Column(String, ForeignKey('jobs.job_id'), nullable=True, index=True)  # Nullable for backward compatibility
    
    # Operation details
    operation_type = Column(String)  # "fetching_context", "generating_review", "self_reflecting", etc.
    command = Column(String, nullable=True)
    status = Column(String)
    
    # Context
    repo = Column(String, nullable=True)
    pr_url = Column(String, nullable=True)
    installation_id = Column(String, nullable=True)
    sender = Column(String, nullable=True)
    request_id = Column(String, nullable=True)
    
    # Timing
    started_at = Column(DateTime, default=datetime.utcnow)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)
    duration = Column(Float, nullable=True)
    error_details = Column(Text, nullable=True)
    
    # Performance metrics
    response_time = Column(Float, nullable=True)
    context_fetch_time = Column(Float, nullable=True)
    ai_processing_time = Column(Float, nullable=True)
    
    # Results
    suggestions_count = Column(Integer, nullable=True)
    errors_count = Column(Integer, nullable=True)
    warnings_count = Column(Integer, nullable=True)
    result_data = Column(JSON, nullable=True)

    # Relationship
    job = relationship("JobDB", backref="operations")

class RepositoryDB(Base):
    __tablename__ = "repositories"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)  # e.g., "owner/repo-name"
    provider = Column(String)  # "github" or "azure_devops"
    url = Column(String)
    is_active = Column(Boolean, default=True)
    
    # Provider-specific configuration
    config = Column(JSON, nullable=True)  # Store provider-specific settings
    
    # Monitoring settings
    monitor_prs = Column(Boolean, default=True)
    monitor_issues = Column(Boolean, default=False)
    auto_review = Column(Boolean, default=True)
    auto_describe = Column(Boolean, default=True)
    auto_improve = Column(Boolean, default=False)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_activity = Column(DateTime, nullable=True)

class LogEntryDB(Base):
    __tablename__ = "log_entries"
    
    id = Column(Integer, primary_key=True, index=True)
    timestamp = Column(DateTime)
    level = Column(String)
    message = Column(Text)
    module = Column(String, nullable=True)
    function = Column(String, nullable=True)
    line = Column(Integer, nullable=True)
    
    # NEW: Job and Operation tracking
    job_id = Column(String, ForeignKey('jobs.job_id'), nullable=True, index=True)
    operation_id = Column(String, ForeignKey('operations.operation_id'), nullable=True, index=True)
    
    # Context information
    pr_url = Column(String, nullable=True)
    command = Column(String, nullable=True)
    installation_id = Column(String, nullable=True)
    repo = Column(String, nullable=True)
    sender = Column(String, nullable=True)
    request_id = Column(String, nullable=True)
    sub_feature = Column(String, nullable=True)
    
    # Status information
    status = Column(String, nullable=True)
    analytics = Column(Boolean, default=False)
    
    # JSON fields for complex data
    artifact = Column(JSON, nullable=True)
    artifacts = Column(JSON, nullable=True)
    error = Column(JSON, nullable=True)
    
    # Application metadata
    app_name = Column(String, nullable=True)
    build_number = Column(String, nullable=True)
    git_provider = Column(String, nullable=True)
    received_at = Column(String, nullable=True)

    # Relationships
    job = relationship("JobDB", backref="logs")
    operation = relationship("OperationDB", backref="logs")

# Initialize database with proper schema handling
# This is called when the module is imported
try:
    from database import initialize_database
    initialize_database()
except ImportError:
    # Fallback if called before database module is fully loaded
    from database import Base, engine
    Base.metadata.create_all(bind=engine)

# Pydantic Models (API schemas)
class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

class RepositoryProvider(str, Enum):
    GITHUB = "github"
    AZURE_DEVOPS = "azure_devops"

class JobType(str, Enum):
    WEBHOOK = "webhook"
    CLI = "cli"
    MANUAL = "manual"
    API = "api"

class JobStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class OperationType(str, Enum):
    STARTING = "starting"
    FETCHING_CONTEXT = "fetching_context"
    PROCESSING_PR = "processing_pr"
    GENERATING_REVIEW = "generating_review"
    GENERATING_DESCRIPTION = "generating_description"
    GENERATING_SUGGESTIONS = "generating_suggestions"
    SELF_REFLECTING = "self_reflecting"
    PUBLISHING_RESULTS = "publishing_results"
    FINALIZING = "finalizing"
    CLEANUP = "cleanup"

class OperationStatus(str, Enum):
    STARTING = "starting"
    PROCESSING = "processing"
    FETCHING_CONTEXT = "fetching_context"
    CONTEXT_COMPLETED = "context_completed"
    CONTEXT_DISABLED = "context_disabled"
    CONTEXT_FAILED = "context_failed"
    PREPARING = "preparing"
    SELF_REFLECTING = "self_reflecting"
    PUBLISHING = "publishing"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"

class Job(BaseModel):
    id: Optional[int] = None
    job_id: str
    job_type: JobType
    source: Optional[str] = None
    status: JobStatus
    
    # Job metadata
    repository: Optional[str] = None
    pr_url: Optional[str] = None
    trigger_user: Optional[str] = None
    trigger_event: Optional[str] = None
    
    # Context information
    installation_id: Optional[str] = None
    request_id: Optional[str] = None
    webhook_payload: Optional[Dict[str, Any]] = None
    
    # Timing
    started_at: str
    completed_at: Optional[str] = None
    last_updated: str
    duration: Optional[float] = None
    
    # Summary metrics
    operations_count: int = 0
    completed_operations: int = 0
    failed_operations: int = 0
    total_logs: int = 0
    error_count: int = 0
    warning_count: int = 0
    
    # Results
    result_summary: Optional[Dict[str, Any]] = None
    error_details: Optional[str] = None
    
    # Related data (when expanded)
    operations: Optional[List['Operation']] = None

    class Config:
        from_attributes = True

class Operation(BaseModel):
    id: Optional[int] = None
    operation_id: str
    job_id: Optional[str] = None
    
    # Operation details
    operation_type: Optional[OperationType] = None
    command: Optional[str] = None
    status: OperationStatus
    
    # Context
    repo: Optional[str] = None
    pr_url: Optional[str] = None
    installation_id: Optional[str] = None
    sender: Optional[str] = None
    request_id: Optional[str] = None
    
    # Timing
    started_at: str
    last_updated: str
    completed_at: Optional[str] = None
    duration: Optional[float] = None
    error_details: Optional[str] = None
    
    # Performance metrics
    response_time: Optional[float] = None
    context_fetch_time: Optional[float] = None
    ai_processing_time: Optional[float] = None
    
    # Results
    suggestions_count: Optional[int] = None
    errors_count: Optional[int] = None
    warnings_count: Optional[int] = None
    result_data: Optional[Dict[str, Any]] = None

    class Config:
        from_attributes = True

class LogEntry(BaseModel):
    id: Optional[int] = None
    timestamp: str
    level: LogLevel
    message: str
    module: Optional[str] = None
    function: Optional[str] = None
    line: Optional[int] = None
    
    # NEW: Job and Operation tracking
    job_id: Optional[str] = None
    operation_id: Optional[str] = None
    
    # Context information
    pr_url: Optional[str] = None
    command: Optional[str] = None
    installation_id: Optional[str] = None
    repo: Optional[str] = None
    sender: Optional[str] = None
    request_id: Optional[str] = None
    sub_feature: Optional[str] = None
    
    # Status information
    status: Optional[OperationStatus] = None
    analytics: Optional[bool] = False
    
    # Artifacts for detailed debugging
    artifact: Optional[Dict[str, Any]] = None
    artifacts: Optional[List[Dict[str, Any]]] = None
    
    # Error information
    error: Optional[Dict[str, Any]] = None
    
    # Application metadata
    app_name: Optional[str] = None
    build_number: Optional[str] = None
    git_provider: Optional[str] = None
    
    # Processing metadata
    received_at: Optional[str] = None

    class Config:
        from_attributes = True

class SystemMetrics(BaseModel):
    timestamp: str
    
    # Performance metrics
    avg_response_time: Optional[str] = None
    success_rate: Optional[str] = None
    error_rate: Optional[str] = None
    
    # Operation metrics
    total_operations: Optional[int] = None
    operations_per_hour: Optional[int] = None
    completed_operations: Optional[int] = None
    failed_operations: Optional[int] = None
    
    # Context-specific metrics
    context_fetch_rate: Optional[str] = None
    context_success_rate: Optional[str] = None
    context_fetch_time: Optional[str] = None
    context_operations: Optional[int] = None
    
    # API metrics
    api_response_time: Optional[str] = None
    api_error_rate: Optional[str] = None
    
    # System health
    system_health: Optional[str] = "healthy"
    database_status: Optional[str] = "online"
    context_service_status: Optional[str] = "connected"

class MetricsTimeSeriesPoint(BaseModel):
    timestamp: str
    value: float
    metric_name: str

class DashboardConfig(BaseModel):
    refresh_interval: int = Field(default=5, description="Refresh interval in seconds")
    max_logs_display: int = Field(default=1000, description="Maximum logs to display")
    max_operations_display: int = Field(default=100, description="Maximum operations to display")
    enable_realtime: bool = Field(default=True, description="Enable real-time updates")
    log_levels: List[LogLevel] = Field(default=[LogLevel.INFO, LogLevel.WARNING, LogLevel.ERROR, LogLevel.CRITICAL])

class WebSocketMessage(BaseModel):
    type: str  # "log", "operation", "metric", "status_update"
    data: Dict[str, Any]
    timestamp: Optional[str] = None

class HealthCheck(BaseModel):
    status: str
    timestamp: str
    version: str
    uptime: Optional[float] = None

class APIResponse(BaseModel):
    data: Any
    total: Optional[int] = None
    page: Optional[int] = None
    per_page: Optional[int] = None
    timestamp: Optional[str] = None
    message: Optional[str] = None

class ConfigUpdate(BaseModel):
    config: Dict[str, Any]

class Repository(BaseModel):
    id: Optional[int] = None
    name: str = Field(..., description="Repository name in format 'owner/repo-name'")
    provider: RepositoryProvider
    url: str = Field(..., description="Repository URL")
    is_active: bool = Field(default=True, description="Whether monitoring is active")
    
    # Provider-specific configuration
    config: Optional[Dict[str, Any]] = Field(default=None, description="Provider-specific settings")
    
    # Monitoring settings
    monitor_prs: bool = Field(default=True, description="Monitor pull requests")
    monitor_issues: bool = Field(default=False, description="Monitor issues")
    auto_review: bool = Field(default=True, description="Automatically review PRs")
    auto_describe: bool = Field(default=True, description="Automatically generate PR descriptions")
    auto_improve: bool = Field(default=False, description="Automatically suggest improvements")
    
    # Metadata
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_activity: Optional[str] = None

    class Config:
        from_attributes = True

class RepositoryCreate(BaseModel):
    name: str = Field(..., description="Repository name in format 'owner/repo-name'")
    provider: RepositoryProvider
    url: str = Field(..., description="Repository URL")
    is_active: bool = Field(default=True)
    
    # Provider-specific configuration
    config: Optional[Dict[str, Any]] = None
    
    # Monitoring settings
    monitor_prs: bool = Field(default=True)
    monitor_issues: bool = Field(default=False)
    auto_review: bool = Field(default=True)
    auto_describe: bool = Field(default=True)
    auto_improve: bool = Field(default=False)

class RepositoryUpdate(BaseModel):
    name: Optional[str] = None
    provider: Optional[RepositoryProvider] = None
    url: Optional[str] = None
    is_active: Optional[bool] = None
    config: Optional[Dict[str, Any]] = None
    monitor_prs: Optional[bool] = None
    monitor_issues: Optional[bool] = None
    auto_review: Optional[bool] = None
    auto_describe: Optional[bool] = None
    auto_improve: Optional[bool] = None 