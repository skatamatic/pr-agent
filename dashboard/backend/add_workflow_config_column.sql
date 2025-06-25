-- Migration script to add has_workflow_config column to repositories table
-- Run this if you get database errors about missing column

ALTER TABLE repositories ADD COLUMN has_workflow_config BOOLEAN DEFAULT FALSE;

-- Update existing repositories to set default value
UPDATE repositories SET has_workflow_config = FALSE WHERE has_workflow_config IS NULL; 