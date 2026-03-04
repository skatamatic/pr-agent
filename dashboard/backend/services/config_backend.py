"""
Config backends for PR-Agent settings (local filesystem or GCS).

When PR_AGENT_CONFIG_GCS_BUCKET is set (and PR_AGENT_CONFIG_PATH is not),
dashboard and PR-Agent use GCS so they share the same config.
"""
from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)

# Logical keys (GCS object names; local maps e.g. secrets.toml -> .secrets.toml)
CONFIG_KEY = "configuration.toml"
SECRETS_KEY = "secrets.toml"
CSHARP_CONFIG_KEY = "csharp_code_context.config.toml"
CSHARP_SECRETS_KEY = "csharp_code_context.secrets.toml"
IGNORE_KEY = "ignore.toml"
BACKUP_KEY = "configuration.toml.backup"
BACKUP_PREFIX = "backups/"
MAX_BACKUPS = 10


class ConfigBackend(ABC):
    """Abstract backend for reading/writing PR-Agent config files."""

    @abstractmethod
    def get(self, key: str) -> Optional[str]:
        """Return file content as string, or None if missing."""
        pass

    @abstractmethod
    def put(self, key: str, content: str) -> None:
        """Write content for the given key."""
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Return True if the key exists."""
        pass

    @abstractmethod
    def list_backup_ids(self) -> List[str]:
        """Return sorted list of backup id strings (e.g. '2025-03-03T12-00-00') under BACKUP_PREFIX."""
        pass

    @abstractmethod
    def delete_backup(self, backup_id: str) -> None:
        """Delete all keys under backups/<backup_id>/."""
        pass

    def put_backup(self, backup_id: str, logical_key: str, content: str) -> None:
        """Write content to backups/<backup_id>/<logical_key>. Uses put() with composite key."""
        if not backup_id or "/" in backup_id or ".." in backup_id:
            return
        self.put(f"{BACKUP_PREFIX}{backup_id}/{logical_key}", content)


class LocalConfigBackend(ConfigBackend):
    """Backend that uses the local filesystem under a base path."""

    KEY_TO_FILENAME = {
        CONFIG_KEY: "configuration.toml",
        SECRETS_KEY: ".secrets.toml",
        CSHARP_CONFIG_KEY: "csharp_code_context.config.toml",
        CSHARP_SECRETS_KEY: "csharp_code_context.secrets.toml",
        IGNORE_KEY: "ignore.toml",
        BACKUP_KEY: "configuration.toml.backup",
    }

    def __init__(self, base_path: Path):
        self.base_path = Path(base_path)

    def _path_for(self, key: str) -> Path:
        if "/" in key:
            return self.base_path / key
        return self.base_path / self.KEY_TO_FILENAME.get(key, key)

    def get(self, key: str) -> Optional[str]:
        p = self._path_for(key)
        if not p.exists():
            return None
        try:
            return p.read_text(encoding="utf-8")
        except Exception as e:
            logger.error("Failed to read %s: %s", p, e)
            return None

    def put(self, key: str, content: str) -> None:
        p = self._path_for(key)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content, encoding="utf-8")

    def exists(self, key: str) -> bool:
        return self._path_for(key).exists()

    def list_backup_ids(self) -> List[str]:
        backup_dir = self.base_path / BACKUP_PREFIX.rstrip("/")
        if not backup_dir.exists() or not backup_dir.is_dir():
            return []
        return sorted(p.name for p in backup_dir.iterdir() if p.is_dir())

    def delete_backup(self, backup_id: str) -> None:
        if not backup_id or "/" in backup_id or ".." in backup_id:
            return
        import shutil
        path = self.base_path / BACKUP_PREFIX.rstrip("/") / backup_id
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)


class GCSConfigBackend(ConfigBackend):
    """Backend that uses Google Cloud Storage (same bucket/prefix as PR-Agent)."""

    def __init__(self, bucket_name: str, prefix: str = ""):
        self.bucket_name = bucket_name
        self.prefix = prefix.rstrip("/")
        if self.prefix:
            self.prefix += "/"
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                from google.cloud import storage
                self._client = storage.Client()
            except ImportError:
                raise RuntimeError(
                    "GCS config backend requires google-cloud-storage. "
                    "pip install google-cloud-storage"
                )
        return self._client

    def _blob_name(self, key: str) -> str:
        return self.prefix + key

    def get(self, key: str) -> Optional[str]:
        try:
            client = self._get_client()
            bucket = client.bucket(self.bucket_name)
            blob = bucket.blob(self._blob_name(key))
            if not blob.exists():
                return None
            return blob.download_as_text(encoding="utf-8")
        except Exception as e:
            logger.error("GCS get %s: %s", key, e)
            return None

    def put(self, key: str, content: str) -> None:
        try:
            client = self._get_client()
            bucket = client.bucket(self.bucket_name)
            blob = bucket.blob(self._blob_name(key))
            blob.upload_from_string(content, content_type="text/plain; charset=utf-8")
        except Exception as e:
            logger.error("GCS put %s: %s", key, e)
            raise

    def exists(self, key: str) -> bool:
        try:
            client = self._get_client()
            bucket = client.bucket(self.bucket_name)
            blob = bucket.blob(self._blob_name(key))
            return blob.exists()
        except Exception as e:
            logger.error("GCS exists %s: %s", key, e)
            return False

    def list_backup_ids(self) -> List[str]:
        try:
            client = self._get_client()
            bucket = client.bucket(self.bucket_name)
            prefix = self._blob_name(BACKUP_PREFIX)  # e.g. "pr-agent-config/backups/"
            ids = set()
            for blob in bucket.list_blobs(prefix=prefix):
                # blob.name e.g. "pr-agent-config/backups/2025-03-03T12-00-00/configuration.toml"
                name = blob.name
                if prefix and name.startswith(prefix):
                    rest = name[len(prefix):].lstrip("/")
                    if "/" in rest:
                        ids.add(rest.split("/")[0])
            return sorted(ids)
        except Exception as e:
            logger.error("GCS list_backup_ids: %s", e)
            return []

    def delete_backup(self, backup_id: str) -> None:
        if not backup_id or "/" in backup_id or ".." in backup_id:
            return
        try:
            client = self._get_client()
            bucket = client.bucket(self.bucket_name)
            prefix = self._blob_name(f"{BACKUP_PREFIX}{backup_id}/")
            for blob in bucket.list_blobs(prefix=prefix):
                blob.delete()
        except Exception as e:
            logger.error("GCS delete_backup %s: %s", backup_id, e)


def get_config_backend():
    """
    Build config backend from env.
    PR_AGENT_CONFIG_PATH (local) wins; else PR_AGENT_CONFIG_GCS_BUCKET (GCS); else local default.
    """
    path_env = os.getenv("PR_AGENT_CONFIG_PATH", "").strip()
    if path_env:
        return LocalConfigBackend(Path(path_env).resolve())
    bucket = os.getenv("PR_AGENT_CONFIG_GCS_BUCKET", "").strip()
    if bucket:
        prefix = os.getenv("PR_AGENT_CONFIG_GCS_PREFIX", "pr-agent-config/").strip()
        return GCSConfigBackend(bucket_name=bucket, prefix=prefix)
    from .system_settings_service import SystemSettingsService
    svc = SystemSettingsService()
    base = Path(svc.get_effective_pr_agent_path()) / "pr_agent" / "settings"
    return LocalConfigBackend(base)
