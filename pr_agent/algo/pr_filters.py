"""
PR Filtering Utilities
Provides filtering logic to prevent pr-agent from running in specific scenarios
"""
import re
from typing import Tuple, Optional
from pr_agent.config_loader import get_settings
from pr_agent.log import get_logger
from pr_agent.git_providers.git_provider import GitProvider


class PRFilterResult:
    """Result of PR filtering checks"""
    def __init__(self, should_skip: bool = False, should_terminate: bool = False, reason: str = ""):
        self.should_skip = should_skip
        self.should_terminate = should_terminate
        self.reason = reason


def check_pr_filters(git_provider: GitProvider, command: str = None) -> PRFilterResult:
    """
    Check all PR filters and return whether to skip or terminate the job
    
    Args:
        git_provider: Git provider instance to access PR data
        command: The command being executed (e.g., "describe", "review", etc.)
        
    Returns:
        PRFilterResult indicating whether to skip, terminate, and the reason
    """
    try:
        settings = get_settings()
        filters = settings.get("pr_filters", {})
        
        # Check if filters are enabled
        if not filters:
            get_logger().debug("No PR filters configured, skipping filter checks")
            return PRFilterResult()
        
        get_logger().debug(f"Applying PR filters for command: {command}")
        
        # Get PR description
        try:
            pr_description = git_provider.get_pr_description_full() or ""
            get_logger().debug(f"Retrieved PR description (length: {len(pr_description)})")
        except Exception as e:
            get_logger().error(f"Failed to get PR description for filtering: {e}")
            # If we can't get the description, we can't apply filters safely
            return PRFilterResult(
                should_terminate=True,
                reason=f"Failed to retrieve PR description for filtering: {e}"
            )
    
        # Filter 1: Skip if description already exists and we're running describe command
        if (filters.get("skip_if_description_exists", False) and 
            command and command.lower() == "describe" and 
            pr_description and pr_description.strip()):
            get_logger().info("PR filter: Description exists, skipping describe command")
            return PRFilterResult(
                should_skip=True,
                reason="PR description already exists, skipping description generation"
            )
        
        # Filter 2: Terminate if [no_bots] is found anywhere in description
        if filters.get("terminate_on_no_bots", False):
            # Case-insensitive, whitespace-tolerant matching for [no_bots]
            if re.search(r'\[no_bots\]', pr_description, re.IGNORECASE):
                get_logger().info("PR filter: [no_bots] found, terminating entire job")
                return PRFilterResult(
                    should_terminate=True,
                    reason="[no_bots] found in PR description, terminating entire job"
                )
        
        # Filter 3: Skip if PR is too large (too many lines changed)
        max_lines = filters.get("max_lines_changed", 0)
        if max_lines > 0:
            try:
                total_lines = calculate_total_lines_changed(git_provider)
                get_logger().debug(f"PR size check: {total_lines} lines changed (limit: {max_lines})")
                if total_lines > max_lines:
                    get_logger().info(f"PR filter: Too large ({total_lines} > {max_lines}), skipping")
                    return PRFilterResult(
                        should_skip=True,
                        reason=f"PR too large ({total_lines} lines changed > {max_lines} limit), skipping"
                    )
            except Exception as e:
                get_logger().error(f"Failed to calculate PR line count for filtering: {e}")
                # If we can't calculate line count, we should be conservative and skip
                return PRFilterResult(
                    should_skip=True,
                    reason=f"Failed to calculate PR size for filtering: {e}"
                )
        
        get_logger().debug("All PR filters passed")
        return PRFilterResult()
        
    except Exception as e:
        get_logger().error(f"Critical error in PR filter processing: {e}")
        # If there's a critical error in filter processing, terminate to be safe
        return PRFilterResult(
            should_terminate=True,
            reason=f"Critical error in PR filter processing: {e}"
        )


def calculate_total_lines_changed(git_provider: GitProvider) -> int:
    """
    Calculate total lines changed in a PR (added + deleted lines)
    
    Args:
        git_provider: Git provider instance to access PR data
        
    Returns:
        Total number of lines changed (added + deleted)
    """
    try:
        diff_files = git_provider.get_diff_files()
        total_lines = 0
        
        for file_info in diff_files:
            # Count added lines (lines starting with +)
            added_lines = file_info.num_plus_lines if file_info.num_plus_lines > 0 else 0
            # Count deleted lines (lines starting with -)
            deleted_lines = file_info.num_minus_lines if file_info.num_minus_lines > 0 else 0
            
            total_lines += added_lines + deleted_lines
        
        get_logger().debug(f"Calculated total lines changed: {total_lines}")
        return total_lines
        
    except Exception as e:
        get_logger().error(f"Error calculating total lines changed: {e}")
        return 0


def should_skip_description_generation(git_provider: GitProvider) -> bool:
    """
    Check if PR description generation should be skipped
    
    Args:
        git_provider: Git provider instance to access PR data
        
    Returns:
        True if description generation should be skipped
    """
    settings = get_settings()
    filters = settings.get("pr_filters", {})
    
    if not filters.get("skip_if_description_exists", False):
        return False
    
    try:
        pr_description = git_provider.get_pr_description_full() or ""
        return bool(pr_description and pr_description.strip())
    except Exception as e:
        get_logger().warning(f"Failed to check PR description for skipping: {e}")
        return False


def should_terminate_job(git_provider: GitProvider) -> Tuple[bool, str]:
    """
    Check if the entire job should be terminated
    
    Args:
        git_provider: Git provider instance to access PR data
        
    Returns:
        Tuple of (should_terminate, reason)
    """
    settings = get_settings()
    filters = settings.get("pr_filters", {})
    
    if not filters.get("terminate_on_no_bots", False):
        return False, ""
    
    try:
        pr_description = git_provider.get_pr_description_full() or ""
        # Case-insensitive, whitespace-tolerant matching for [no_bots]
        if re.search(r'\[no_bots\]', pr_description, re.IGNORECASE):
            return True, "[no_bots] found in PR description, terminating entire job"
    except Exception as e:
        get_logger().warning(f"Failed to check PR description for termination: {e}")
    
    return False, ""


def should_skip_large_pr(git_provider: GitProvider) -> Tuple[bool, str]:
    """
    Check if PR should be skipped due to size
    
    Args:
        git_provider: Git provider instance to access PR data
        
    Returns:
        Tuple of (should_skip, reason)
    """
    settings = get_settings()
    filters = settings.get("pr_filters", {})
    
    max_lines = filters.get("max_lines_changed", 0)
    if max_lines <= 0:
        return False, ""
    
    try:
        total_lines = calculate_total_lines_changed(git_provider)
        if total_lines > max_lines:
            return True, f"PR too large ({total_lines} lines changed > {max_lines} limit), skipping"
    except Exception as e:
        get_logger().warning(f"Failed to check PR size for skipping: {e}")
    
    return False, ""
