"""
Configuration Service - Responsible for managing PR-Agent configuration
Follows Single Responsibility Principle
"""
import toml
import shutil
from pathlib import Path
from typing import Dict, Any, Optional
from config import settings
from .system_settings_service import SystemSettingsService


class ConfigService:
    """Service for managing PR-Agent configuration files"""
    
    def __init__(self, database_manager=None):
        # Store database manager (optional for now)
        self.database_manager = database_manager
        
        # Initialize system settings service
        self.system_settings = SystemSettingsService(database_manager)
        
        # Initialize all configuration file paths using effective PR-agent path
        self._initialize_paths()
    
    def _initialize_paths(self):
        """Initialize all configuration file paths using the effective PR-agent install path"""
        # Get the effective PR-agent path (custom or default)
        pr_agent_path = self.system_settings.get_effective_pr_agent_path()
        base_path = Path(pr_agent_path) / "pr_agent" / "settings"
        
        # Initialize all configuration file paths
        self.config_path = base_path / "configuration.toml"
        self.backup_path = base_path / "configuration.toml.backup"
        self.secrets_path = base_path / "secrets.toml"
        self.ignore_path = base_path / "ignore.toml"
        self.csharp_context_config_path = base_path / "csharp_code_context.config.toml"
        self.csharp_context_secrets_path = base_path / "csharp_code_context_secrets.toml"
    
    def refresh_paths(self):
        """Refresh all configuration paths (useful when PR-agent path changes)"""
        self._initialize_paths()
    
    def validate_current_path(self) -> Dict[str, Any]:
        """Validate the current PR-agent install path"""
        current_path = self.system_settings.get_effective_pr_agent_path()
        return self.system_settings.validate_pr_agent_path(current_path)
    
    def is_path_valid(self) -> bool:
        """Check if the current PR-agent path is valid"""
        validation = self.validate_current_path()
        return validation.get('valid', False)
    
    def _load_toml_file(self, file_path: Optional[Path]) -> Dict[str, Any]:
        """Load a TOML file safely, returning empty dict if file doesn't exist or has errors"""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            if file_path and file_path.exists():
                logger.debug(f"Loading TOML file: {file_path}")
                with open(file_path, 'r', encoding='utf-8') as f:
                    config = toml.load(f)
                logger.debug(f"Successfully loaded TOML file: {file_path}")
                return config
            else:
                logger.debug(f"TOML file does not exist: {file_path}")
        except Exception as e:
            logger.error(f"Failed to load TOML file {file_path}: {str(e)}")
        return {}
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration when no config file exists"""
        return {
            "config": {
                "model": "anthropic/claude-3-5-sonnet-20241022",
                "model_reasoning": "anthropic/claude-3-5-sonnet-20241022", 
                "model_weak": "gpt-4o-mini",
                "fallback_models": ["gpt-4o-mini"],
                "reasoning_effort": "high",
                "max_model_tokens": 94000,
                "temperature": 0.2,
                "verbosity_level": 2,
                "ai_timeout": 180,
                "publish_output": True,
                "enable_auto_approval": False
            },
            "pr_reviewer": {
                "enabled": True,
                "require_tests": False,
                "auto_review": False
            },
            "pr_description": {
                "enabled": True,
                "publish_description": True
            },
            "pr_code_suggestions": {
                "enabled": True,
                "auto_improve": False
            },
            "csharp_code_context_service": {
                "enabled": False,
                "default_depth": 1,
                "default_mode": "Minified",
                "timeout": 180,
                "url": ""
            },
            "enabled_actions": {
                "pr_reviewer": True,
                "pr_description": True,
                "pr_code_suggestions": True,
                "pr_questions": True,
                "pr_test": False,
                "pr_add_docs": False,
                "pr_update_changelog": False
            },
            "api_keys": {
                "openai": "",
                "anthropic": "",
                "google": ""
            },
            "pr_dev_time_estimation": {
                "enabled": True,
                "model": "",
                "fallback_to_heuristic": True,
                "estimation_timeout_seconds": 30,
                "confidence_threshold": "medium"
            }
        }
    
    async def get_config(self) -> Dict[str, Any]:
        """Get current PR-Agent configuration from multiple TOML files"""
        try:
            # Start with default configuration
            config = self._get_default_config()
            
            # Load main configuration
            main_config = self._load_toml_file(self.config_path)
            if main_config:
                config = self._deep_merge(config, main_config)
            
            # Load secrets configuration (overwrites any secrets in main config)
            secrets_config = self._load_toml_file(self.secrets_path)
            if secrets_config:
                # Merge API keys and other secrets
                if 'api_keys' in secrets_config:
                    config.setdefault('api_keys', {}).update(secrets_config['api_keys'])
                # Merge any other secret sections
                for key, value in secrets_config.items():
                    if key != 'api_keys':
                        config[key] = self._deep_merge(config.get(key, {}), value) if isinstance(value, dict) else value
            
            # Load C# context service configuration
            context_config = self._load_toml_file(self.csharp_context_config_path)
            if context_config:
                # Merge the context service configuration
                if 'csharp_code_context_service' in context_config:
                    config['csharp_code_context_service'] = self._deep_merge(
                        config.get('csharp_code_context_service', {}),
                        context_config['csharp_code_context_service']
                    )
                else:
                    # If the entire file is context service config
                    config['csharp_code_context_service'] = self._deep_merge(
                        config.get('csharp_code_context_service', {}),
                        context_config
                    )
            
            # Load C# context service secrets
            context_secrets = self._load_toml_file(self.csharp_context_secrets_path)
            if context_secrets:
                # Merge context service secrets
                config.setdefault('csharp_code_context_service', {}).update(context_secrets)
            
            # Load ignore patterns (for completeness, though not typically shown in UI)
            ignore_config = self._load_toml_file(self.ignore_path)
            if ignore_config:
                config['ignore'] = ignore_config
            
            return config
            
        except Exception as e:
            # On any error, return default config
            print(f"Warning: Failed to load configuration: {str(e)}")
            return self._get_default_config()
    
    def _deep_merge(self, default: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Deep merge two dictionaries, with override taking precedence"""
        result = default.copy()
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = self._deep_merge(result[key], value)
            else:
                result[key] = value
        
        return result
    
    async def update_config(self, config_data: Dict[str, Any]) -> Dict[str, str]:
        """Update PR-Agent configuration by distributing settings to appropriate files"""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            logger.info(f"Starting configuration update with {len(config_data)} sections")
            
            # Log the current paths being used
            logger.info(f"Config paths - Main: {self.config_path}, Secrets: {self.secrets_path}, Context: {self.csharp_context_config_path}")
            
            # Separate configuration into different files
            main_config = {}
            secrets_config = {}
            context_config = {}
            
            # Distribute settings to appropriate files
            for section_key, section_value in config_data.items():
                logger.debug(f"Processing section: {section_key}")
                if section_key == 'api_keys':
                    # API keys go to secrets file
                    secrets_config['api_keys'] = section_value
                    logger.debug(f"Added {section_key} to secrets config")
                elif section_key == 'csharp_code_context_service':
                    # Context service config goes to its own file
                    context_config['csharp_code_context_service'] = section_value
                    logger.debug(f"Added {section_key} to context config")
                elif section_key in ['ignore']:
                    # Skip ignore patterns for now
                    logger.debug(f"Skipping {section_key} section")
                    continue
                else:
                    # Everything else goes to main config under [config] section
                    if 'config' not in main_config:
                        main_config['config'] = {}
                    main_config['config'][section_key] = section_value
                    logger.debug(f"Added {section_key} to main config")
            
            # Update main configuration file
            if main_config and self.config_path:
                logger.info(f"Updating main config file: {self.config_path}")
                await self._update_single_config_file(self.config_path, main_config, self.backup_path)
            
            # Update secrets file if we have API keys
            if secrets_config and self.secrets_path:
                logger.info(f"Updating secrets file: {self.secrets_path}")
                await self._update_single_config_file(self.secrets_path, secrets_config)
            
            # Update context service config if we have those settings
            if context_config and self.csharp_context_config_path:
                logger.info(f"Updating context config file: {self.csharp_context_config_path}")
                await self._update_single_config_file(self.csharp_context_config_path, context_config)
            
            logger.info("Configuration update completed successfully")
            return {"status": "success", "message": "Configuration updated successfully across multiple files"}
            
        except Exception as e:
            logger.error(f"Configuration update failed: {str(e)}")
            return {"status": "error", "message": f"Failed to update configuration: {str(e)}"}
    
    async def _update_single_config_file(self, file_path: Path, config_data: Dict[str, Any], backup_path: Optional[Path] = None):
        """Update a single configuration file surgically, preserving structure and only changing modified values"""
        # Ensure directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Create backup if config exists and backup path provided
        if file_path.exists() and backup_path:
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(file_path, backup_path)
        
        # Use surgical update approach
        await self._surgical_update_toml(file_path, config_data)
    
    async def _surgical_update_toml(self, file_path: Path, new_data: Dict[str, Any]):
        """Update a TOML file by loading, merging, and saving - avoiding duplicate keys"""
        import logging
        logger = logging.getLogger(__name__)
        
        try:
            # Ensure parent directory exists
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            if not file_path.exists():
                # If file doesn't exist, create it with the new data
                logger.info(f"Creating new TOML file: {file_path}")
                with open(file_path, 'w', encoding='utf-8') as f:
                    toml.dump(new_data, f)
                return
            
            # Load existing config
            existing_config = self._load_toml_file(file_path)
            if not existing_config:
                existing_config = {}
            
            # Deep merge the configurations
            merged_config = self._deep_merge(existing_config, new_data)
            
            # Write the merged config back to the file
            logger.info(f"Updating TOML file: {file_path}")
            with open(file_path, 'w', encoding='utf-8') as f:
                toml.dump(merged_config, f)
            
            logger.info(f"Successfully updated TOML file: {file_path}")
            
        except Exception as e:
            logger.error(f"Failed to update TOML file {file_path}: {str(e)}")
            raise
    
    def _find_config_changes(self, existing: Dict[str, Any], new: Dict[str, Any]) -> Dict[str, Any]:
        """Find what has actually changed between existing and new config"""
        changes = {}
        
        for key, value in new.items():
            if key not in existing:
                # New key
                changes[key] = {'type': 'new', 'value': value}
            elif isinstance(value, dict) and isinstance(existing[key], dict):
                # Nested dictionary - check recursively
                nested_changes = self._find_config_changes(existing[key], value)
                if nested_changes:
                    changes[key] = {'type': 'nested', 'changes': nested_changes}
            elif existing[key] != value:
                # Value changed
                changes[key] = {'type': 'changed', 'old_value': existing[key], 'new_value': value}
        
        return changes
    
    async def restore_backup(self) -> Dict[str, str]:
        """Restore configuration from backup"""
        try:
            if not self.backup_path or not self.backup_path.exists():
                return {"status": "error", "message": "No backup file found"}
            
            if not self.config_path:
                return {"status": "error", "message": "Configuration path not available"}
            
            shutil.copy2(self.backup_path, self.config_path)
            return {"status": "success", "message": "Configuration restored from backup"}
            
        except Exception as e:
            return {"status": "error", "message": f"Failed to restore backup: {str(e)}"}
    
    async def validate_config(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """Validate configuration data"""
        validation_result = {
            "valid": True,
            "errors": [],
            "warnings": []
        }
        
        # Basic validation rules
        required_sections = ['config']
        for section in required_sections:
            if section not in config_data:
                validation_result["errors"].append(f"Missing required section: {section}")
                validation_result["valid"] = False
        
        # Validate model configurations
        if 'config' in config_data:
            config_section = config_data['config']
            
            # Check for required model settings
            if 'model' not in config_section:
                validation_result["warnings"].append("No default model specified")
            
            # Validate API key presence (without exposing values)
            api_keys = config_data.get('api_keys', {})
            has_api_key = any(key and key.strip() for key in api_keys.values())
            if not has_api_key:
                validation_result["warnings"].append("No API keys configured")
        
        # Validate context service configuration
        if 'csharp_code_context_service' in config_data:
            context_config = config_data['csharp_code_context_service']
            if context_config.get('enabled', False) and not context_config.get('url'):
                validation_result["warnings"].append("Context service enabled but no URL specified")
        
        return validation_result
    
    async def get_config_schema(self) -> Dict[str, Any]:
        """Get configuration schema for validation and UI generation"""
        return {
            "sections": {
                "config": {
                    "title": "General Configuration",
                    "fields": {
                        "model": {"type": "string", "required": True, "description": "Default AI model"},
                        "openai_key": {"type": "string", "sensitive": True, "description": "OpenAI API key"},
                        "anthropic_key": {"type": "string", "sensitive": True, "description": "Anthropic API key"},
                        "max_tokens": {"type": "integer", "default": 4000, "description": "Maximum tokens per request"}
                    }
                },
                "pr_reviewer": {
                    "title": "PR Reviewer Settings",
                    "fields": {
                        "enabled": {"type": "boolean", "default": True, "description": "Enable PR review"},
                        "require_tests": {"type": "boolean", "default": False, "description": "Require test coverage"}
                    }
                },
                "csharp_code_context_service": {
                    "title": "Code Context Service",
                    "fields": {
                        "enabled": {"type": "boolean", "default": False, "description": "Enable context service"},
                        "url": {"type": "string", "description": "Context service URL"},
                        "timeout": {"type": "integer", "default": 30, "description": "Request timeout in seconds"}
                    }
                },
                "pr_dev_time_estimation": {
                    "title": "Developer Time Estimation",
                    "fields": {
                        "enabled": {"type": "boolean", "default": True, "description": "Enable AI-powered developer time estimation"},
                        "model": {"type": "string", "default": "", "description": "AI model to use for time estimation (leave empty to use same as tool)"},
                        "fallback_to_heuristic": {"type": "boolean", "default": True, "description": "Fall back to heuristic estimation if AI fails"},
                        "estimation_timeout_seconds": {"type": "integer", "default": 30, "description": "Timeout for AI estimation calls"},
                        "confidence_threshold": {"type": "select", "options": ["low", "medium", "high"], "default": "medium", "description": "Minimum confidence level to accept AI estimates"}
                    }
                }
            }
        } 