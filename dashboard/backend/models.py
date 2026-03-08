from sqlalchemy import Column, String, DateTime, Text, JSON, Integer, Float, Boolean, ForeignKey, desc, and_, or_, func
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, backref
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
    current_step = Column(String, nullable=True)  # Real-time step tracking: "Context", "Generating", "Reflecting", etc.
    
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
    
    # Legacy AI/LLM Metrics (for backward compatibility)
    model_used = Column(String, nullable=True)
    input_tokens = Column(Integer, nullable=True)
    output_tokens = Column(Integer, nullable=True)
    estimated_dev_hours_saved = Column(Float, nullable=True)
    
    # NEW: Multi-model AI/LLM Metrics 
    ai_models_used = Column(JSON, nullable=True)  # {"model_name": {"input_tokens": int, "output_tokens": int}, ...}
    total_input_tokens = Column(Integer, nullable=True)  # Aggregate across all models
    total_output_tokens = Column(Integer, nullable=True)  # Aggregate across all models
    
    # AI Insights - structured analysis data from self-reflection and dev time estimation
    insights = Column(JSON, nullable=True)  # {"dev_time_estimation": {...}, "self_reflection": {...}}
    
    # Results
    suggestions_count = Column(Integer, nullable=True)
    errors_count = Column(Integer, nullable=True)
    warnings_count = Column(Integer, nullable=True)
    result_data = Column(JSON, nullable=True)

    # Relationship
    job = relationship("JobDB", backref=backref("operations", order_by="OperationDB.started_at"))

class ActionRunnerConnectionDB(Base):
    """One per ADO org (or org+project) or GitHub org; groups repos that share one self-hosted runner."""
    __tablename__ = "action_runner_connections"
    
    id = Column(Integer, primary_key=True, index=True)
    provider = Column(String, nullable=False)  # "github" or "azure_devops"
    organization = Column(String, nullable=False)
    project = Column(String, nullable=True)  # ADO project; null for GitHub (org-level)
    display_name = Column(String, nullable=True)  # e.g. "MyOrg (ADO)" or "my-org"
    agent_pool = Column(String, nullable=True)  # ADO agent pool name (e.g. "PRAgent_Cloud")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    # GCP-provisioned runner VM (when dashboard creates the VM)
    gcp_instance_name = Column(String, nullable=True)  # GCE instance name
    gcp_zone = Column(String, nullable=True)  # e.g. us-central1-a


class RepositoryDB(Base):
    __tablename__ = "repositories"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)  # e.g., "owner/repo-name"
    provider = Column(String)  # "github" or "azure_devops"
    url = Column(String)
    is_active = Column(Boolean, default=True)
    action_runner_connection_id = Column(Integer, ForeignKey("action_runner_connections.id"), nullable=True)
    
    # Provider-specific configuration
    config = Column(JSON, nullable=True)  # Store provider-specific settings
    
    # Access tokens for health checks (encrypted/hashed in production)
    github_token = Column(String, nullable=True)  # GitHub personal access token
    azure_pat = Column(String, nullable=True)     # Azure DevOps personal access token
    
    # Runner/Agent health tracking
    runner_status = Column(String, nullable=True)  # "running", "stopped", "error", "unknown"
    runner_last_seen = Column(DateTime, nullable=True)
    runner_error = Column(String, nullable=True)
    
    # Runner service monitoring
    runner_service_name = Column(String, nullable=True)  # Windows service name
    runner_service_status = Column(String, nullable=True)  # "running", "stopped", "not_found", "error"
    runner_service_last_checked = Column(DateTime, nullable=True)
    runner_service_details = Column(JSON, nullable=True)  # Additional service details
    
    # Azure agent service monitoring
    azure_agent_service_name = Column(String, nullable=True)  # Azure agent Windows service name
    azure_agent_service_status = Column(String, nullable=True)  # "running", "stopped", "not_found", "error"
    azure_agent_service_last_checked = Column(DateTime, nullable=True)
    azure_agent_service_details = Column(JSON, nullable=True)  # Additional Azure agent service details
    azure_agent_status = Column(String, nullable=True)  # "running", "stopped", "error", "unknown"
    azure_agent_error = Column(String, nullable=True)  # Azure agent error message
    
    # Repository configuration detection
    has_pr_agent_config = Column(Boolean, default=False)  # .pr_agent.toml exists
    has_workflow_config = Column(Boolean, default=False)  # GitHub Actions workflow with PR-Agent env vars exists
    config_last_checked = Column(DateTime, nullable=True)
    effective_config = Column(JSON, nullable=True)  # Merged config with overrides
    
    # Best practices tracking
    has_best_practices = Column(Boolean, default=False)  # best_practices.md exists
    best_practices_content = Column(Text, nullable=True)  # Cached content
    best_practices_last_fetched = Column(DateTime, nullable=True)
    best_practices_pr_url = Column(String, nullable=True)  # Pending PR URL
    best_practices_pr_number = Column(Integer, nullable=True)  # Pending PR number
    best_practices_pr_branch = Column(String, nullable=True)  # Branch name for pending PR
    best_practices_pr_status = Column(String, nullable=True)  # "pending", "merged", "closed"
    
    # PR-Agent config tracking
    has_pr_agent_config = Column(Boolean, default=False)  # .pr_agent.toml exists
    pr_agent_config_content = Column(Text, nullable=True)  # Cached content
    pr_agent_config_last_fetched = Column(DateTime, nullable=True)
    pr_agent_config_pr_url = Column(String, nullable=True)  # Pending PR URL
    pr_agent_config_pr_number = Column(Integer, nullable=True)  # Pending PR number
    pr_agent_config_pr_branch = Column(String, nullable=True)  # Branch name for pending PR
    pr_agent_config_pr_status = Column(String, nullable=True)  # "pending", "merged", "closed"
    
    # GitHub Action config tracking
    github_action_config_pr_url = Column(String, nullable=True)  # Pending PR URL
    github_action_config_pr_number = Column(Integer, nullable=True)  # Pending PR number
    github_action_config_pr_branch = Column(String, nullable=True)  # Branch name for pending PR
    github_action_config_pr_status = Column(String, nullable=True)  # "pending", "merged", "closed"
    
    # Azure Pipeline config tracking
    azure_pipeline_config_pr_url = Column(String, nullable=True)  # Pending PR URL
    azure_pipeline_config_pr_number = Column(Integer, nullable=True)  # Pending PR number
    azure_pipeline_config_pr_branch = Column(String, nullable=True)  # Branch name for pending PR
    azure_pipeline_config_pr_status = Column(String, nullable=True)  # "pending", "merged", "closed"
    
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
    
    # Optional: link to shared runner connection (one runner per ADO org or GitHub org)
    action_runner_connection = relationship("ActionRunnerConnectionDB", backref="repositories", foreign_keys=[action_runner_connection_id])

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

class HealthCacheDB(Base):
    __tablename__ = "health_cache"
    
    id = Column(Integer, primary_key=True, index=True)
    service_name = Column(String, unique=True, index=True)  # "database", "context_service", etc.
    status = Column(String)  # "connected", "error", "warning", "disabled"
    message = Column(String, nullable=True)
    error_details = Column(String, nullable=True)
    endpoint = Column(String, nullable=True)
    
    # Cache metadata
    last_checked = Column(DateTime, default=datetime.utcnow)
    is_checking = Column(Boolean, default=False)
    check_count = Column(Integer, default=0)
    
    # Additional data
    details = Column(JSON, nullable=True)
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class MetricsAggregateDB(Base):
    __tablename__ = "metrics_aggregate"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Aggregate metrics (no history, just current totals)
    total_jobs = Column(Integer, default=0)
    total_operations = Column(Integer, default=0)
    total_input_tokens = Column(Integer, default=0)
    total_output_tokens = Column(Integer, default=0)
    total_estimated_dev_hours = Column(Float, default=0.0)
    
    # Model breakdown (JSON with model -> {input_tokens, output_tokens, operations_count})
    model_usage = Column(JSON, default=dict)
    
    # Timestamps
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class MetricsConfigDB(Base):
    __tablename__ = "metrics_config"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Token pricing (per 1K tokens)
    model_costs = Column(JSON, default=dict)  # {"gpt-4": {"input": 0.03, "output": 0.06}}
    
    # Developer cost calculation
    developer_hourly_rate = Column(Float, default=75.0)  # USD per hour
    hours_multiplier = Column(Float, default=1.0)  # Fudge factor for LLM estimates
    
    # Timestamps
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

class UserDB(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)

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
    SKIPPED = "skipped"

class OperationType(str, Enum):
    # PR-Agent commands/tools
    REVIEW = "review"
    DESCRIBE = "describe"
    IMPROVE = "improve"
    TEST = "test"
    ADD_DOCS = "add_docs"
    UPDATE_CHANGELOG = "update_changelog"
    SIMILAR_ISSUE = "similar_issue"
    
    # Process stages
    STARTING = "starting"
    FETCHING_CONTEXT = "fetching_context"
    PROCESSING_PR = "processing_pr"
    SELF_REFLECTING = "self_reflecting"
    PUBLISHING_RESULTS = "publishing_results"
    FINALIZING = "finalizing"
    CLEANUP = "cleanup"
    
    # Generating stages (for detailed operation tracking)
    GENERATING_REVIEW = "generating_review"
    GENERATING_DESCRIPTION = "generating_description"
    GENERATING_SUGGESTIONS = "generating_suggestions"
    GENERATING_QUESTIONS = "generating_questions"
    GENERATING_LABELS = "generating_labels"
    ESTIMATING_DEV_TIME = "estimating_dev_time"

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
    model_config = {'protected_namespaces': (), 'from_attributes': True}
    
    id: Optional[int] = None
    operation_id: str
    job_id: Optional[str] = None
    
    # Operation details
    operation_type: Optional[OperationType] = None
    command: Optional[str] = None
    status: OperationStatus
    current_step: Optional[str] = None
    
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
    
    # Legacy AI/LLM Metrics (for backward compatibility)
    model_used: Optional[str] = None
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    estimated_dev_hours_saved: Optional[float] = None
    
    # NEW: Multi-model AI/LLM Metrics 
    ai_models_used: Optional[Dict[str, Dict[str, int]]] = None
    total_input_tokens: Optional[int] = None
    total_output_tokens: Optional[int] = None
    
    # AI Insights - structured analysis data from self-reflection and dev time estimation
    insights: Optional[Dict[str, Any]] = None
    
    # Results
    suggestions_count: Optional[int] = None
    errors_count: Optional[int] = None
    warnings_count: Optional[int] = None
    result_data: Optional[Dict[str, Any]] = None

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
    max_logs_display: int = Field(default=10000, description="Maximum logs to display")
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
    action_runner_connection_id: Optional[int] = Field(default=None, description="Shared runner connection (one per ADO org or GitHub org)")

    # Provider-specific configuration
    config: Optional[Dict[str, Any]] = Field(default=None, description="Provider-specific settings")
    
    # Access tokens (never exposed in API responses)
    github_token: Optional[str] = Field(default=None, description="GitHub access token")
    azure_pat: Optional[str] = Field(default=None, description="Azure DevOps PAT")
    
    # Token status indicators (safe to expose)
    has_github_token: Optional[bool] = Field(default=None, description="Whether GitHub token is configured")
    has_azure_pat: Optional[bool] = Field(default=None, description="Whether Azure PAT is configured")
    
    # Runner/Agent health tracking
    runner_status: Optional[str] = Field(default=None, description="Runner health status")
    runner_last_seen: Optional[str] = None
    runner_error: Optional[str] = None
    
    # Runner service monitoring
    runner_service_name: Optional[str] = Field(default=None, description="Windows service name")
    runner_service_status: Optional[str] = Field(default=None, description="Windows service status")
    runner_service_last_checked: Optional[str] = None
    runner_service_details: Optional[Dict[str, Any]] = Field(default=None, description="Additional service details")
    
    # Azure agent service monitoring
    azure_agent_service_name: Optional[str] = Field(default=None, description="Azure agent Windows service name")
    azure_agent_service_status: Optional[str] = Field(default=None, description="Azure agent Windows service status")
    azure_agent_service_last_checked: Optional[str] = None
    azure_agent_service_details: Optional[Dict[str, Any]] = Field(default=None, description="Additional Azure agent service details")
    azure_agent_status: Optional[str] = Field(default=None, description="Azure agent health status")
    azure_agent_error: Optional[str] = None
    
    # Repository configuration detection
    has_pr_agent_config: bool = Field(default=False, description="Has .pr_agent.toml file")
    has_workflow_config: bool = Field(default=False, description="Has GitHub Actions workflow with PR-Agent configuration")
    config_last_checked: Optional[str] = None
    effective_config: Optional[Dict[str, Any]] = Field(default=None, description="Merged configuration")
    
    # Best practices tracking
    has_best_practices: bool = Field(default=False, description="Has best_practices.md file")
    best_practices_content: Optional[str] = Field(default=None, description="Cached best practices content")
    best_practices_last_fetched: Optional[str] = None
    best_practices_pr_url: Optional[str] = Field(default=None, description="Pending best practices PR URL")
    best_practices_pr_number: Optional[int] = Field(default=None, description="Pending best practices PR number")
    best_practices_pr_branch: Optional[str] = Field(default=None, description="Pending best practices PR branch")
    best_practices_pr_status: Optional[str] = Field(default=None, description="Pending PR status: pending, merged, closed")
    
    # PR-Agent config tracking
    pr_agent_config_content: Optional[str] = Field(default=None, description="Cached PR-Agent config content")
    pr_agent_config_last_fetched: Optional[str] = None
    pr_agent_config_pr_url: Optional[str] = Field(default=None, description="Pending PR-Agent config PR URL")
    pr_agent_config_pr_number: Optional[int] = Field(default=None, description="Pending PR-Agent config PR number")
    pr_agent_config_pr_branch: Optional[str] = Field(default=None, description="Pending PR-Agent config PR branch")
    pr_agent_config_pr_status: Optional[str] = Field(default=None, description="Pending PR status: pending, merged, closed")
    
    # GitHub Action config tracking
    github_action_config_pr_url: Optional[str] = Field(default=None, description="Pending GitHub Action config PR URL")
    github_action_config_pr_number: Optional[int] = Field(default=None, description="Pending GitHub Action config PR number")
    github_action_config_pr_branch: Optional[str] = Field(default=None, description="Pending GitHub Action config PR branch")
    github_action_config_pr_status: Optional[str] = Field(default=None, description="Pending GitHub Action config PR status: pending, merged, closed")
    
    # Azure Pipeline config tracking
    azure_pipeline_config_pr_url: Optional[str] = Field(default=None, description="Pending Azure Pipeline config PR URL")
    azure_pipeline_config_pr_number: Optional[int] = Field(default=None, description="Pending Azure Pipeline config PR number")
    azure_pipeline_config_pr_branch: Optional[str] = Field(default=None, description="Pending Azure Pipeline config PR branch")
    azure_pipeline_config_pr_status: Optional[str] = Field(default=None, description="Pending Azure Pipeline config PR status: pending, merged, closed")
    
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

class ActionRunnerConnectionCreate(BaseModel):
    provider: str = Field(..., description="github or azure_devops")
    organization: str = Field(..., description="Org name (GitHub org or ADO org)")
    project: Optional[str] = Field(default=None, description="ADO project; null for GitHub")
    display_name: Optional[str] = None
    agent_pool: Optional[str] = Field(default=None, description="ADO agent pool name (e.g. 'PRAgent_Cloud')")


class ProvisionRunnerRequest(BaseModel):
    """Optional body for provisioning; ADO PAT is needed once for agent auto-registration."""
    ado_pat: Optional[str] = Field(default=None, description="Azure DevOps PAT with Agent Pools (read, manage) scope. Used once for registration, not stored.")
    agent_pool: Optional[str] = Field(default=None, description="Override agent pool (defaults to connection's agent_pool)")


class ActionRunnerConnectionResponse(BaseModel):
    id: int
    provider: str
    organization: str
    project: Optional[str]
    display_name: Optional[str]
    agent_pool: Optional[str] = None
    created_at: datetime
    updated_at: datetime
    repository_count: int = 0
    runner_status: Optional[str] = None
    gcp_instance_name: Optional[str] = None
    gcp_zone: Optional[str] = None

    class Config:
        from_attributes = True


class RepositoryCreate(BaseModel):
    name: str = Field(..., description="Repository name in format 'owner/repo-name'")
    provider: RepositoryProvider
    url: str = Field(..., description="Repository URL")
    is_active: bool = Field(default=True)
    action_runner_connection_id: Optional[int] = Field(default=None, description="Optional: link to shared runner connection (one per ADO org or GitHub org)")

    # Provider-specific configuration
    config: Optional[Dict[str, Any]] = None

    # Access tokens for health checks
    github_token: Optional[str] = None
    azure_pat: Optional[str] = None
    
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
    action_runner_connection_id: Optional[int] = None
    config: Optional[Dict[str, Any]] = None

    # Access tokens for health checks
    github_token: Optional[str] = None
    azure_pat: Optional[str] = None

    monitor_prs: Optional[bool] = None
    monitor_issues: Optional[bool] = None
    auto_review: Optional[bool] = None
    auto_describe: Optional[bool] = None
    auto_improve: Optional[bool] = None

# Notification Models
class NotificationConfigDB(Base):
    __tablename__ = "notification_configs"
    
    id = Column(Integer, primary_key=True, index=True)
    service_type = Column(String, index=True)  # "teams", "slack", "email"
    name = Column(String)  # User-friendly name for the config
    enabled = Column(Boolean, default=True)
    
    # Service-specific configuration
    webhook_url = Column(String, nullable=True)  # For Teams/Slack
    channel = Column(String, nullable=True)  # For Slack
    
    # Email configuration
    smtp_server = Column(String, nullable=True)
    smtp_port = Column(Integer, nullable=True)
    email_username = Column(String, nullable=True)
    email_password = Column(String, nullable=True)  # Should be encrypted
    recipient_emails = Column(JSON, nullable=True)  # List of email addresses
    
    # Event configuration
    event_types = Column(JSON, default=list)  # List of event types to notify for
    repository_filter = Column(JSON, nullable=True)  # List of repositories to monitor
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    last_test = Column(DateTime, nullable=True)
    test_status = Column(String, nullable=True)  # "success", "failed"

class NotificationEventDB(Base):
    __tablename__ = "notification_events"
    
    id = Column(Integer, primary_key=True, index=True)
    event_type = Column(String, index=True)
    event_data = Column(JSON)
    repositories = Column(JSON, nullable=True)  # List of repositories involved
    
    # Delivery tracking
    sent_to_services = Column(JSON, nullable=True)  # List of services it was sent to
    delivery_status = Column(JSON, nullable=True)  # Delivery status per service
    
    # Metadata
    timestamp = Column(DateTime, default=datetime.utcnow)
    processed = Column(Boolean, default=False)

class NotificationEventType(str, Enum):
    NEW_JOB = "new_job"
    NEW_OPERATION = "new_operation"
    JOB_FAILURE = "job_failure"
    SYSTEM_HEALTH_CHANGE = "system_health_change"
    TEST_NOTIFICATION = "test_notification"

class NotificationServiceType(str, Enum):
    TEAMS = "teams"
    SLACK = "slack"
    EMAIL = "email"

class NotificationConfig(BaseModel):
    id: Optional[int] = None
    service_type: NotificationServiceType
    name: str
    enabled: bool = True
    
    # Service-specific configuration
    webhook_url: Optional[str] = None
    channel: Optional[str] = None
    
    # Email configuration
    smtp_server: Optional[str] = None
    smtp_port: Optional[int] = None
    email_username: Optional[str] = None
    email_password: Optional[str] = None
    recipient_emails: Optional[List[str]] = None
    
    # Event configuration
    event_types: List[NotificationEventType] = Field(default_factory=list)
    repository_filter: Optional[List[str]] = None
    
    # Metadata
    created_at: Optional[str] = None
    updated_at: Optional[str] = None
    last_test: Optional[str] = None
    test_status: Optional[str] = None

    class Config:
        from_attributes = True

class NotificationConfigCreate(BaseModel):
    service_type: NotificationServiceType
    name: str
    enabled: bool = True
    
    # Service-specific configuration
    webhook_url: Optional[str] = None
    channel: Optional[str] = None
    
    # Email configuration
    smtp_server: Optional[str] = None
    smtp_port: Optional[int] = None
    email_username: Optional[str] = None
    email_password: Optional[str] = None
    recipient_emails: Optional[List[str]] = None
    
    # Event configuration
    event_types: List[NotificationEventType] = Field(default_factory=list)
    repository_filter: Optional[List[str]] = None

class NotificationConfigUpdate(BaseModel):
    name: Optional[str] = None
    enabled: Optional[bool] = None
    
    # Service-specific configuration
    webhook_url: Optional[str] = None
    channel: Optional[str] = None
    
    # Email configuration
    smtp_server: Optional[str] = None
    smtp_port: Optional[int] = None
    email_username: Optional[str] = None
    email_password: Optional[str] = None
    recipient_emails: Optional[List[str]] = None
    
    # Event configuration
    event_types: Optional[List[NotificationEventType]] = None
    repository_filter: Optional[List[str]] = None

class NotificationEvent(BaseModel):
    id: Optional[int] = None
    event_type: NotificationEventType
    event_data: Dict[str, Any]
    repositories: Optional[List[str]] = None
    
    # Delivery tracking
    sent_to_services: Optional[List[str]] = None
    delivery_status: Optional[Dict[str, str]] = None
    
    # Metadata
    timestamp: Optional[str] = None
    processed: bool = False

    class Config:
        from_attributes = True

class HealthCache(BaseModel):
    model_config = {'from_attributes': True}
    
    id: Optional[int] = None
    service_name: str
    status: str
    message: Optional[str] = None
    error_details: Optional[str] = None
    endpoint: Optional[str] = None
    
    # Cache metadata
    last_checked: str
    is_checking: bool = False
    check_count: int = 0
    
    # Additional data
    details: Optional[Dict[str, Any]] = None
    
    # Timestamps
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class MetricsAggregate(BaseModel):
    model_config = {'protected_namespaces': (), 'from_attributes': True}
    
    id: Optional[int] = None
    
    # Aggregate metrics
    total_jobs: int = 0
    total_operations: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_estimated_dev_hours: float = 0.0
    
    # Model breakdown
    model_usage: Dict[str, Any] = Field(default_factory=dict)
    
    # Timestamps
    last_updated: Optional[str] = None

class MetricsConfig(BaseModel):
    model_config = {'protected_namespaces': (), 'from_attributes': True}
    
    id: Optional[int] = None
    
    # Token pricing (per 1K tokens)
    model_costs: Dict[str, Dict[str, float]] = Field(default_factory=dict)
    
    # Developer cost calculation
    developer_hourly_rate: float = 75.0
    hours_multiplier: float = 1.0
    
    # Timestamps
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

class MetricsConfigUpdate(BaseModel):
    model_config = {'protected_namespaces': ()}
    
    model_costs: Optional[Dict[str, Dict[str, float]]] = None
    developer_hourly_rate: Optional[float] = None
    hours_multiplier: Optional[float] = None

class MetricsSummary(BaseModel):
    model_config = {'protected_namespaces': ()}
    
    # Computed metrics
    total_jobs: int
    total_operations: int
    total_input_tokens: int
    total_output_tokens: int
    total_token_cost: float
    total_dev_hours_saved: float
    total_dev_cost_saved: float
    total_savings: float  # dev_cost_saved - token_cost
    
    # Breakdown
    model_breakdown: Dict[str, Dict[str, Any]]
    
    # Configuration
    config: MetricsConfig

# Pydantic models for API
class User(BaseModel):
    id: int
    username: str
    is_active: bool
    created_at: datetime
    last_login: Optional[datetime] = None

class UserLogin(BaseModel):
    username: str
    password: str

class ChangePassword(BaseModel):
    current_password: str
    new_password: str 