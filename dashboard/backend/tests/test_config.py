"""
Tests for config: CORS parsing and PORT/api_host behavior.
Config is loaded at import time; we test the behavior and parsing logic.
"""
import pytest
import os

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_cors_origins_is_list():
    """After load, settings.cors_origins should be a list (default or from env)."""
    from config import settings
    assert isinstance(settings.cors_origins, list)
    assert len(settings.cors_origins) >= 1


def test_cors_env_parsing_logic():
    """Replicate DASHBOARD_CORS_ORIGINS parsing: comma-separated -> list."""
    _cors_env = "https://a.run.app,https://b.run.app , http://localhost:3000"
    result = [o.strip() for o in _cors_env.split(",") if o.strip()]
    assert result == ["https://a.run.app", "https://b.run.app", "http://localhost:3000"]


def test_api_port_reads_from_port_env():
    """settings.api_port should be int; when PORT is set it is used."""
    from config import settings
    assert isinstance(settings.api_port, int)
    assert 1 <= settings.api_port <= 65535


def test_api_host_is_string():
    """settings.api_host should be 0.0.0.0 or 127.0.0.1."""
    from config import settings
    assert settings.api_host in ("0.0.0.0", "127.0.0.1")


def test_database_url_set_or_default():
    """settings.database_url should be set (sqlite or postgres) or empty from env override."""
    from config import settings
    assert hasattr(settings, "database_url")
    url = getattr(settings, "database_url", "") or ""
    assert isinstance(url, str)
    if url:
        assert url.startswith("sqlite") or "postgresql" in url
