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
        
        # Filter 2: Terminate if [nobots] or [no_bots] is found anywhere in description
        if filters.get("terminate_on_no_bots", False):
            # Case-insensitive matching for [nobots] or [no_bots]
            if re.search(r'\[no[_]?bots\]', pr_description, re.IGNORECASE):
                get_logger().info("PR filter: [nobots] found, terminating entire job")
                return PRFilterResult(
                    should_terminate=True,
                    reason="[nobots] found in PR description, terminating entire job"
                )
        
        # Filter 3: Terminate if PR is too large (too many lines changed)
        max_lines = filters.get("max_lines_changed", 0)
        if max_lines > 0:
            try:
                total_lines = calculate_total_lines_changed(git_provider)
                get_logger().debug(f"PR size check: {total_lines} lines changed (limit: {max_lines})")
                if total_lines > max_lines:
                    get_logger().info(f"PR filter: Too large ({total_lines} > {max_lines}), terminating")

                    # Add a comment to inform the user about the size limit
                    try:
                        comment_body = f"This PR is too large for automated analysis. The maximum allowed diff size is {max_lines} lines (this PR has {total_lines} lines changed)."
                        git_provider.publish_comment(comment_body)
                        get_logger().info("Posted size limit comment to PR")
                    except Exception as comment_error:
                        get_logger().warning(f"Failed to post size limit comment: {comment_error}")
                        # Continue with termination even if comment posting fails

                    return PRFilterResult(
                        should_terminate=True,
                        reason=f"PR too large ({total_lines} lines changed > {max_lines} limit), terminating entire job"
                    )
            except Exception as e:
                get_logger().error(f"Failed to calculate PR line count for filtering: {e}")
                # If we can't calculate line count, we should be conservative and terminate
                return PRFilterResult(
                    should_terminate=True,
                    reason=f"Failed to calculate PR size for filtering: {e}"
                )

        # Filter 4: Skip all tools if PR-Agent has already processed this PR
        if filters.get("skip_if_review_suggestions_exist", False):
            try:
                has_existing_comments = check_for_existing_pr_agent_comments(git_provider)
                get_logger().debug(f"Existing PR-Agent comments check: {has_existing_comments}")
                if has_existing_comments:
                    get_logger().info(f"PR filter: PR-Agent has already processed this PR, skipping {command}")
                    return PRFilterResult(
                        should_skip=True,
                        reason=f"PR-Agent has already processed this PR, skipping {command} command"
                    )
            except Exception as e:
                get_logger().error(f"Failed to check for existing PR-Agent comments: {e}")
                # If we can't check, we should be conservative and skip
                return PRFilterResult(
                    should_skip=True,
                    reason=f"Failed to check for existing PR-Agent comments: {e}"
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
        # Case-insensitive matching for [nobots] or [no_bots]
        if re.search(r'\[no[_]?bots\]', pr_description, re.IGNORECASE):
            return True, "[nobots] found in PR description, terminating entire job"
    except Exception as e:
        get_logger().warning(f"Failed to check PR description for termination: {e}")
    
    return False, ""


def check_for_existing_pr_agent_comments(git_provider: GitProvider) -> bool:
    """
    Check if PR already has PR-Agent generated comments (reviews, suggestions, descriptions, etc.)

    Looks for any PR-Agent generated content by checking for known patterns.
    The primary trigger is any comment containing "PR Reviewer Guide" (case insensitive).
    If present, it means PR-Agent has already processed this PR at least once.

    Args:
        git_provider: Git provider instance to access PR data

    Returns:
        True if any PR-Agent generated content already exists
    """
    try:
        comments = list(git_provider.get_issue_comments())

        for comment in comments:
            comment_body = comment.body if hasattr(comment, 'body') else str(comment)
            if not comment_body:
                continue

            # Primary check: Any comment containing "PR Reviewer Guide" (case insensitive)
            try:
                if "pr reviewer guide" in comment_body.lower():
                    get_logger().debug(f"Found existing PR-Agent review guide in comment: {comment_body[:100]}...")
                    return True
            except (UnicodeDecodeError, UnicodeEncodeError):
                try:
                    if "pr reviewer guide" in str(comment_body).lower():
                        get_logger().debug(f"Found existing PR-Agent review guide in comment (encoding fallback): {str(comment_body)[:100]}...")
                        return True
                except Exception:
                    continue

            # Additional patterns for completeness
            pr_agent_patterns = [
                "No suggestions found to improve this PR",
                "No code suggestions found for the PR",
                "Failed to generate code suggestions",
                "## PR Code Suggestions ✨",
                "## PR Agent Walkthrough 🤖",
                "## PR Labels:",
            ]

            for pattern in pr_agent_patterns:
                try:
                    if pattern in comment_body:
                        get_logger().debug(f"Found existing PR-Agent content pattern: {pattern}")
                        return True
                except (UnicodeDecodeError, UnicodeEncodeError):
                    try:
                        if pattern in str(comment_body):
                            get_logger().debug(f"Found existing PR-Agent content pattern (encoding fallback): {pattern}")
                            return True
                    except Exception:
                        continue

        return False

    except Exception as e:
        get_logger().warning(f"Failed to check for existing PR-Agent comments: {e}")
        return False


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
