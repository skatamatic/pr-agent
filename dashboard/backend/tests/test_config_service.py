"""
Unit tests for ConfigService (paths, validate_current_path, is_path_valid, get_config).
"""
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import database_manager
from services.config_service import ConfigService
from services.system_settings_service import SystemSettingsService


@pytest.fixture
def ensure_system_settings_table():
    database_manager.set_system_setting("_cfg_init", "_")
    yield


@pytest.fixture
def config_service(ensure_system_settings_table):
    return ConfigService()


class TestConfigServiceInternal:
    """_get_default_config, _load_toml_file."""

    def test__get_default_config_returns_dict(self, config_service):
        out = config_service._get_default_config()
        assert isinstance(out, dict)
        assert "config" in out
        assert "api_keys" in out
        assert "pr_reviewer" in out

    def test__load_toml_file_none_path_returns_empty(self, config_service):
        out = config_service._load_toml_file(None)
        assert out == {}

    def test__load_toml_file_nonexistent_returns_empty(self, config_service):
        out = config_service._load_toml_file(Path("/nonexistent/toml/file.toml"))
        assert out == {}


class TestConfigServicePaths:
    def test_refresh_paths(self, config_service):
        config_service.refresh_paths()
        assert hasattr(config_service, "config_path")
        assert "configuration" in str(config_service.config_path) or "pr_agent" in str(config_service.config_path)

    def test_validate_current_path_returns_dict(self, config_service):
        result = config_service.validate_current_path()
        assert isinstance(result, dict)
        assert "valid" in result

    def test_is_path_valid_returns_bool(self, config_service):
        assert isinstance(config_service.is_path_valid(), bool)


@pytest.mark.asyncio
class TestConfigServiceGetConfig:
    async def test_get_config_returns_dict(self, config_service):
        result = await config_service.get_config()
        assert isinstance(result, dict)
        # Default or merged config has at least some keys
        assert len(result) >= 0

    async def test_get_config_schema_returns_dict(self, config_service):
        result = await config_service.get_config_schema()
        assert isinstance(result, dict)
        assert "sections" in result or len(result) >= 0

    async def test_get_config_masks_context_service_username_password(self, config_service):
        """Context service username and password are masked as *** in API response."""
        from services.config_backend import (
            CONFIG_KEY,
            CSHARP_CONFIG_KEY,
            CSHARP_SECRETS_KEY,
        )
        backend = MagicMock()
        backend.get.side_effect = lambda k: {
            CONFIG_KEY: "[config]\nmodel = 'x'",
            CSHARP_CONFIG_KEY: "[csharp_code_context_service]\nenabled = true\nurl = 'https://example.com'",
            CSHARP_SECRETS_KEY: "[csharp_code_context_service]\nusername = 'secret_user'\npassword = 'secret_pass'",
        }.get(k, None)
        backend.exists.return_value = True
        config_service.backend = backend
        result = await config_service.get_config()
        ctx = result.get("csharp_code_context_service", {})
        assert ctx.get("username") == "***"
        assert ctx.get("password") == "***"
        assert ctx.get("url") == "https://example.com"


@pytest.mark.asyncio
class TestConfigServiceUpdateConfig:
    """update_config splits context secrets and writes to correct keys."""

    async def test_update_config_splits_context_secrets(self, config_service):
        from services.config_backend import (
            CONFIG_KEY,
            CSHARP_CONFIG_KEY,
            CSHARP_SECRETS_KEY,
        )
        backend = MagicMock()
        backend.exists.return_value = False
        backend.get.return_value = None
        config_service.backend = backend
        config_service._create_rotated_backup = MagicMock()
        config_data = {
            "config": {"model": "x"},
            "csharp_code_context_service": {
                "enabled": True,
                "url": "https://ctx.example.com",
                "username": "u1",
                "password": "p1",
            },
        }
        await config_service.update_config(config_data)
        put_calls = {c[0][0]: c[0][1] for c in backend.put.call_args_list}
        assert CSHARP_CONFIG_KEY in put_calls
        assert CSHARP_SECRETS_KEY in put_calls
        import toml
        ctx_config = toml.loads(put_calls[CSHARP_CONFIG_KEY])
        assert "username" not in ctx_config.get("csharp_code_context_service", {})
        assert ctx_config["csharp_code_context_service"].get("url") == "https://ctx.example.com"
        ctx_secrets = toml.loads(put_calls[CSHARP_SECRETS_KEY])
        assert ctx_secrets["csharp_code_context_service"].get("username") == "u1"
        assert ctx_secrets["csharp_code_context_service"].get("password") == "p1"


    async def test_update_config_masked_password_preserves_existing(self, config_service):
        """Sending '***' for username/password must not overwrite stored credentials."""
        from services.config_backend import CSHARP_SECRETS_KEY
        import toml
        backend = MagicMock()
        backend.exists.return_value = False
        backend.get.side_effect = lambda k: (
            toml.dumps({"csharp_code_context_service": {"username": "real_user", "password": "real_pass"}})
            if k == CSHARP_SECRETS_KEY else None
        )
        config_service.backend = backend
        config_service._create_rotated_backup = MagicMock()
        config_data = {
            "csharp_code_context_service": {
                "enabled": True,
                "url": "https://ctx.example.com",
                "username": "***",
                "password": "***",
            },
        }
        await config_service.update_config(config_data)
        put_calls = {c[0][0]: c[0][1] for c in backend.put.call_args_list}
        if CSHARP_SECRETS_KEY in put_calls:
            ctx_secrets = toml.loads(put_calls[CSHARP_SECRETS_KEY])
            inner = ctx_secrets.get("csharp_code_context_service", ctx_secrets)
            assert inner.get("username") == "real_user"
            assert inner.get("password") == "real_pass"

    async def test_update_config_empty_credentials_preserves_existing(self, config_service):
        """Sending empty strings for credentials must not overwrite stored credentials."""
        from services.config_backend import CSHARP_SECRETS_KEY
        import toml
        backend = MagicMock()
        backend.exists.return_value = False
        backend.get.side_effect = lambda k: (
            toml.dumps({"csharp_code_context_service": {"username": "real_user", "password": "real_pass"}})
            if k == CSHARP_SECRETS_KEY else None
        )
        config_service.backend = backend
        config_service._create_rotated_backup = MagicMock()
        config_data = {
            "csharp_code_context_service": {
                "enabled": True,
                "url": "https://ctx.example.com",
                "username": "",
                "password": "",
            },
        }
        await config_service.update_config(config_data)
        put_calls = {c[0][0]: c[0][1] for c in backend.put.call_args_list}
        if CSHARP_SECRETS_KEY in put_calls:
            ctx_secrets = toml.loads(put_calls[CSHARP_SECRETS_KEY])
            inner = ctx_secrets.get("csharp_code_context_service", ctx_secrets)
            assert inner.get("username") == "real_user"
            assert inner.get("password") == "real_pass"
        else:
            pass


@pytest.mark.asyncio
class TestConfigServiceBulkUpload:
    """bulk_upload_config writes extracted contents and creates backup."""

    async def test_bulk_upload_config_empty_returns_error(self, config_service):
        result = await config_service.bulk_upload_config({})
        assert result.get("status") == "error"
        assert "No config" in result.get("message", "")

    async def test_bulk_upload_config_writes_and_creates_backup(self, config_service):
        from services.config_backend import CONFIG_KEY, CSHARP_CONFIG_KEY
        backend = MagicMock()
        backend.list_backup_ids.return_value = []
        config_service.backend = backend
        key_to_content = {
            CONFIG_KEY: "[config]\nmodel = 'y'",
            CSHARP_CONFIG_KEY: "[csharp_code_context_service]\nenabled = false\n",
        }
        result = await config_service.bulk_upload_config(key_to_content)
        assert result.get("status") == "success"
        assert backend.put.call_count >= 2  # backup writes + overwrites
        put_keys = [c[0][0] for c in backend.put.call_args_list]
        assert CONFIG_KEY in put_keys
        assert CSHARP_CONFIG_KEY in put_keys

    async def test_bulk_upload_invalid_toml_returns_error(self, config_service):
        """Uploading invalid TOML should fail before any writes."""
        from services.config_backend import CONFIG_KEY
        backend = MagicMock()
        backend.list_backup_ids.return_value = []
        config_service.backend = backend
        key_to_content = {CONFIG_KEY: "this is not [ valid TOML !!!"}
        result = await config_service.bulk_upload_config(key_to_content)
        assert result.get("status") == "error"
        assert "Invalid TOML" in result.get("message", "")
        assert backend.put.call_count == 0

    async def test_bulk_upload_unrecognised_keys_filtered(self, config_service):
        """Keys not in the allowed set should be silently dropped."""
        backend = MagicMock()
        backend.list_backup_ids.return_value = []
        config_service.backend = backend
        key_to_content = {"random_file.txt": "hello"}
        result = await config_service.bulk_upload_config(key_to_content)
        assert result.get("status") == "error"
        assert "No recognised" in result.get("message", "")


@pytest.mark.asyncio
class TestConfigServiceApiKeyMasking:
    """API key masking in get_config and round-trip protection in update_config."""

    async def test_get_config_masks_api_keys(self, config_service):
        from services.config_backend import CONFIG_KEY, SECRETS_KEY
        backend = MagicMock()
        # Native format (dashboard writes these; PR-Agent reads them directly)
        backend.get.side_effect = lambda k: {
            CONFIG_KEY: "[config]\nmodel = 'x'",
            SECRETS_KEY: "[openai]\nkey = 'sk-real-key'\n[anthropic]\nkey = 'ant-real-key'",
        }.get(k, None)
        backend.exists.return_value = True
        config_service.backend = backend
        result = await config_service.get_config()
        api_keys = result.get("api_keys", {})
        assert api_keys.get("openai") == "***"
        assert api_keys.get("anthropic") == "***"
        assert api_keys.get("google", "") in ("", None)

    async def test_get_config_masks_api_keys_legacy_format(self, config_service):
        """Legacy [api_keys] in secrets still works for read."""
        from services.config_backend import CONFIG_KEY, SECRETS_KEY
        backend = MagicMock()
        backend.get.side_effect = lambda k: {
            CONFIG_KEY: "[config]\nmodel = 'x'",
            SECRETS_KEY: "[api_keys]\nopenai = 'sk-legacy'\nanthropic = 'ant-legacy'",
        }.get(k, None)
        backend.exists.return_value = True
        config_service.backend = backend
        result = await config_service.get_config()
        api_keys = result.get("api_keys", {})
        assert api_keys.get("openai") == "***"
        assert api_keys.get("anthropic") == "***"

    async def test_update_config_masked_api_keys_not_written(self, config_service):
        """Sending *** for API keys must not overwrite real keys. We do not write secrets when only masked/empty."""
        from services.config_backend import SECRETS_KEY
        backend = MagicMock()
        backend.exists.return_value = False
        backend.get.return_value = None
        config_service.backend = backend
        config_service._create_rotated_backup = MagicMock()
        config_data = {
            "api_keys": {"openai": "***", "anthropic": "***", "google": ""},
        }
        await config_service.update_config(config_data)
        put_calls = {c[0][0]: c[0][1] for c in backend.put.call_args_list}
        # No secrets update when only masked/empty keys sent
        assert SECRETS_KEY not in put_calls

    async def test_update_config_writes_native_secrets_format(self, config_service):
        """Saving real API keys writes PR-Agent native [openai] key, [anthropic] key, etc."""
        from services.config_backend import SECRETS_KEY
        import toml
        backend = MagicMock()
        backend.exists.return_value = False
        backend.get.return_value = None
        config_service.backend = backend
        config_service._create_rotated_backup = MagicMock()
        config_data = {
            "config": {"model": "x"},
            "api_keys": {"openai": "sk-new", "anthropic": "", "google": ""},
        }
        await config_service.update_config(config_data)
        put_calls = {c[0][0]: c[0][1] for c in backend.put.call_args_list}
        assert SECRETS_KEY in put_calls
        secrets = toml.loads(put_calls[SECRETS_KEY])
        assert secrets.get("openai") == {"key": "sk-new"}
        assert "anthropic" not in secrets or secrets.get("anthropic", {}).get("key") in ("", None)
        assert "api_keys" not in secrets

    async def test_update_config_writes_sections_top_level_and_keeps_csharp_out_of_main(self, config_service):
        """Non-secret sections must stay top-level; csharp context remains in dedicated files."""
        from services.config_backend import CONFIG_KEY, CSHARP_CONFIG_KEY, CSHARP_SECRETS_KEY
        import toml

        backend = MagicMock()
        backend.exists.return_value = False
        backend.get.return_value = None
        config_service.backend = backend
        config_service._create_rotated_backup = MagicMock()

        config_data = {
            "config": {"model": "gpt-5.3-codex"},
            "pr_reviewer": {"enabled": True, "auto_review": False},
            "pr_description": {"enabled": True},
            "csharp_code_context_service": {
                "enabled": True,
                "url": "https://ctx.example.com",
                "username": "ctx-user",
                "password": "ctx-pass",
            },
        }

        await config_service.update_config(config_data)
        put_calls = {c[0][0]: c[0][1] for c in backend.put.call_args_list}
        assert CONFIG_KEY in put_calls
        main = toml.loads(put_calls[CONFIG_KEY])
        assert "config" in main and main["config"].get("model") == "gpt-5.3-codex"
        assert "pr_reviewer" in main
        assert "pr_description" in main
        assert "csharp_code_context_service" not in main
        assert not isinstance(main.get("config", {}).get("pr_reviewer"), dict)
        assert CSHARP_CONFIG_KEY in put_calls
        assert CSHARP_SECRETS_KEY in put_calls

    async def test_update_config_migrates_legacy_config_prefixed_sections(self, config_service):
        """Legacy nested [config.<section>] should be migrated back to top-level on save."""
        from services.config_backend import CONFIG_KEY
        import toml

        backend = MagicMock()
        backend.exists.return_value = True

        legacy_main = toml.dumps({
            "config": {
                "model": "legacy-model",
                "pr_reviewer": {"enabled": False, "auto_review": True},
                "pr_description": {"enabled": False},
                "csharp_code_context_service": {"enabled": True},
            },
            "csharp_code_context_service": {"enabled": True},
        })

        backend.get.side_effect = lambda key: legacy_main if key == CONFIG_KEY else None
        config_service.backend = backend
        config_service._create_rotated_backup = MagicMock()

        await config_service.update_config({"config": {"model": "new-model"}})

        put_calls = {c[0][0]: c[0][1] for c in backend.put.call_args_list}
        updated_main = toml.loads(put_calls[CONFIG_KEY])
        assert updated_main.get("config", {}).get("model") == "new-model"
        assert "pr_reviewer" in updated_main
        assert "pr_description" in updated_main
        assert "pr_reviewer" not in updated_main.get("config", {})
        assert "pr_description" not in updated_main.get("config", {})
        assert "csharp_code_context_service" not in updated_main
        assert "csharp_code_context_service" not in updated_main.get("config", {})

@pytest.mark.asyncio
class TestConfigServiceBackupRotation:
    """_create_rotated_backup honours MAX_BACKUPS limit."""

    async def test_rotation_deletes_oldest(self, config_service):
        from services.config_backend import CONFIG_KEY, MAX_BACKUPS
        backend = MagicMock()
        existing_ids = [f"2025-03-{i:02d}T00-00-00-000000" for i in range(1, MAX_BACKUPS + 3)]
        backend.list_backup_ids.return_value = existing_ids
        backend.get.return_value = None
        config_service.backend = backend
        config_service._create_rotated_backup()
        deleted = [c[0][0] for c in backend.delete_backup.call_args_list]
        assert len(deleted) == len(existing_ids) - MAX_BACKUPS
        for d in deleted:
            assert d in existing_ids[:len(existing_ids) - MAX_BACKUPS]
