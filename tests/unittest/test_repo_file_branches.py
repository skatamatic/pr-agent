"""Tests for repo config file branch resolution."""
from unittest.mock import MagicMock, patch

import pytest

from pr_agent.algo.utils import (
    _dedupe_branch_names,
    fetch_repo_file_content,
    resolve_repo_file_branches,
)


class TestDedupeBranchNames:
    def test_removes_duplicates_and_empty(self):
        assert _dedupe_branch_names(["master", "", "main", "master", "  ", "main"]) == [
            "master",
            "main",
        ]


class TestResolveRepoFileBranches:
    @patch("pr_agent.config_loader.get_settings")
    def test_master_default_repo_order(self, mock_get_settings):
        mock_get_settings.return_value.config.get.return_value = ""

        provider = MagicMock()
        provider.get_pr_branch.return_value = "feature/foo"
        provider.get_pr_target_branch.return_value = "master"
        provider.get_repo_default_branch.return_value = "master"

        branches = resolve_repo_file_branches(provider)
        assert branches.index("feature/foo") < branches.index("master")
        assert "main" in branches
        assert branches.count("master") == 1

    @patch("pr_agent.config_loader.get_settings")
    def test_configured_branch_first(self, mock_get_settings):
        mock_get_settings.return_value.config.get.return_value = "release"

        provider = MagicMock()
        provider.get_pr_branch.return_value = "feature/foo"
        provider.get_pr_target_branch.return_value = "master"
        provider.get_repo_default_branch.return_value = "master"

        branches = resolve_repo_file_branches(provider)
        assert branches[0] == "release"

    @patch("pr_agent.config_loader.get_settings")
    def test_extra_branch_after_configured(self, mock_get_settings):
        mock_get_settings.return_value.config.get.return_value = "release"

        provider = MagicMock()
        provider.get_pr_branch.return_value = "feature/foo"
        provider.get_pr_target_branch.return_value = "master"
        provider.get_repo_default_branch.return_value = "master"

        branches = resolve_repo_file_branches(provider, extra_branch="hotfix")
        assert branches[:2] == ["release", "hotfix"]

    @patch("pr_agent.config_loader.get_settings")
    def test_fallback_when_provider_methods_missing(self, mock_get_settings):
        mock_get_settings.return_value.config.get.return_value = ""

        provider = MagicMock(spec=[])
        branches = resolve_repo_file_branches(provider)
        assert branches == ["main", "master", "develop"]


class TestFetchRepoFileContent:
    @patch("pr_agent.algo.utils.resolve_repo_file_branches")
    def test_returns_first_non_empty_content(self, mock_resolve):
        mock_resolve.return_value = ["feature", "master", "main"]

        provider = MagicMock()
        provider.get_pr_file_content.side_effect = ["", "toml-content", "other"]

        content = fetch_repo_file_content(provider, ".pr_agent.toml")
        assert content == "toml-content"
        provider.get_pr_file_content.assert_any_call(".pr_agent.toml", "master")

    @patch("pr_agent.algo.utils.resolve_repo_file_branches")
    def test_returns_empty_when_not_found(self, mock_resolve):
        mock_resolve.return_value = ["master", "main"]

        provider = MagicMock()
        provider.get_pr_file_content.return_value = ""

        assert fetch_repo_file_content(provider, "best_practices.md") == ""
