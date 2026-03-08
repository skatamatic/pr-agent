"""
Configuration Service - Responsible for managing PR-Agent configuration
Follows Single Responsibility Principle

Config location from env only (no DB):
- PR_AGENT_CONFIG_PATH: local directory; dashboard and PR-Agent both use it.
- PR_AGENT_CONFIG_GCS_BUCKET + PREFIX: GCS; both use same bucket so dashboard edits apply to next PR-Agent run.
"""
import logging
import os
import toml
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)
from config import settings
from .system_settings_service import SystemSettingsService
from .config_backend import (
    get_config_backend,
    LocalConfigBackend,
    GCSConfigBackend,
    CONFIG_KEY,
    SECRETS_KEY,
    CSHARP_CONFIG_KEY,
    CSHARP_SECRETS_KEY,
    IGNORE_KEY,
    BACKUP_KEY,
    BACKUP_PREFIX,
    MAX_BACKUPS,
)


def _get_config_base_path() -> Path:
    """Resolve config directory from env (local only). For GCS, use get_config_backend()."""
    path_env = os.getenv("PR_AGENT_CONFIG_PATH", "").strip()
    if path_env:
        return Path(path_env).resolve()
    svc = SystemSettingsService()
    default_root = Path(svc.get_effective_pr_agent_path())
    return default_root / "pr_agent" / "settings"


class ConfigService:
    """Service for managing PR-Agent configuration files (local or GCS backend)."""
    
    def __init__(self, database_manager=None):
        self.database_manager = database_manager
        self.system_settings = SystemSettingsService(database_manager)
        self.backend = get_config_backend()
        self._initialize_paths()
    
    def _initialize_paths(self):
        """Set path attributes for display/compat; actual I/O uses self.backend."""
        base_path = _get_config_base_path()
        self.config_path = base_path / "configuration.toml"
        self.backup_path = base_path / "configuration.toml.backup"
        self.secrets_path = base_path / ".secrets.toml"
        self.ignore_path = base_path / "ignore.toml"
        self.csharp_context_config_path = base_path / "csharp_code_context.config.toml"
        self.csharp_context_secrets_path = base_path / "csharp_code_context.secrets.toml"
    
    def refresh_paths(self):
        self.backend = get_config_backend()
        self._initialize_paths()
    
    def get_config_source(self) -> Dict[str, Any]:
        """Current config location from env (no DB)."""
        path_env = os.getenv("PR_AGENT_CONFIG_PATH", "").strip()
        gcs_bucket = os.getenv("PR_AGENT_CONFIG_GCS_BUCKET", "").strip()
        if path_env:
            return {"config_path": str(Path(path_env).resolve()), "source": "env", "env_var": "PR_AGENT_CONFIG_PATH"}
        if gcs_bucket:
            prefix = os.getenv("PR_AGENT_CONFIG_GCS_PREFIX", "pr-agent-config/").strip()
            return {"config_path": f"gs://{gcs_bucket}/{prefix}", "source": "gcs", "env_var": "PR_AGENT_CONFIG_GCS_BUCKET"}
        base = _get_config_base_path()
        return {"config_path": str(base), "source": "default", "env_var": None}
    
    def validate_current_path(self) -> Dict[str, Any]:
        if isinstance(self.backend, GCSConfigBackend):
            return {"valid": True, "details": {"backend": "gcs", "bucket": self.backend.bucket_name, "prefix": self.backend.prefix}}
        return self.validate_config_path(_get_config_base_path())

    def validate_config_path(self, path: Any) -> Dict[str, Any]:
        path_obj = Path(path).resolve()
        if not path_obj.exists():
            return {"valid": False, "error": "Path does not exist", "details": str(path_obj)}
        if not path_obj.is_dir():
            return {"valid": False, "error": "Not a directory", "details": str(path_obj)}
        return {"valid": True, "details": {"config_path": str(path_obj), "config_file_exists": (path_obj / "configuration.toml").exists()}}
    
    def is_path_valid(self) -> bool:
        return self.validate_current_path().get("valid", False)

    async def ensure_cloud_config(self) -> Dict[str, Any]:
        """Auto-seed dashboard connection info and default azure_devops_config into GCS.

        Called once on backend startup. Only fills in values that are missing so
        user edits are never overwritten. Requires GCS backend; silently no-ops for local.
        """
        if not isinstance(self.backend, GCSConfigBackend):
            return {"seeded": False, "reason": "not_gcs"}

        seeded = []
        try:
            # ---- configuration.toml: dashboard.url + azure_devops_config defaults ----
            raw_cfg = self.backend.get(CONFIG_KEY) or ""
            cfg = {}
            try:
                cfg = toml.loads(raw_cfg) if raw_cfg.strip() else {}
            except toml.TomlDecodeError:
                logger.warning("GCS configuration.toml is invalid TOML; skipping auto-seed for it")
                cfg = None

            if cfg is not None:
                changed = False
                dashboard_section = cfg.setdefault("dashboard", {})
                if not dashboard_section.get("url") and getattr(settings, "backend_base_url", ""):
                    dashboard_section["url"] = settings.backend_base_url
                    changed = True
                    seeded.append("dashboard.url")

                ado_section = cfg.setdefault("azure_devops_config", {})
                ado_defaults = {
                    "auto_describe": True,
                    "auto_review": True,
                    "auto_improve": True,
                    "enable_output": True,
                    "pr_actions": ["pullrequest"],
                }
                for k, v in ado_defaults.items():
                    if k not in ado_section:
                        ado_section[k] = v
                        changed = True
                        seeded.append(f"azure_devops_config.{k}")

                if not cfg.get("config", {}).get("git_provider"):
                    cfg.setdefault("config", {})["git_provider"] = "azure"
                    changed = True
                    seeded.append("config.git_provider")

                if changed:
                    self.backend.put(CONFIG_KEY, toml.dumps(cfg))

            # ---- secrets.toml: dashboard.api_key ----
            raw_sec = self.backend.get(SECRETS_KEY) or ""
            sec = {}
            try:
                sec = toml.loads(raw_sec) if raw_sec.strip() else {}
            except toml.TomlDecodeError:
                logger.warning("GCS secrets.toml is invalid TOML; skipping auto-seed for it")
                sec = None

            if sec is not None:
                changed_sec = False
                dash_sec = sec.setdefault("dashboard", {})
                api_key = getattr(settings, "dashboard_api_key", "")
                if api_key and not dash_sec.get("api_key"):
                    dash_sec["api_key"] = api_key
                    changed_sec = True
                    seeded.append("dashboard.api_key")

                if changed_sec:
                    self.backend.put(SECRETS_KEY, toml.dumps(sec))

        except Exception as e:
            logger.error("Auto-seed GCS config failed: %s", e)
            return {"seeded": False, "error": str(e)}

        if seeded:
            logger.info("Auto-seeded GCS config: %s", ", ".join(seeded))
        return {"seeded": bool(seeded), "keys": seeded}

    def _create_rotated_backup(self) -> None:
        """Create a named/dated backup of all config keys and keep at most MAX_BACKUPS."""
        now = datetime.now(timezone.utc)
        backup_id = now.strftime("%Y-%m-%dT%H-%M-%S") + f"-{now.microsecond:06d}"
        keys_to_backup = [CONFIG_KEY, SECRETS_KEY, CSHARP_CONFIG_KEY, CSHARP_SECRETS_KEY, IGNORE_KEY]
        for key in keys_to_backup:
            content = self.backend.get(key)
            if content:
                self.backend.put_backup(backup_id, key, content)
        ids = self.backend.list_backup_ids()
        if len(ids) > MAX_BACKUPS:
            for bid in ids[:-MAX_BACKUPS]:
                self.backend.delete_backup(bid)
                logger.info("Rotated config backup: removed %s", bid)
    
    def _load_toml_from_backend(self, key: str) -> Dict[str, Any]:
        """Load TOML from backend by key. Returns {} if missing or on error."""
        content = self.backend.get(key)
        if not content:
            return {}
        try:
            return toml.loads(content)
        except Exception as e:
            logger.error("Failed to parse TOML for %s: %s", key, e)
            return {}
    
    def _load_toml_file(self, file_path: Optional[Path]) -> Dict[str, Any]:
        """Load TOML from path; used by tests. Production uses _load_toml_from_backend."""
        if file_path is None:
            return {}
        if isinstance(self.backend, LocalConfigBackend):
            key = next((k for k, v in LocalConfigBackend.KEY_TO_FILENAME.items() if self.backend._path_for(k) == Path(file_path)), None)
            if key:
                return self._load_toml_from_backend(key)
        if Path(file_path).exists():
            try:
                return toml.load(file_path)
            except Exception:
                pass
        return {}
    
    def _get_default_config(self) -> Dict[str, Any]:
        """Get default configuration when no config file exists"""
        return {
            "config": {
                "model": "anthropic/claude-sonnet-4-6-20260205",
                "model_reasoning": "anthropic/claude-opus-4-6-20260205",
                "model_weak": "gpt-5.3-codex-spark",
                "fallback_models": ["gpt-5.3-codex-spark"],
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
            },
            "pr_filters": {
                "skip_if_description_exists": True,
                "terminate_on_no_bots": True,
                "max_lines_changed": 1000
            }
        }
    
    async def get_config(self) -> Dict[str, Any]:
        """Get current PR-Agent configuration from backend (local or GCS)."""
        try:
            config = self._get_default_config()
            main_config = self._load_toml_from_backend(CONFIG_KEY)
            if main_config:
                config = self._deep_merge(config, main_config)
            secrets_config = self._load_toml_from_backend(SECRETS_KEY)
            if secrets_config:
                # Build api_keys for API/UI from PR-Agent native TOML sections (no bridge in PR-Agent)
                def _read(key: str, native_section: str, native_field: str) -> str:
                    if isinstance(secrets_config.get(native_section), dict) and secrets_config[native_section].get(native_field):
                        return secrets_config[native_section][native_field]
                    if isinstance(secrets_config.get('api_keys'), dict) and secrets_config['api_keys'].get(key):
                        return secrets_config['api_keys'][key]
                    return ""
                config['api_keys'] = {
                    'openai': _read('openai', 'openai', 'key'),
                    'anthropic': _read('anthropic', 'anthropic', 'key'),
                    'google': _read('google', 'google_ai_studio', 'gemini_api_key'),
                }
                # Merge any other secret sections (e.g. dashboard)
                for key, value in secrets_config.items():
                    if key not in ('api_keys', 'openai', 'anthropic', 'google_ai_studio'):
                        config[key] = self._deep_merge(config.get(key, {}), value) if isinstance(value, dict) else value
            
            context_config = self._load_toml_from_backend(CSHARP_CONFIG_KEY)
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
            
            context_secrets = self._load_toml_from_backend(CSHARP_SECRETS_KEY)
            if context_secrets:
                # Merge context service secrets (file may be [csharp_code_context_service] or flat)
                inner = context_secrets.get("csharp_code_context_service", context_secrets)
                if isinstance(inner, dict):
                    config.setdefault("csharp_code_context_service", {}).update(inner)
            
            ignore_config = self._load_toml_from_backend(IGNORE_KEY)
            if ignore_config:
                config['ignore'] = ignore_config

            # Mask all secrets for API response (do not expose actual values)
            if config.get('api_keys') and isinstance(config['api_keys'], dict):
                for key in config['api_keys']:
                    if config['api_keys'][key]:
                        config['api_keys'][key] = '***'
            if config.get('csharp_code_context_service'):
                ctx = config['csharp_code_context_service']
                if ctx.get('username'):
                    ctx['username'] = '***'
                if ctx.get('password'):
                    ctx['password'] = '***'
            
            return config
            
        except Exception as e:
            logger.error("Failed to load configuration: %s", e, exc_info=True)
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
        try:
            logger.info("Starting configuration update with %s sections", len(config_data))
            self._create_rotated_backup()

            # Separate configuration into different files
            main_config = {}
            secrets_config = {}
            context_config = {}
            context_secrets = {}  # username, password -> csharp_code_context.secrets.toml

            # Distribute settings to appropriate files
            for section_key, section_value in config_data.items():
                logger.debug("Processing section: %s", section_key)
                if section_key == 'api_keys':
                    # Write PR-Agent native TOML sections so no bridge is needed in config_loader
                    if isinstance(section_value, dict):
                        openai_val = section_value.get('openai') or ''
                        anthropic_val = section_value.get('anthropic') or ''
                        google_val = section_value.get('google') or ''
                        if openai_val and openai_val != '***':
                            secrets_config['openai'] = {'key': openai_val}
                        if anthropic_val and anthropic_val != '***':
                            secrets_config['anthropic'] = {'key': anthropic_val}
                        if google_val and google_val != '***':
                            secrets_config['google_ai_studio'] = {'gemini_api_key': google_val}
                    logger.debug("Added api_keys to secrets config (native openai/anthropic/google_ai_studio)")
                elif section_key == 'csharp_code_context_service':
                    # Split context: non-secret -> config file, username/password -> secrets file
                    ctx = section_value if isinstance(section_value, dict) else {}
                    context_config['csharp_code_context_service'] = {
                        k: v for k, v in ctx.items()
                        if k not in ('username', 'password')
                    }
                    if ctx.get('username') is not None or ctx.get('password') is not None:
                        if ctx.get('username') not in (None, '', '***'):
                            context_secrets['username'] = ctx['username']
                        if ctx.get('password') not in (None, '', '***'):
                            context_secrets['password'] = ctx['password']
                    logger.debug("Added csharp_code_context_service to context config and secrets")
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
            
            if main_config:
                logger.info("Updating main config")
                await self._update_single_config_backend(CONFIG_KEY, main_config)
            if secrets_config:
                logger.info("Updating secrets config")
                await self._update_single_config_backend(SECRETS_KEY, secrets_config)
            if context_config:
                logger.info("Updating context config")
                await self._update_single_config_backend(CSHARP_CONFIG_KEY, context_config)
            if context_secrets:
                logger.info("Updating context secrets")
                existing_secrets = self._load_toml_from_backend(CSHARP_SECRETS_KEY)
                existing_ctx = existing_secrets.get('csharp_code_context_service', existing_secrets)
                if not isinstance(existing_ctx, dict):
                    existing_ctx = {}
                merged_ctx = {**existing_ctx, **context_secrets}
                self.backend.put(CSHARP_SECRETS_KEY, toml.dumps({'csharp_code_context_service': merged_ctx}))
            
            logger.info("Configuration update completed successfully")
            return {"status": "success", "message": "Configuration updated successfully across multiple files"}
            
        except Exception as e:
            logger.error(f"Configuration update failed: {str(e)}")
            return {"status": "error", "message": f"Failed to update configuration: {str(e)}"}
    
    async def _update_single_config_backend(self, key: str, config_data: Dict[str, Any]):
        """Update a single config by key (backend handles local or GCS).
        Rotated backup is already created by _create_rotated_backup() before this is called."""
        existing = self._load_toml_from_backend(key)
        merged = self._deep_merge(existing, config_data)
        self.backend.put(key, toml.dumps(merged))
    
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
    
    # Filename to logical key for bulk upload (accept both .secrets.toml and secrets.toml)
    BULK_UPLOAD_FILENAMES = {
        "configuration.toml": CONFIG_KEY,
        ".secrets.toml": SECRETS_KEY,
        "secrets.toml": SECRETS_KEY,
        "csharp_code_context.config.toml": CSHARP_CONFIG_KEY,
        "csharp_code_context.secrets.toml": CSHARP_SECRETS_KEY,
        "ignore.toml": IGNORE_KEY,
    }

    async def bulk_upload_config(self, key_to_content: Dict[str, str]) -> Dict[str, Any]:
        """
        Overwrite backend config with provided file contents (extracted from upload; no ZIP is stored).
        key_to_content: logical key (CONFIG_KEY, SECRETS_KEY, etc.) -> full file content as string.
        Creates a rotated backup before overwriting, then writes each content to the backend.
        """
        try:
            if not key_to_content:
                return {"status": "error", "message": "No config files provided"}
            allowed = {CONFIG_KEY, SECRETS_KEY, CSHARP_CONFIG_KEY, CSHARP_SECRETS_KEY, IGNORE_KEY}
            to_write = {k: v for k, v in key_to_content.items() if k in allowed}
            if not to_write:
                return {"status": "error", "message": "No recognised config files in upload"}
            for key, content in to_write.items():
                try:
                    toml.loads(content)
                except toml.TomlDecodeError as e:
                    return {"status": "error", "message": f"Invalid TOML in {key}: {e}"}
            self._create_rotated_backup()
            for key, content in to_write.items():
                self.backend.put(key, content)
            logger.info("Bulk config upload completed: %s keys written", len(to_write))
            return {"status": "success", "message": f"Uploaded {len(to_write)} config file(s). Backup created."}
        except Exception as e:
            logger.error("Bulk config upload failed: %s", e)
            return {"status": "error", "message": str(e)}

    async def restore_backup(self) -> Dict[str, str]:
        """Restore configuration from backup (backend)."""
        try:
            if not self.backend.exists(BACKUP_KEY):
                return {"status": "error", "message": "No backup file found"}
            content = self.backend.get(BACKUP_KEY)
            if not content:
                return {"status": "error", "message": "No backup content"}
            self.backend.put(CONFIG_KEY, content)
            return {"status": "success", "message": "Configuration restored from backup"}
        except Exception as e:
            return {"status": "error", "message": str(e)}
    
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