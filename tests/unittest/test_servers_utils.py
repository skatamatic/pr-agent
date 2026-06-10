"""Tests for pr_agent.servers.utils (signature verification, rate-limit helper)."""
import hashlib
import hmac

import pytest
from fastapi import HTTPException

from pr_agent.servers.utils import DefaultDictWithTimeout, verify_signature


class TestVerifySignature:
    def test_accepts_valid_github_signature(self):
        secret = "my-webhook-secret"
        body = b'{"action":"opened"}'
        digest = hmac.new(secret.encode("utf-8"), msg=body, digestmod=hashlib.sha256).hexdigest()
        header = "sha256=" + digest
        verify_signature(body, secret, header)

    def test_rejects_missing_header(self):
        with pytest.raises(HTTPException) as exc:
            verify_signature(b"{}", "secret", None)
        assert exc.value.status_code == 403
        assert "missing" in exc.value.detail.lower()

    def test_rejects_bad_signature(self):
        with pytest.raises(HTTPException) as exc:
            verify_signature(b"{}", "secret", "sha256=deadbeef")
        assert exc.value.status_code == 403
        assert "didn't match" in exc.value.detail.lower()


class TestDefaultDictWithTimeout:
    def test_set_and_get_updates_key_time(self):
        d = DefaultDictWithTimeout(list, ttl=3600, refresh_interval=60)
        d["k"].append(1)
        assert d["k"] == [1]

    def test_delitem_removes_key(self):
        d = DefaultDictWithTimeout(list, ttl=None)
        d["a"] = [1]
        del d["a"]
        assert "a" not in d
