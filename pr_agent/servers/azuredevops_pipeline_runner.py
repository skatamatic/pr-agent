import asyncio
import json
import os
from typing import Union

from pr_agent.agent.pr_agent import PRAgent
from pr_agent.algo.pr_filters import check_pr_filters
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
        setup_dashboard_integration, update_job_status
    )
    DASHBOARD_AVAILABLE = True
except ImportError:
    DASHBOARD_AVAILABLE = False


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

    # Apply PR filters before processing
    try:
        git_provider = get_git_provider(pr_url)
        # Determine which commands will be run to pass appropriate command context
        commands_to_run = []
        if auto_describe is None or is_true(auto_describe):
            commands_to_run.append("describe")
        if auto_review is None or is_true(auto_review):
            commands_to_run.append("review")
        if auto_improve is None or is_true(auto_improve):
            commands_to_run.append("improve")

        # Track skipped operations for dashboard signaling
        skipped_operations = []

        # Check filters for each command that will be run
        for command in commands_to_run[:]:
            filter_result = check_pr_filters(git_provider, command)

            if filter_result.should_terminate:
                get_logger().error(f"PR filter triggered termination: {filter_result.reason}")
                return
            elif filter_result.should_skip:
                get_logger().info(f"PR filter triggered skip for {command}: {filter_result.reason}")
                # Track skipped operation for later dashboard signaling
                skipped_operations.append({
                    'command': command,
                    'reason': filter_result.reason
                })
                # Remove the skipped command from the list
                if command in commands_to_run:
                    commands_to_run.remove(command)

        # If all commands were skipped, exit early
        if not commands_to_run:
            get_logger().info("All commands skipped by PR filters")
            try:
                if DASHBOARD_AVAILABLE and dashboard_enabled:
                    from pr_agent.log.job_context import job_context, JobType, operation_context, OperationType, update_operation_status, update_job_status
                    # Create minimal job context for skipped operations
                    with job_context(
                        job_type=JobType.WEBHOOK,
                        source="azuredevops_pipeline",
                        repository=repository,
                        pr_url=pr_url,
                        trigger_event="pullrequest"
                    ) as job_id:
                        # Create skipped operations
                        for skipped_op in skipped_operations:
                            if skipped_op['command'] == "review":
                                op_type = OperationType.REVIEW
                            elif skipped_op['command'] == "improve":
                                op_type = OperationType.IMPROVE
                            elif skipped_op['command'] == "describe":
                                op_type = OperationType.DESCRIBE
                            else:
                                op_type = OperationType.STARTING
                            with operation_context(operation_type=op_type, command=skipped_op['command'], repo=repository, pr_url=pr_url):
                                update_operation_status('skipped', result_data={ 'reason': skipped_op['reason'] })
                        # Mark job as skipped
                        update_job_status('skipped', result_summary={ 'reason': 'All commands skipped by PR filters' })
            except Exception as e:
                get_logger().debug(f"Failed to signal skipped operations/job: {e}")
            return
            
    except Exception as e:
        get_logger().error(f"Failed to apply PR filters, terminating for safety: {e}")
        return

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
                                        get_logger().info(f"Setting final job status: {final_status}")
                                        update_job_status(final_status, error_details=error_details, result_summary=result_summary)
                                        
                                        # Wait for all pending dashboard operations to complete
                                        get_logger().debug("Waiting for pending dashboard operations to complete...")
                                        from pr_agent.log.job_context import wait_for_pending_tasks
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
            await run_action()
        finally:
            # CRITICAL: Ensure all dashboard operations complete before exit
            if DASHBOARD_AVAILABLE:
                try:
                    get_logger().info("Starting final dashboard cleanup and sync...")
                    
                    # First, wait for any remaining pending tasks
                    from pr_agent.log.job_context import wait_for_pending_tasks, cleanup_all_dashboard_tasks
                    await wait_for_pending_tasks(timeout=15.0)
                    get_logger().debug("Final pending tasks completed")
                    
                    # Then perform full cleanup
                    await cleanup_all_dashboard_tasks()
                    get_logger().info("Dashboard cleanup completed successfully")
                    
                except Exception as e:
                    get_logger().error(f"Dashboard cleanup error: {e}")  # Log as error since this is critical
                    # Try once more with shorter timeout
                    try:
                        await wait_for_pending_tasks(timeout=5.0)
                        get_logger().debug("Emergency cleanup completed")
                    except Exception as e2:
                        get_logger().error(f"Emergency cleanup failed: {e2}")
    
    asyncio.run(main()) 