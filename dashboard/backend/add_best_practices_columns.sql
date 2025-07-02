-- Migration: Add best practices tracking columns to repositories table
-- Date: 2024-01-15

-- Add best practices tracking columns
ALTER TABLE repositories ADD COLUMN has_best_practices BOOLEAN DEFAULT FALSE;
ALTER TABLE repositories ADD COLUMN best_practices_content TEXT;
ALTER TABLE repositories ADD COLUMN best_practices_last_fetched DATETIME;
ALTER TABLE repositories ADD COLUMN best_practices_pr_url TEXT;
ALTER TABLE repositories ADD COLUMN best_practices_pr_number INTEGER;
ALTER TABLE repositories ADD COLUMN best_practices_pr_branch TEXT;
ALTER TABLE repositories ADD COLUMN best_practices_pr_status TEXT;

-- Update existing repositories to have default values
UPDATE repositories SET has_best_practices = FALSE WHERE has_best_practices IS NULL;

-- Create index for faster queries on PR status
CREATE INDEX IF NOT EXISTS idx_repositories_best_practices_pr_status ON repositories(best_practices_pr_status); 