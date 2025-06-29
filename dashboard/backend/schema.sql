-- Database Schema for PR Agent Dashboard
-- Generated automatically

CREATE TABLE operations (
	id INTEGER NOT NULL, 
	operation_id VARCHAR, 
	command VARCHAR, 
	repo VARCHAR, 
	pr_url VARCHAR, 
	status VARCHAR, 
	started_at DATETIME DEFAULT CURRENT_TIMESTAMP, 
	last_updated DATETIME DEFAULT CURRENT_TIMESTAMP, 
	completed_at DATETIME, 
	duration FLOAT, 
	error_details TEXT, 
	installation_id VARCHAR, 
	sender VARCHAR, 
	request_id VARCHAR, 
	response_time FLOAT, 
	context_fetch_time FLOAT, 
	ai_processing_time FLOAT, 
	suggestions_count INTEGER, 
	errors_count INTEGER, 
	warnings_count INTEGER, 
	job_id VARCHAR, 
	operation_type VARCHAR, 
	result_data JSON, 
	model_used VARCHAR, 
	input_tokens INTEGER, 
	output_tokens INTEGER, 
	estimated_dev_hours_saved FLOAT, 
	PRIMARY KEY (id)
);

CREATE TABLE log_entries (
	id INTEGER NOT NULL, 
	timestamp DATETIME, 
	level VARCHAR, 
	message TEXT, 
	module VARCHAR, 
	function VARCHAR, 
	line INTEGER, 
	pr_url VARCHAR, 
	command VARCHAR, 
	installation_id VARCHAR, 
	repo VARCHAR, 
	sender VARCHAR, 
	request_id VARCHAR, 
	sub_feature VARCHAR, 
	status VARCHAR, 
	analytics BOOLEAN DEFAULT FALSE, 
	artifact JSON, 
	artifacts JSON, 
	error JSON, 
	app_name VARCHAR, 
	build_number VARCHAR, 
	git_provider VARCHAR, 
	received_at VARCHAR, 
	job_id VARCHAR, 
	operation_id VARCHAR, 
	PRIMARY KEY (id)
);

CREATE TABLE repositories (
	id INTEGER NOT NULL, 
	name VARCHAR, 
	provider VARCHAR, 
	url VARCHAR, 
	is_active BOOLEAN DEFAULT TRUE, 
	config JSON, 
	monitor_prs BOOLEAN DEFAULT TRUE, 
	monitor_issues BOOLEAN DEFAULT FALSE, 
	auto_review BOOLEAN DEFAULT TRUE, 
	auto_describe BOOLEAN DEFAULT TRUE, 
	auto_improve BOOLEAN DEFAULT FALSE, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP, 
	updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, 
	last_activity DATETIME, 
	github_token VARCHAR, 
	azure_pat VARCHAR, 
	runner_status VARCHAR, 
	runner_last_seen DATETIME, 
	runner_error VARCHAR, 
	has_pr_agent_config BOOLEAN DEFAULT FALSE, 
	config_last_checked DATETIME, 
	effective_config JSON, 
	has_workflow_config BOOLEAN DEFAULT FALSE, 
	PRIMARY KEY (id)
);

CREATE TABLE jobs (
	id INTEGER NOT NULL, 
	job_id VARCHAR, 
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
	error_details TEXT, 
	PRIMARY KEY (id)
);

CREATE TABLE notification_configs (
	id INTEGER NOT NULL, 
	service_type VARCHAR, 
	name VARCHAR, 
	enabled BOOLEAN DEFAULT TRUE, 
	webhook_url VARCHAR, 
	channel VARCHAR, 
	smtp_server VARCHAR, 
	smtp_port INTEGER, 
	email_username VARCHAR, 
	email_password VARCHAR, 
	recipient_emails JSON, 
	event_types JSON DEFAULT '[]', 
	repository_filter JSON, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP, 
	updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, 
	last_test DATETIME, 
	test_status VARCHAR, 
	PRIMARY KEY (id)
);

CREATE TABLE notification_events (
	id INTEGER NOT NULL, 
	event_type VARCHAR, 
	event_data JSON, 
	repositories JSON, 
	sent_to_services JSON, 
	delivery_status JSON, 
	timestamp DATETIME DEFAULT CURRENT_TIMESTAMP, 
	processed BOOLEAN DEFAULT FALSE, 
	PRIMARY KEY (id)
);

CREATE TABLE system_settings (
                        key TEXT PRIMARY KEY,
                        value TEXT,
                        updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                    );

CREATE TABLE users (
	id INTEGER NOT NULL, 
	username VARCHAR NOT NULL, 
	password_hash VARCHAR NOT NULL, 
	is_active BOOLEAN DEFAULT TRUE, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP, 
	last_login DATETIME, 
	PRIMARY KEY (id)
);

CREATE TABLE health_cache (
	id INTEGER NOT NULL, 
	service_name VARCHAR, 
	status VARCHAR, 
	message VARCHAR, 
	error_details VARCHAR, 
	endpoint VARCHAR, 
	last_checked DATETIME DEFAULT CURRENT_TIMESTAMP, 
	is_checking BOOLEAN DEFAULT FALSE, 
	check_count INTEGER DEFAULT 0, 
	details JSON, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP, 
	updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id)
);

CREATE TABLE metrics_aggregate (
	id INTEGER NOT NULL, 
	total_jobs INTEGER DEFAULT 0, 
	total_operations INTEGER DEFAULT 0, 
	total_input_tokens INTEGER DEFAULT 0, 
	total_output_tokens INTEGER DEFAULT 0, 
	total_estimated_dev_hours FLOAT DEFAULT 0.0, 
	model_usage JSON DEFAULT '{}', 
	last_updated DATETIME DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id)
);

CREATE TABLE metrics_config (
	id INTEGER NOT NULL, 
	model_costs JSON DEFAULT '{}', 
	developer_hourly_rate FLOAT DEFAULT 75.0, 
	hours_multiplier FLOAT DEFAULT 1.0, 
	created_at DATETIME DEFAULT CURRENT_TIMESTAMP, 
	updated_at DATETIME DEFAULT CURRENT_TIMESTAMP, 
	PRIMARY KEY (id)
);

CREATE INDEX ix_operations_id ON operations (id);

CREATE UNIQUE INDEX ix_operations_operation_id ON operations (operation_id);

CREATE INDEX ix_log_entries_id ON log_entries (id);

CREATE UNIQUE INDEX ix_repositories_name ON repositories (name);

CREATE INDEX ix_repositories_id ON repositories (id);

CREATE INDEX ix_jobs_id ON jobs (id);

CREATE UNIQUE INDEX ix_jobs_job_id ON jobs (job_id);

CREATE INDEX ix_notification_configs_service_type ON notification_configs (service_type);

CREATE INDEX ix_notification_configs_id ON notification_configs (id);

CREATE INDEX ix_notification_events_event_type ON notification_events (event_type);

CREATE INDEX ix_notification_events_id ON notification_events (id);

CREATE UNIQUE INDEX ix_health_cache_service_name ON health_cache (service_name);

CREATE INDEX ix_health_cache_id ON health_cache (id);

CREATE INDEX ix_metrics_aggregate_id ON metrics_aggregate (id);

CREATE INDEX ix_metrics_config_id ON metrics_config (id);

CREATE INDEX ix_users_id ON users (id);

CREATE UNIQUE INDEX ix_users_username ON users (username);

