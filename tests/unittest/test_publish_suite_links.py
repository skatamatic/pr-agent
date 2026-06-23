import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(
    0,
    str(
        Path(__file__).resolve().parents[2]
        / ".cursor/skills/publish-docs-to-confluence/scripts"
    ),
)

import publish_suite as ps  # noqa: E402


class TestIsLinkableRepoPath(unittest.TestCase):
    def test_api_ellipsis_not_linkable(self):
        for path in (
            ".../sync-status",
            ".../template",
            ".../env-vars",
            ".../policies/{policy_id}",
            "/api/repositories/{id}/azure-pipeline-config",
        ):
            with self.subTest(path=path):
                self.assertTrue(ps.is_api_route_shorthand(path))
                self.assertFalse(ps.is_linkable_repo_path(path))

    def test_real_repo_paths_still_linkable(self):
        for path in (
            "dashboard/backend/main.py",
            "pr_agent/algo/utils.py",
            "terraform/gcp/",
            "deployment.md",
        ):
            with self.subTest(path=path):
                self.assertTrue(ps.is_linkable_repo_path(path))

    def test_inline_api_table_cell_not_wired(self):
        line = "| GET | `.../sync-status`, `.../template`, `.../env-vars` |"
        github = ps.GitHubLinkConfig(
            repo_url="https://github.com/skatamatic/pr-agent",
            ref="develop",
        )
        out, wired = ps.rewrite_inline_repo_paths(
            line,
            github,
            "technical/dashboard-api/repositories.md",
        )
        self.assertEqual(out, line)
        self.assertEqual(wired, [])


class TestGitHubPathVerifier(unittest.TestCase):
    def test_exists_caches_404(self):
        github = ps.GitHubLinkConfig(
            repo_url="https://github.com/skatamatic/pr-agent",
            ref="develop",
        )
        verifier = ps.GitHubPathVerifier(config=github, enabled=True)

        with patch("urllib.request.urlopen") as urlopen:
            urlopen.side_effect = ps.urllib.error.HTTPError(
                "https://api.github.com/", 404, "Not Found", {}, None
            )
            self.assertFalse(
                verifier.exists("docs/suite/technical/dashboard-api/.../sync-status")
            )
            self.assertFalse(
                verifier.exists("docs/suite/technical/dashboard-api/.../sync-status")
            )
            urlopen.assert_called_once()

    def test_exists_true_on_success(self):
        github = ps.GitHubLinkConfig(
            repo_url="https://github.com/skatamatic/pr-agent",
            ref="develop",
        )
        verifier = ps.GitHubPathVerifier(config=github, enabled=True)
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        with patch("urllib.request.urlopen", return_value=mock_resp):
            self.assertTrue(verifier.exists("pr_agent/algo/utils.py"))


if __name__ == "__main__":
    unittest.main()
