"""
System Settings Service - Manages global dashboard settings
"""
import os
from pathlib import Path
from typing import Optional, Dict, Any
from database import SessionLocal
from sqlalchemy import text


class SystemSettingsService:
    """Service for managing system-wide settings"""
    
    def __init__(self, database_manager=None):
        self.database_manager = database_manager
    
    def get_setting(self, key: str) -> Optional[str]:
        """Get a system setting value by key"""
        with SessionLocal() as db:
            try:
                result = db.execute(
                    text("SELECT value FROM system_settings WHERE key = :key"),
                    {"key": key}
                ).fetchone()
                return result[0] if result else None
            except Exception as e:
                print(f"Error getting setting {key}: {str(e)}")
                return None
    
    def set_setting(self, key: str, value: str) -> bool:
        """Set a system setting value"""
        with SessionLocal() as db:
            try:
                # Use UPSERT (INSERT OR REPLACE for SQLite)
                db.execute(
                    text("""
                        INSERT OR REPLACE INTO system_settings (key, value, updated_at) 
                        VALUES (:key, :value, CURRENT_TIMESTAMP)
                    """),
                    {"key": key, "value": value}
                )
                db.commit()
                return True
            except Exception as e:
                print(f"Error setting setting {key}: {str(e)}")
                db.rollback()
                return False
    
    def delete_setting(self, key: str) -> bool:
        """Delete a system setting"""
        with SessionLocal() as db:
            try:
                db.execute(
                    text("DELETE FROM system_settings WHERE key = :key"),
                    {"key": key}
                )
                db.commit()
                return True
            except Exception as e:
                print(f"Error deleting setting {key}: {str(e)}")
                db.rollback()
                return False
    
    def get_all_settings(self) -> Dict[str, str]:
        """Get all system settings as a dictionary"""
        with SessionLocal() as db:
            try:
                result = db.execute(
                    text("SELECT key, value FROM system_settings")
                ).fetchall()
                return {row[0]: row[1] for row in result}
            except Exception as e:
                print(f"Error getting all settings: {str(e)}")
                return {}
    
    # PR-Agent specific methods
    def get_pr_agent_install_path(self) -> Optional[str]:
        """Get the custom PR-agent install path"""
        return self.get_setting("pr_agent_install_path")
    
    def set_pr_agent_install_path(self, path: str) -> bool:
        """Set the custom PR-agent install path"""
        return self.set_setting("pr_agent_install_path", path)
    
    def validate_pr_agent_path(self, path: str) -> Dict[str, Any]:
        """
        Validate that the PR-agent path contains the necessary configuration files
        Returns validation result with status and details
        """
        try:
            path_obj = Path(path)
            
            if not path_obj.exists():
                return {
                    "valid": False,
                    "error": "Path does not exist",
                    "details": f"Directory '{path}' not found"
                }
            
            if not path_obj.is_dir():
                return {
                    "valid": False,
                    "error": "Path is not a directory",
                    "details": f"'{path}' is not a directory"
                }
            
            # Check for expected PR-agent structure
            settings_dir = path_obj / "pr_agent" / "settings"
            config_file = settings_dir / "configuration.toml"
            
            if not settings_dir.exists():
                return {
                    "valid": False,
                    "error": "PR-agent settings directory not found",
                    "details": f"Expected '{settings_dir}' directory not found"
                }
            
            if not config_file.exists():
                return {
                    "valid": False,
                    "error": "Main configuration file not found",
                    "details": f"Expected '{config_file}' file not found"
                }
            
            # Check for additional expected files
            expected_files = [
                "ignore.toml",
                "language_extensions.toml",
                "pr_reviewer_prompts.toml",
                "pr_description_prompts.toml"
            ]
            
            missing_files = []
            found_files = []
            
            for filename in expected_files:
                file_path = settings_dir / filename
                if file_path.exists():
                    found_files.append(filename)
                else:
                    missing_files.append(filename)
            
            # Optional files (warn if missing but still valid)
            optional_files = [
                "secrets.toml",
                "csharp_code_context.config.toml",
                "csharp_code_context_secrets.toml"
            ]
            
            optional_found = []
            optional_missing = []
            
            for filename in optional_files:
                file_path = settings_dir / filename
                if file_path.exists():
                    optional_found.append(filename)
                else:
                    optional_missing.append(filename)
            
            # Path is valid if we have the main config and at least some core files
            is_valid = len(found_files) >= 3  # At least 3 of the 4 expected files
            
            return {
                "valid": is_valid,
                "error": None if is_valid else "Insufficient PR-agent configuration files",
                "details": {
                    "path": str(path_obj),
                    "settings_dir": str(settings_dir),
                    "config_file": str(config_file),
                    "found_files": found_files,
                    "missing_files": missing_files,
                    "optional_found": optional_found,
                    "optional_missing": optional_missing,
                    "total_found": len(found_files),
                    "total_expected": len(expected_files)
                }
            }
            
        except Exception as e:
            return {
                "valid": False,
                "error": "Validation error",
                "details": f"Error validating path: {str(e)}"
            }
    
    def get_default_pr_agent_path(self) -> str:
        """Get the default PR-agent path (relative to dashboard)"""
        # Default behavior - relative path from dashboard backend
        config_dir = Path(__file__).parent.parent  # dashboard/backend
        pr_agent_root = config_dir.parent.parent    # go up to pr-agent root
        return str(pr_agent_root)
    
    def get_effective_pr_agent_path(self) -> str:
        """Get the effective PR-agent path (settings.toml or default)"""
        # Check settings.toml for pr_agent_path
        try:
            from config import settings
            if hasattr(settings, 'pr_agent_path') and settings.pr_agent_path:
                return str(settings.pr_agent_path)
        except Exception as e:
            print(f"Warning: Could not read pr_agent_path from settings.toml: {e}")
        
        # Fall back to default path
        return self.get_default_pr_agent_path() 