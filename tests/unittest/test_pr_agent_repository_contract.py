"""
Unit tests for canonical `repository` field in PR-Agent logging integration.
No DB, network, or LLM — mocks only.
"""
import pytest
from unittest.mock import MagicMock, patch

from pr_agent.log.dashboard_sink import DashboardSink
from pr_agent.log.job_context import (
    JobContext,
    OperationType,
    bind_logger_context,
    get_current_context,
    operation_context,
)


class TestOperationContextRepository:
    def teardown_method(self):
        JobContext.clear_operation_context()
        JobContext.clear_job_context()

    def test_operation_context_metadata_uses_repository_key_only(self):
        with patch("pr_agent.log.job_context.get_dashboard_client", None):
            with patch("pr_agent.log.job_context.logger", None):
                with operation_context(
                    OperationType.REVIEW,
                    repository="owner/name",
                    command="review",
                ):
                    meta = JobContext.get_operation_metadata()
                    assert meta.get("repository") == "owner/name"
                    assert "repo" not in meta

    def test_get_current_context_exposes_repository(self):
        with patch("pr_agent.log.job_context.get_dashboard_client", None):
            with patch("pr_agent.log.job_context.logger", None):
                with operation_context(
                    OperationType.DESCRIBE,
                    repository="acme/core",
                    command="describe",
                ):
                    ctx = get_current_context()
                    assert ctx["operation_metadata"].get("repository") == "acme/core"


class TestBindLoggerContextRepository:
    def teardown_method(self):
        JobContext.clear_operation_context()
        JobContext.clear_job_context()

    def test_bind_logger_context_includes_repository_not_repo(self):
        mock_logger = MagicMock()
        mock_bound = MagicMock()
        mock_logger.bind.return_value = mock_bound

        # Establish context without triggering logger.bind in set_operation_context
        with patch("pr_agent.log.job_context.get_dashboard_client", None):
            with patch("pr_agent.log.job_context.logger", None):
                JobContext.set_operation_context(
                    "op-test-1",
                    {
                        "operation_type": "review",
                        "repository": "acme/widget",
                    },
                )
        try:
            with patch("pr_agent.log.job_context.logger", mock_logger):
                bind_logger_context()
        finally:
            JobContext.clear_operation_context()

        mock_logger.bind.assert_called_once()
        kwargs = mock_logger.bind.call_args.kwargs
        assert kwargs.get("repository") == "acme/widget"
        assert "repo" not in kwargs


class TestDashboardSinkFormatLogEntry:
    def test_format_log_entry_includes_repository_from_extra(self):
        sink = DashboardSink(dashboard_url=None)
        from types import SimpleNamespace

        record = {
            "time": SimpleNamespace(timestamp=lambda: 1_700_000_000.0),
            "level": SimpleNamespace(name="INFO"),
            "message": "hello",
            "name": "test_mod",
            "function": "fn",
            "line": 42,
            "extra": {
                "repository": "org/repo",
                "job_id": "j-1",
            },
        }

        with patch("pr_agent.log.job_context.JobContext.get_current_step", return_value=None):
            entry = sink._format_log_entry(record)

        assert entry.get("repository") == "org/repo"
        assert "repo" not in entry

    def test_format_log_entry_legacy_repo_in_extra_not_copied(self):
        """`repo` is not a context field — only `repository` is exported."""
        sink = DashboardSink(dashboard_url=None)
        from types import SimpleNamespace

        record = {
            "time": SimpleNamespace(timestamp=lambda: 1_700_000_000.0),
            "level": SimpleNamespace(name="INFO"),
            "message": "hello",
            "name": "m",
            "function": "f",
            "line": 1,
            "extra": {
                "repo": "legacy-only",
                "repository": "canonical/org",
            },
        }

        with patch("pr_agent.log.job_context.JobContext.get_current_step", return_value=None):
            entry = sink._format_log_entry(record)

        assert entry.get("repository") == "canonical/org"
        assert entry.get("repo") is None
