"""
Git utility functions for the dashboard.
Local copies of functions that may not be available in the installed pr-agent package.
"""
import logging

logger = logging.getLogger(__name__)

def get_best_practices_content(git_provider, branch="main") -> str:
    """
    Load best_practices.md file from the repository root if it exists.
    
    Args:
        git_provider: The git provider instance
        branch: Branch to fetch from (defaults to "main")
        
    Returns:
        str: Content of best_practices.md file, or empty string if not found
    """
    try:
        # Try to get the best practices file from the repo root
        # Use provided branch or try common default branches
        branches_to_try = [branch, "main", "master", "develop"]
        
        # Try to get PR branch if available (only works if git provider has PR context)
        try:
            if hasattr(git_provider, 'get_pr_branch'):
                pr_branch = git_provider.get_pr_branch()
                if pr_branch:
                    branches_to_try.insert(0, pr_branch)
        except Exception as pr_branch_e:
            logger.debug(f"Could not get PR branch (no PR context): {pr_branch_e}")
        
        for branch_name in branches_to_try:
            try:
                best_practices_content = git_provider.get_pr_file_content("best_practices.md", branch_name)
                if best_practices_content and best_practices_content.strip():
                    logger.info(f"Found best_practices.md file in repository root on branch {branch_name}")
                    return best_practices_content.strip()
            except Exception as branch_e:
                logger.debug(f"Could not load best_practices.md from branch {branch_name}: {branch_e}")
                continue
        
        logger.debug("best_practices.md file not found in any branch")
        return ""
    except Exception as e:
        logger.debug(f"Could not load best_practices.md from repository root: {e}")
        return ""


def get_pr_agent_config_content(git_provider, branch="main") -> str:
    """
    Load .pr_agent.toml file from the repository root if it exists.
    
    Args:
        git_provider: The git provider instance
        branch: Branch to fetch from (defaults to "main")
        
    Returns:
        str: Content of .pr_agent.toml file, or empty string if not found
    """
    try:
        # Try to get the PR-Agent config file from the repo root
        # Use provided branch or try common default branches
        branches_to_try = [branch, "main", "master", "develop"]
        
        # Try to get PR branch if available (only works if git provider has PR context)
        try:
            if hasattr(git_provider, 'get_pr_branch'):
                pr_branch = git_provider.get_pr_branch()
                if pr_branch:
                    branches_to_try.insert(0, pr_branch)
        except Exception as pr_branch_e:
            logger.debug(f"Could not get PR branch (no PR context): {pr_branch_e}")
        
        for branch_name in branches_to_try:
            try:
                pr_agent_config_content = git_provider.get_pr_file_content(".pr_agent.toml", branch_name)
                if pr_agent_config_content and pr_agent_config_content.strip():
                    logger.info(f"Found .pr_agent.toml file in repository root on branch {branch_name}")
                    return pr_agent_config_content.strip()
            except Exception as branch_e:
                logger.debug(f"Could not load .pr_agent.toml from branch {branch_name}: {branch_e}")
                continue
        
        logger.debug(".pr_agent.toml file not found in any branch")
        return ""
    except Exception as e:
        logger.debug(f"Could not load .pr_agent.toml from repository root: {e}")
        return "" 