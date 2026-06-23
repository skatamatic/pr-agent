"""
Git utility functions for the dashboard.
Re-exports branch-aware helpers from pr_agent.
"""
from pr_agent.algo.utils import (  # noqa: F401
    fetch_repo_file_content,
    get_best_practices_content,
    get_pr_agent_config_content,
    resolve_repo_file_branches,
)
