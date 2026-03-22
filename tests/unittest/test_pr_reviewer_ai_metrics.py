"""PR Reviewer dashboard metrics: aggregate send, not per successful AI step."""
import os
from unittest.mock import MagicMock, patch

# Allow importing pr_agent git providers without full Dynaconf github.* keys in minimal test envs
os.environ.setdefault("GITHUB__RATELIMIT_RETRIES", "5")


def test_send_aggregated_ai_metrics_calls_multi_model_once():
    from pr_agent.tools import pr_reviewer as pr_mod

    with patch.object(pr_mod, "update_operation_multi_model_ai_metrics") as multi:
        with patch.object(pr_mod, "DASHBOARD_INTEGRATION_AVAILABLE", True):
            reviewer = MagicMock()
            reviewer.ai_models_metrics = {"gpt-4": {"input_tokens": 10, "output_tokens": 20}}
            pr_mod.PRReviewer._send_aggregated_ai_metrics(reviewer, 1.5)
            multi.assert_called_once_with(
                {"gpt-4": {"input_tokens": 10, "output_tokens": 20}},
                1.5,
            )


def test_send_aggregated_skips_when_no_metrics():
    from pr_agent.tools import pr_reviewer as pr_mod

    with patch.object(pr_mod, "update_operation_multi_model_ai_metrics") as multi:
        with patch.object(pr_mod, "DASHBOARD_INTEGRATION_AVAILABLE", True):
            reviewer = MagicMock()
            reviewer.ai_models_metrics = {}
            pr_mod.PRReviewer._send_aggregated_ai_metrics(reviewer, 1.0)
            multi.assert_not_called()
