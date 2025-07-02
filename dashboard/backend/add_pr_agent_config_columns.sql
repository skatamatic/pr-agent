-- Migration script to add PR-Agent config tracking columns to repositories table
-- Run this if you have an existing database without these columns

BEGIN TRANSACTION;

-- Add PR-Agent config tracking columns
ALTER TABLE repositories ADD COLUMN has_pr_agent_config BOOLEAN DEFAULT FALSE;
ALTER TABLE repositories ADD COLUMN pr_agent_config_content TEXT;
ALTER TABLE repositories ADD COLUMN pr_agent_config_last_fetched DATETIME;
ALTER TABLE repositories ADD COLUMN pr_agent_config_pr_url VARCHAR;
ALTER TABLE repositories ADD COLUMN pr_agent_config_pr_number INTEGER;
ALTER TABLE repositories ADD COLUMN pr_agent_config_pr_branch VARCHAR;
ALTER TABLE repositories ADD COLUMN pr_agent_config_pr_status VARCHAR;

-- Update existing repositories to have default values
UPDATE repositories SET has_pr_agent_config = FALSE WHERE has_pr_agent_config IS NULL;

COMMIT; 