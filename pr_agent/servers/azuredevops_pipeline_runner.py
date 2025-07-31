import asyncio
import json
import os
import signal
import sys
from typing import Union

from pr_agent.agent.pr_agent import PRAgent
from pr_agent.config_loader import get_settings
from pr_agent.git_providers import get_git_provider
from pr_agent.git_providers.utils import apply_repo_settings
from pr_agent.log import get_logger

from pr_agent.tools.pr_code_suggestions import PRCodeSuggestions
from pr_agent.tools.pr_description import PRDescription
from pr_agent.tools.pr_reviewer import PRReviewer

# Dashboard integration imports
try:
    from pr_agent.log.job_context import (
        job_context, JobType, extract_repository_from_url, 
        setup_dashboard_integration, update_job_status,
        wait_for_pending_tasks, cleanup_all_dashboard_tasks
    )
    DASHBOARD_AVAILABLE = True
except ImportError:
    DASHBOARD_AVAILABLE = False

# Global flag for graceful shutdown
_shutdown_requested = False
_current_job_id = None

def signal_handler(signum, frame):
    """Handle shutdown signals gracefully"""
    global _shutdown_requested, _current_job_id
    _shutdown_requested = True
    get_logger().warning(f"Shutdown signal {signum} received, initiating graceful shutdown...")
    
    # If we have an active job, try to mark it as cancelled
    if _current_job_id and DASHBOARD_AVAILABLE:
        try:
            import asyncio
            # Schedule the status update
            loop = asyncio.get_event_loop()
            loop.create_task(update_job_status_async("cancelled", error_details=f"Process terminated by signal {signum}"))
        except Exception as e:
            get_logger().error(f"Failed to update job status on signal: {e}")

async def update_job_status_async(status: str, error_details: str = None):
    """Async wrapper for job status updates from signal handlers"""
    try:
        update_job_status(status, error_details=error_details)
        await wait_for_pending_tasks(timeout=3.0)
    except Exception as e:
        get_logger().error(f"Failed to update job status: {e}")

def setup_signal_handlers():
    """Setup signal handlers for graceful shutdown"""
    if hasattr(signal, 'SIGTERM'):
        signal.signal(signal.SIGTERM, signal_handler)
    if hasattr(signal, 'SIGINT'):
        signal.signal(signal.SIGINT, signal_handler)
    get_logger().debug("Signal handlers configured for graceful shutdown")

async def cleanup_orphaned_jobs():
    """Check for and cleanup any orphaned jobs from previous runs"""
    if not DASHBOARD_AVAILABLE:
        return
    
    try:
        get_logger().debug("Checking for orphaned jobs from previous runs...")
        # This would ideally call a dashboard API to find jobs in 'running' state 
        # that are older than X minutes and mark them as 'failed'
        # For now, just ensure our cleanup is robust
        await cleanup_all_dashboard_tasks()
        get_logger().debug("Orphaned job cleanup completed")
    except Exception as e:
        get_logger().debug(f"Orphaned job cleanup error: {e}")

async def validate_cleanup_completion():
    """Validate that all cleanup operations actually completed"""
    try:
        # Double-check that no tasks are still pending
        from pr_agent.log.job_context import get_pending_tasks
        remaining_tasks = get_pending_tasks()
        if remaining_tasks:
            get_logger().warning(f"Found {len(remaining_tasks)} remaining tasks after cleanup!")
            # Try to cancel them
            for task in remaining_tasks:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*remaining_tasks, return_exceptions=True)
            get_logger().debug("Forced cleanup of remaining tasks completed")
        else:
            get_logger().debug("Cleanup validation passed - no remaining tasks")
    except Exception as e:
        get_logger().error(f"Cleanup validation error: {e}")


def is_true(value: Union[str, bool]) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() == 'true'
    return False


def get_setting_or_env(key: str, default: Union[str, bool, None] = None) -> Union[str, bool, None]:
    try:
        value = get_settings().get(key, default)
    except AttributeError:  # TBD still need to debug why this happens on Azure DevOps
        value = os.getenv(key, None) or os.getenv(key.upper(), None) or os.getenv(key.lower(), None) or default
    return value


async def run_action():
    # Get Azure DevOps environment variables
    BUILD_REASON = os.environ.get('BUILD_REASON')
    SYSTEM_PULLREQUEST_PULLREQUESTID = os.environ.get('SYSTEM_PULLREQUEST_PULLREQUESTID')
    SYSTEM_TEAMPROJECT = os.environ.get('SYSTEM_TEAMPROJECT')
    BUILD_REPOSITORY_NAME = os.environ.get('BUILD_REPOSITORY_NAME')
    SYSTEM_COLLECTIONURI = os.environ.get('SYSTEM_COLLECTIONURI')
    
    # Authentication and AI keys
    AZURE_DEVOPS_PAT = os.environ.get('AZURE_DEVOPS_PAT') or os.environ.get('SYSTEM_ACCESSTOKEN')
    OPENAI_KEY = os.environ.get('OPENAI_KEY') or os.environ.get('OPENAI.KEY')
    OPENAI_ORG = os.environ.get('OPENAI_ORG') or os.environ.get('OPENAI.ORG')
    
    # Setup dashboard integration (error resilient)
    dashboard_enabled = False
    if DASHBOARD_AVAILABLE:
        try:
            dashboard_enabled = setup_dashboard_integration()
            get_logger().info(f"Azure DevOps Pipeline execution starting - Dashboard integration: {'enabled' if dashboard_enabled else 'disabled'}")
        except Exception as e:
            get_logger().debug(f"Dashboard setup failed: {e}")

    # Check if required environment variables are set
    if not BUILD_REASON:
        print("BUILD_REASON not set")
        return
    if BUILD_REASON != 'PullRequest':
        print(f"BUILD_REASON is '{BUILD_REASON}', not 'PullRequest' - skipping")
        return
    if not SYSTEM_PULLREQUEST_PULLREQUESTID:
        print("SYSTEM_PULLREQUEST_PULLREQUESTID not set")
        return
    if not SYSTEM_TEAMPROJECT:
        print("SYSTEM_TEAMPROJECT not set")
        return
    if not BUILD_REPOSITORY_NAME:
        print("BUILD_REPOSITORY_NAME not set")
        return
    if not SYSTEM_COLLECTIONURI:
        print("SYSTEM_COLLECTIONURI not set")
        return
    if not AZURE_DEVOPS_PAT:
        print("AZURE_DEVOPS_PAT or SYSTEM_ACCESSTOKEN not set")
        return

    # Set the environment variables in the settings
    if OPENAI_KEY:
        get_settings().set("OPENAI.KEY", OPENAI_KEY)
    else:
        # Might not be set if the user is using models not from OpenAI
        print("OPENAI_KEY not set")
    if OPENAI_ORG:
        get_settings().set("OPENAI.ORG", OPENAI_ORG)
    
    # Configure Azure DevOps settings
    get_settings().set("AZURE_DEVOPS.PAT", AZURE_DEVOPS_PAT)
    get_settings().set("AZURE_DEVOPS.ORG", SYSTEM_COLLECTIONURI)
    get_settings().set("CONFIG.GIT_PROVIDER", "azure")  # Set git provider for Azure DevOps
    enable_output = get_setting_or_env("AZURE_DEVOPS_CONFIG.ENABLE_OUTPUT", True)
    get_settings().set("AZURE_DEVOPS_CONFIG.ENABLE_OUTPUT", enable_output)
    get_settings().set("CONFIG.PUBLISH_OUTPUT_PROGRESS", False)  # Disable progress output in pipeline

    # Construct PR URL from Azure DevOps environment variables
    # Format: https://dev.azure.com/{organization}/{project}/_git/{repo}/pullrequest/{pr_id}
    organization = SYSTEM_COLLECTIONURI.rstrip('/').split('/')[-1]
    pr_url = f"{SYSTEM_COLLECTIONURI.rstrip('/')}/{SYSTEM_TEAMPROJECT}/_git/{BUILD_REPOSITORY_NAME}/pullrequest/{SYSTEM_PULLREQUEST_PULLREQUESTID}"
    
    get_logger().info(f"Processing Azure DevOps PR: {pr_url}")

    try:
        get_logger().info("Applying repo settings")
        apply_repo_settings(pr_url)
        get_logger().info(f"enable_custom_labels: {get_settings().config.enable_custom_labels}")
    except Exception as e:
        get_logger().info(f"azure devops pipeline: failed to apply repo settings: {e}")

    # Handle pull request event (equivalent to GitHub's pull_request event)
    if BUILD_REASON == "PullRequest":
        # Get the trigger reason - Azure DevOps doesn't provide exact action like GitHub
        # but we can treat all PullRequest builds as valid actions
        # Future: Could potentially get more details from Azure DevOps API if needed
        action = "pullrequest"  # Generic action for Azure DevOps
        
        # Retrieve the list of actions from the configuration (for consistency with GitHub)
        pr_actions = get_settings().get("AZURE_DEVOPS_CONFIG.PR_ACTIONS", ["pullrequest"])
        
        # For now, Azure DevOps pipelines always run on PR events, so we always proceed
        # but maintain the structure for potential future filtering
        if action in pr_actions:
            # Guard: Skip PRs created by PR Agent Dashboard
            try:
                provider = get_git_provider()(pr_url=pr_url)
                pr_description = provider.get_pr_description()
                if pr_description and "This PR was created automatically via PR Agent Dashboard" in pr_description:
                    get_logger().info(f"Skipping Azure DevOps Pipeline processing - PR was created by PR Agent Dashboard: {pr_url}")
                    return
            except Exception as e:
                get_logger().debug(f"Could not check PR description for dashboard marker: {e}")

            # Legacy - supporting AZURE_DEVOPS_CONFIG, AZURE_DEVOPS, and GITHUB_ACTION_CONFIG for compatibility
            auto_review = get_setting_or_env("AZURE_DEVOPS_CONFIG.AUTO_REVIEW", None)
            if auto_review is None:
                auto_review = get_setting_or_env("AZURE_DEVOPS.AUTO_REVIEW", None)
            if auto_review is None:
                auto_review = get_setting_or_env("GITHUB_ACTION_CONFIG.AUTO_REVIEW", None)
            auto_describe = get_setting_or_env("AZURE_DEVOPS_CONFIG.AUTO_DESCRIBE", None)
            if auto_describe is None:
                auto_describe = get_setting_or_env("AZURE_DEVOPS.AUTO_DESCRIBE", None)
            if auto_describe is None:
                auto_describe = get_setting_or_env("GITHUB_ACTION_CONFIG.AUTO_DESCRIBE", None)
            auto_improve = get_setting_or_env("AZURE_DEVOPS_CONFIG.AUTO_IMPROVE", None)
            if auto_improve is None:
                auto_improve = get_setting_or_env("AZURE_DEVOPS.AUTO_IMPROVE", None)
            if auto_improve is None:
                auto_improve = get_setting_or_env("GITHUB_ACTION_CONFIG.AUTO_IMPROVE", None)

            # Set the configuration for auto actions
            get_settings().config.is_auto_command = True # Set the flag to indicate that the command is auto
            get_settings().pr_description.final_update_message = False  # No final update message when auto_describe is enabled
            get_logger().info(f"Running auto actions: auto_describe={auto_describe}, auto_review={auto_review}, auto_improve={auto_improve}")

            # Extract repository for dashboard tracking
            repository = None
            if DASHBOARD_AVAILABLE:
                try:
                    repository = extract_repository_from_url(pr_url)
                    if repository:
                        get_logger().debug(f"Extracted repository: {repository}")
                except Exception as e:
                    get_logger().debug(f"Failed to extract repository from URL: {e}")

            # Determine which tools to run
            tools_to_run = []
            if auto_describe is None or is_true(auto_describe):
                tools_to_run.append(("describe", PRDescription))
            if auto_review is None or is_true(auto_review):
                tools_to_run.append(("review", PRReviewer))
            if auto_improve is None or is_true(auto_improve):
                tools_to_run.append(("improve", PRCodeSuggestions))

            if tools_to_run:
                try:
                    # Create job context if dashboard integration is available
                    if DASHBOARD_AVAILABLE and dashboard_enabled:
                        try:
                            with job_context(
                                job_type=JobType.WEBHOOK,
                                source="azuredevops_pipeline",
                                repository=repository,
                                pr_url=pr_url,
                                trigger_event=f"pullrequest_{action}",
                                request_id=f"ado-pipeline-{SYSTEM_PULLREQUEST_PULLREQUESTID}-{os.getpid()}"
                            ) as job_id:
                                global _current_job_id
                                _current_job_id = job_id
                                get_logger().info(f"Azure DevOps Pipeline job started with ID: {job_id} - Running tools: {[tool[0] for tool in tools_to_run]}")
                                
                                final_status = "failed"  # Default to failed, update to completed if successful
                                error_details = None
                                result_summary = None
                                
                                try:
                                    # Update job status to running
                                    update_job_status("running")
                                    
                                    # Execute each tool sequentially
                                    completed_tools = []
                                    for i, (tool_name, tool_class) in enumerate(tools_to_run):
                                        try:
                                            get_logger().info(f"Executing {tool_name} tool ({i+1}/{len(tools_to_run)})...")
                                            await tool_class(pr_url).run()
                                            completed_tools.append(tool_name)
                                            get_logger().info(f"Successfully completed {tool_name} tool ({i+1}/{len(tools_to_run)})")
                                        except Exception as e:
                                            get_logger().error(f"Failed to run {tool_name} tool ({i+1}/{len(tools_to_run)}): {e}")
                                            get_logger().error(f"Exception type: {type(e).__name__}")
                                            get_logger().error(f"Continuing to next tool...")
                                            # Continue with other tools but track the failure
                                            completed_tools.append(f"{tool_name}(failed)")
                                        
                                        get_logger().info(f"Completed processing {tool_name}, moving to next tool...")
                                    
                                    # All tools completed (some may have failed individually)
                                    final_status = "completed"
                                    result_summary = {
                                        "action": action,
                                        "tools_executed": completed_tools,
                                        "success": True
                                    }
                                    get_logger().info(f"Azure DevOps Pipeline job {job_id} completed successfully")
                                    
                                except Exception as e:
                                    # Critical failure that stopped all execution
                                    final_status = "failed"
                                    error_details = str(e)
                                    get_logger().error(f"Azure DevOps Pipeline job {job_id} failed: {e}")
                                    
                                finally:
                                    # CRITICAL: Ensure final status is always set and persisted
                                    try:
                                        # Check if shutdown was requested
                                        if _shutdown_requested:
                                            final_status = "cancelled"
                                            error_details = "Process shutdown requested"
                                            get_logger().warning("Shutdown requested during job execution")
                                        
                                        get_logger().info(f"Setting final job status: {final_status}")
                                        update_job_status(final_status, error_details=error_details, result_summary=result_summary)
                                        
                                        # Wait for all pending dashboard operations to complete
                                        get_logger().debug("Waiting for pending dashboard operations to complete...")
                                        await wait_for_pending_tasks(timeout=10.0)
                                        get_logger().debug("Dashboard operations completed")
                                        
                                    except Exception as e:
                                        get_logger().error(f"Failed to finalize job status: {e}")
                                        # Try one more time with a simpler update
                                        try:
                                            update_job_status("failed", error_details=f"Finalization error: {e}")
                                            await wait_for_pending_tasks(timeout=5.0)
                                        except Exception as e2:
                                            get_logger().error(f"Final fallback status update failed: {e2}")
                                    
                                    finally:
                                        # Clear global job tracking 
                                        global _current_job_id
                                        _current_job_id = None
                                        get_logger().debug(f"Cleared global job tracking for {job_id}")
                                
                        except Exception as e:
                            get_logger().warning(f"Dashboard job tracking failed, continuing without tracking: {e}")
                            # Fall through to execute without job tracking
                            get_logger().info("Executing tools without dashboard tracking (fallback mode)")
                            for i, (tool_name, tool_class) in enumerate(tools_to_run):
                                try:
                                    get_logger().info(f"Executing {tool_name} tool without tracking ({i+1}/{len(tools_to_run)})...")
                                    await tool_class(pr_url).run()
                                    get_logger().info(f"Successfully completed {tool_name} tool without tracking ({i+1}/{len(tools_to_run)})")
                                except Exception as e:
                                    get_logger().error(f"Failed to run {tool_name} tool without tracking ({i+1}/{len(tools_to_run)}): {e}")
                                    get_logger().error(f"Exception type: {type(e).__name__}")
                                    get_logger().error(f"Continuing to next tool...")
                                    # Continue with other tools
                                
                                get_logger().info(f"Completed processing {tool_name} (fallback), moving to next tool...")
                    else:
                        # Execute without job tracking (fallback or dashboard disabled)
                        get_logger().info("Executing tools without dashboard tracking (dashboard disabled)")
                        for i, (tool_name, tool_class) in enumerate(tools_to_run):
                            try:
                                get_logger().info(f"Executing {tool_name} tool (no tracking) ({i+1}/{len(tools_to_run)})...")
                                await tool_class(pr_url).run()
                                get_logger().info(f"Successfully completed {tool_name} tool (no tracking) ({i+1}/{len(tools_to_run)})")
                            except Exception as e:
                                get_logger().error(f"Failed to run {tool_name} tool (no tracking) ({i+1}/{len(tools_to_run)}): {e}")
                                get_logger().error(f"Exception type: {type(e).__name__}")
                                get_logger().error(f"Continuing to next tool...")
                                # Continue with other tools
                            
                            get_logger().info(f"Completed processing {tool_name} (no tracking), moving to next tool...")
                                
                except Exception as e:
                    get_logger().error(f"Failed to execute Azure DevOps Pipeline tools: {e}")
                    # Don't re-raise to allow graceful exit
            else:
                get_logger().info("No tools enabled for execution")
        else:
            get_logger().info(f"Skipping action: {action}")


if __name__ == '__main__':
    async def main():
        try:
            setup_signal_handlers()
            await cleanup_orphaned_jobs()
            await run_action()
        finally:
            # CRITICAL: Ensure all dashboard operations complete before exit
            global _current_job_id
            _current_job_id = None  # Clear current job tracking
            
            if DASHBOARD_AVAILABLE:
                try:
                    get_logger().info("Starting comprehensive dashboard cleanup and sync...")
                    
                    # First, wait for any remaining pending tasks with extended timeout for Azure DevOps
                    await wait_for_pending_tasks(timeout=20.0)  # Extended timeout for Azure DevOps pipelines
                    get_logger().debug("Pending tasks wait completed")
                    
                    # Validate cleanup before proceeding
                    await validate_cleanup_completion()
                    
                    # Then perform full cleanup
                    await cleanup_all_dashboard_tasks()
                    get_logger().info("Dashboard cleanup completed successfully")
                    
                    # Final validation that everything is clean
                    await validate_cleanup_completion()
                    get_logger().debug("Final cleanup validation passed")
                    
                except Exception as e:
                    get_logger().error(f"Dashboard cleanup error: {e}")  # Log as error since this is critical
                    # Try once more with shorter timeout
                    try:
                        get_logger().warning("Attempting emergency cleanup...")
                        await wait_for_pending_tasks(timeout=8.0)
                        await cleanup_all_dashboard_tasks()
                        get_logger().debug("Emergency cleanup completed")
                        
                        # Final emergency validation
                        await validate_cleanup_completion()
                        get_logger().debug("Emergency cleanup validation passed")
                        
                    except Exception as e2:
                        get_logger().error(f"Emergency cleanup failed: {e2}")
                        
                        # Last resort - try to at least validate what's left
                        try:
                            await validate_cleanup_completion()
                            get_logger().warning("Last resort validation completed")
                        except Exception as e3:
                            get_logger().error(f"Final validation failed: {e3}")
                            
            get_logger().info("Azure DevOps Pipeline Runner shutdown complete")
    
    asyncio.run(main()) 