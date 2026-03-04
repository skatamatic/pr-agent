"""
Tests that azure-pipelines-pr-agent.yml includes required env vars for dashboard integration.

Ensures DASHBOARD_URL and DASHBOARD_API_KEY are present in the Execute PR-Agent step
so that pipeline runners can report jobs/operations/logs to the dashboard.
"""
import os

import yaml
import pytest


# Repo root (parent of tests/)
REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
PIPELINE_PATH = os.path.join(REPO_ROOT, "azure-pipelines-pr-agent.yml")


def _load_pipeline():
    with open(PIPELINE_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _find_execute_pr_agent_step(pipeline):
    """Find the step with displayName 'Execute PR‑Agent' (or similar)."""
    for stage in pipeline.get("stages", []):
        for job in stage.get("jobs", []):
            for step in job.get("steps", []):
                if step.get("displayName") == "Execute PR‑Agent":
                    return step
    return None


class TestAzurePipelineYaml:
    """Validate azure-pipelines-pr-agent.yml structure and env."""

    def test_pipeline_file_exists(self):
        assert os.path.isfile(PIPELINE_PATH), f"Pipeline file not found: {PIPELINE_PATH}"

    def test_execute_pr_agent_step_has_dashboard_url_in_env(self):
        """Execute PR-Agent step must pass DASHBOARD_URL so runners can report to dashboard."""
        pipeline = _load_pipeline()
        step = _find_execute_pr_agent_step(pipeline)
        assert step is not None, "Step 'Execute PR‑Agent' not found in pipeline"
        env = step.get("env") or {}
        assert "DASHBOARD_URL" in env, (
            "DASHBOARD_URL must be in the Execute PR‑Agent step env so pipeline runners "
            "can report jobs/operations/logs to the dashboard. Add: DASHBOARD_URL: $(DASHBOARD_URL)"
        )
        assert env.get("DASHBOARD_URL") == "$(DASHBOARD_URL)", (
            "DASHBOARD_URL should be set from pipeline variable: $(DASHBOARD_URL)"
        )

    def test_execute_pr_agent_step_has_dashboard_api_key_in_env(self):
        """Execute PR-Agent step should pass DASHBOARD_API_KEY for optional dashboard auth."""
        pipeline = _load_pipeline()
        step = _find_execute_pr_agent_step(pipeline)
        assert step is not None, "Step 'Execute PR‑Agent' not found in pipeline"
        env = step.get("env") or {}
        assert "DASHBOARD_API_KEY" in env, (
            "DASHBOARD_API_KEY should be in the Execute PR‑Agent step env for optional dashboard API key. "
            "Add: DASHBOARD_API_KEY: $(DASHBOARD_API_KEY)"
        )
