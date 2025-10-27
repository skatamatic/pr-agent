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
from pr_agent.servers.github_app import handle_line_comments
from pr_agent.tools.pr_code_suggestions import PRCodeSuggestions
from pr_agent.tools.pr_description import PRDescription
from pr_agent.tools.pr_reviewer import PRReviewer

# Dashboard integration imports
try:
    from pr_agent.log.job_context import (
        job_context,
        JobType,
        extract_repository_from_url,
        setup_dashboard_integration,
        update_job_status,
        operation_context,
        OperationType,
        update_operation_status,
        wait_for_pending_tasks,
        cleanup_all_dashboard_tasks,
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


def get_setting_or_env(key: str, default: Union[str, bool] = None) -> Union[str, bool]:
    try:
        value = get_settings().get(key, default)
    except AttributeError:  # TBD still need to debug why this happens on GitHub Actions
        value = os.getenv(key, None) or os.getenv(key.upper(), None) or os.getenv(key.lower(), None) or default
    return value


async def run_action():
    # Get environment variables
    GITHUB_EVENT_NAME = os.environ.get('GITHUB_EVENT_NAME')
    GITHUB_EVENT_PATH = os.environ.get('GITHUB_EVENT_PATH')
    OPENAI_KEY = os.environ.get('OPENAI_KEY') or os.environ.get('OPENAI.KEY')
    OPENAI_ORG = os.environ.get('OPENAI_ORG') or os.environ.get('OPENAI.ORG')
    GITHUB_TOKEN = os.environ.get('GITHUB_TOKEN')
    # get_settings().set("CONFIG.PUBLISH_OUTPUT_PROGRESS", False)
    
    # Setup dashboard integration (error resilient)
    dashboard_enabled = False
    if DASHBOARD_AVAILABLE:
        try:
            dashboard_enabled = setup_dashboard_integration()
            get_logger().info(f"GitHub Action execution starting - Dashboard integration: {'enabled' if dashboard_enabled else 'disabled'}")
        except Exception as e:
            get_logger().debug(f"Dashboard setup failed: {e}")

    # Check if required environment variables are set
    if not GITHUB_EVENT_NAME:
        print("GITHUB_EVENT_NAME not set")
        return
    if not GITHUB_EVENT_PATH:
        print("GITHUB_EVENT_PATH not set")
        return
    if not GITHUB_TOKEN:
        print("GITHUB_TOKEN not set")
        return

    # Set the environment variables in the settings
    if OPENAI_KEY:
        get_settings().set("OPENAI.KEY", OPENAI_KEY)
    else:
        # Might not be set if the user is using models not from OpenAI
        print("OPENAI_KEY not set")
    if OPENAI_ORG:
        get_settings().set("OPENAI.ORG", OPENAI_ORG)
    get_settings().set("GITHUB.USER_TOKEN", GITHUB_TOKEN)
    get_settings().set("GITHUB.DEPLOYMENT_TYPE", "user")
    enable_output = get_setting_or_env("GITHUB_ACTION_CONFIG.ENABLE_OUTPUT", True)
    get_settings().set("GITHUB_ACTION_CONFIG.ENABLE_OUTPUT", enable_output)

    # Load the event payload
    try:
        with open(GITHUB_EVENT_PATH, 'r') as f:
            event_payload = json.load(f)
    except json.decoder.JSONDecodeError as e:
        print(f"Failed to parse JSON: {e}")
        return

    try:
        get_logger().info("Applying repo settings")
        pr_url = event_payload.get("pull_request", {}).get("html_url")
        if pr_url:
            apply_repo_settings(pr_url)
            get_logger().info(f"enable_custom_labels: {get_settings().config.enable_custom_labels}")
    except Exception as e:
        get_logger().info(f"github action: failed to apply repo settings: {e}")

    # Handle pull request opened event
    if GITHUB_EVENT_NAME == "pull_request" or GITHUB_EVENT_NAME == "pull_request_target":
        action = event_payload.get("action")

        # Retrieve the list of actions from the configuration
        pr_actions = get_settings().get("GITHUB_ACTION_CONFIG.PR_ACTIONS", ["opened", "reopened", "ready_for_review", "review_requested"])

        if action in pr_actions:
            pr_url = event_payload.get("pull_request", {}).get("html_url")
            
            # Guard: Skip PRs created by PR Agent Dashboard
            pr_description = event_payload.get("pull_request", {}).get("body", "") or ""
            if "This PR was created automatically via PR Agent Dashboard" in pr_description:
                get_logger().info(f"Skipping GitHub Action processing - PR was created by PR Agent Dashboard: {pr_url}")
                return
            
            if pr_url:
                # legacy - supporting both GITHUB_ACTION and GITHUB_ACTION_CONFIG
                auto_review = get_setting_or_env("GITHUB_ACTION.AUTO_REVIEW", None)
                if auto_review is None:
                    auto_review = get_setting_or_env("GITHUB_ACTION_CONFIG.AUTO_REVIEW", None)
                auto_describe = get_setting_or_env("GITHUB_ACTION.AUTO_DESCRIBE", None)
                if auto_describe is None:
                    auto_describe = get_setting_or_env("GITHUB_ACTION_CONFIG.AUTO_DESCRIBE", None)
                auto_improve = get_setting_or_env("GITHUB_ACTION.AUTO_IMPROVE", None)
                if auto_improve is None:
                    auto_improve = get_setting_or_env("GITHUB_ACTION_CONFIG.AUTO_IMPROVE", None)

                # Extract repository for dashboard tracking (needed for filter processing)
                repository = None
                if DASHBOARD_AVAILABLE:
                    try:
                        repository = extract_repository_from_url(pr_url)
                        if repository:
                            get_logger().debug(f"Extracted repository: {repository}")
                    except Exception as e:
                        get_logger().debug(f"Failed to extract repository from URL: {e}")

                # Apply PR filters before processing
                try:
                    git_provider = get_git_provider()(pr_url=pr_url)
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
                                # Create minimal job context for skipped operations
                                with job_context(
                                    job_type=JobType.WEBHOOK,
                                    source="github_action",
                                    repository=repository,
                                    pr_url=pr_url,
                                    trigger_event=f"pull_request_{action}"
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
                                # Mark job as skipped and wait for completion
                                update_job_status('skipped', result_summary={ 'reason': 'All commands skipped by PR filters' })
                                # Ensure dashboard updates are processed before exiting
                                try:
                                    loop = asyncio.get_event_loop()
                                    if loop.is_running():
                                        # Wait for any pending dashboard tasks to complete
                                        loop.run_until_complete(wait_for_pending_tasks(timeout=5.0))
                                except Exception as e:
                                    get_logger().debug(f"Failed to wait for dashboard tasks: {e}")
                        except Exception as e:
                            get_logger().debug(f"Failed to signal skipped operations/job: {e}")
                        return

                except Exception as e:
                    get_logger().error(f"Failed to apply PR filters, terminating for safety: {e}")
                    return

                # Set the configuration for auto actions
                get_settings().config.is_auto_command = True # Set the flag to indicate that the command is auto
                get_settings().pr_description.final_update_message = False  # No final update message when auto_describe is enabled
                get_logger().info(f"Running auto actions: auto_describe={auto_describe}, auto_review={auto_review}, auto_improve={auto_improve}")

                # Determine which tools to run - using the FILTERED commands_to_run list
                tools_to_run = []
                if "describe" in commands_to_run:
                    tools_to_run.append(("describe", PRDescription))
                if "review" in commands_to_run:
                    tools_to_run.append(("review", PRReviewer))
                if "improve" in commands_to_run:
                    tools_to_run.append(("improve", PRCodeSuggestions))
                
                get_logger().info(f"Tools to run after filtering: {[tool[0] for tool in tools_to_run]}")

                # Execute all tools within a single job context
                try:
                    # Create job context if dashboard integration is available
                    if DASHBOARD_AVAILABLE and dashboard_enabled:
                        try:
                            with job_context(
                                job_type=JobType.WEBHOOK,
                                source="github_action",
                                repository=repository,
                                pr_url=pr_url,
                                trigger_event=f"pull_request_{action}",
                                request_id=f"gh-action-{action}-{os.getpid()}"
                            ) as job_id:
                                get_logger().info(f"GitHub Action job started with ID: {job_id} - Running tools: {[tool[0] for tool in tools_to_run]}")
                                
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
                                            get_logger().debug(f"Executing {tool_name} tool ({i+1}/{len(tools_to_run)})")
                                            await tool_class(pr_url).run()
                                            completed_tools.append(tool_name)
                                            get_logger().debug(f"Successfully completed {tool_name} tool")
                                        except Exception as e:
                                            get_logger().error(f"Failed to run {tool_name} tool: {e}")
                                            # Continue with other tools but track the failure
                                            completed_tools.append(f"{tool_name}(failed)")
                                    
                                    # All tools completed (some may have failed individually)
                                    final_status = "completed"
                                    result_summary = {
                                        "action": action, 
                                        "tools_executed": completed_tools,
                                        "success": True
                                    }
                                    get_logger().info(f"GitHub Action job {job_id} completed successfully")
                                    
                                except Exception as e:
                                    # Critical failure that stopped all execution
                                    final_status = "failed"
                                    error_details = str(e)
                                    get_logger().error(f"GitHub Action job {job_id} failed: {e}")
                                    
                                finally:
                                    # CRITICAL: Ensure final status is always set and persisted
                                    try:
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
                                    
                        except Exception as e:
                            get_logger().warning(f"Dashboard job tracking failed, continuing without tracking: {e}")
                            # Fall through to execute without job tracking
                            get_logger().debug("Executing tools without dashboard tracking (fallback mode)")
                            for tool_name, tool_class in tools_to_run:
                                try:
                                    await tool_class(pr_url).run()
                                    get_logger().debug(f"Completed {tool_name} tool without tracking")
                                except Exception as e:
                                    get_logger().error(f"Failed to run {tool_name} tool without tracking: {e}")
                                    # Continue with other tools
                    else:
                        # Execute without job tracking (dashboard disabled)
                        get_logger().debug("Executing tools without dashboard tracking (dashboard disabled)")
                        for tool_name, tool_class in tools_to_run:
                            try:
                                await tool_class(pr_url).run()
                                get_logger().debug(f"Completed {tool_name} tool (dashboard disabled)")
                            except Exception as e:
                                get_logger().error(f"Failed to run {tool_name} tool (dashboard disabled): {e}")
                                # Continue with other tools
                                
                except Exception as e:
                    get_logger().error(f"Failed to execute GitHub Action tools: {e}")
                    # Don't re-raise to allow other event types to be processed
        else:
            get_logger().info(f"Skipping action: {action}")

    # Handle issue comment event
    elif GITHUB_EVENT_NAME == "issue_comment" or GITHUB_EVENT_NAME == "pull_request_review_comment":
        action = event_payload.get("action")
        if action in ["created", "edited"]:
            comment_body = event_payload.get("comment", {}).get("body")
            try:
                if GITHUB_EVENT_NAME == "pull_request_review_comment":
                    if '/ask' in comment_body:
                        comment_body = handle_line_comments(event_payload, comment_body)
            except Exception as e:
                get_logger().error(f"Failed to handle line comments: {e}")
                return
            if comment_body:
                is_pr = False
                disable_eyes = False
                # check if issue is pull request
                if event_payload.get("issue", {}).get("pull_request"):
                    url = event_payload.get("issue", {}).get("pull_request", {}).get("html_url")
                    is_pr = True
                elif event_payload.get("pull_request", {}).get("html_url"):  # for 'pull_request_review_comment'
                    url = event_payload.get("pull_request", {}).get("html_url")
                    is_pr = True
                    disable_eyes = True
                else:
                    url = event_payload.get("issue", {}).get("html_url")

                if url:
                    body = comment_body.strip().lower()
                    comment_id = event_payload.get("comment", {}).get("id")
                    provider = get_git_provider()(pr_url=url)
                    
                    # Extract repository for dashboard tracking
                    repository = None
                    if DASHBOARD_AVAILABLE:
                        try:
                            repository = extract_repository_from_url(url)
                            if repository:
                                get_logger().debug(f"Extracted repository: {repository}")
                        except Exception as e:
                            get_logger().debug(f"Failed to extract repository from URL: {e}")
                    
                    # Execute with dashboard job tracking
                    try:
                        # Create job context if dashboard integration is available
                        if DASHBOARD_AVAILABLE and dashboard_enabled:
                            try:
                                with job_context(
                                    job_type=JobType.WEBHOOK,
                                    source="github_action",
                                    repository=repository,
                                    pr_url=url if is_pr else None,
                                    issue_url=url if not is_pr else None,
                                    trigger_event=f"{GITHUB_EVENT_NAME}_{action}",
                                    request_id=f"gh-action-comment-{action}-{comment_id or os.getpid()}"
                                ) as job_id:
                                    get_logger().info(f"GitHub Action comment job started with ID: {job_id} - Command: {body}")
                                    
                                    final_status = "failed"  # Default to failed, update to completed if successful
                                    error_details = None
                                    result_summary = None
                                    
                                    try:
                                        # Update job status to running
                                        update_job_status("running")
                                        
                                        # Execute the PR-Agent command
                                        result = None
                                        if is_pr:
                                            result = await PRAgent().handle_request(
                                                url, body, notify=lambda: provider.add_eyes_reaction(
                                                    comment_id, disable_eyes=disable_eyes
                                                )
                                            )
                                        else:
                                            result = await PRAgent().handle_request(url, body)
                                        
                                        # Command completed successfully
                                        final_status = "completed"
                                        if result:
                                            result_summary = {"command": body, "success": True}
                                            get_logger().info(f"GitHub Action comment job {job_id} completed successfully")
                                        else:
                                            result_summary = {"command": body, "success": True, "note": "no explicit result"}
                                            get_logger().info(f"GitHub Action comment job {job_id} completed")
                                        
                                    except Exception as e:
                                        # Command failed
                                        final_status = "failed"
                                        error_details = str(e)
                                        get_logger().error(f"GitHub Action comment job {job_id} failed: {e}")
                                        
                                    finally:
                                        # CRITICAL: Ensure final status is always set and persisted
                                        try:
                                            get_logger().info(f"Setting final comment job status: {final_status}")
                                            update_job_status(final_status, error_details=error_details, result_summary=result_summary)
                                            
                                            # Wait for all pending dashboard operations to complete
                                            get_logger().debug("Waiting for pending dashboard operations to complete...")
                                            await wait_for_pending_tasks(timeout=10.0)
                                            get_logger().debug("Dashboard operations completed")
                                            
                                        except Exception as e:
                                            get_logger().error(f"Failed to finalize comment job status: {e}")
                                            # Try one more time with a simpler update
                                            try:
                                                update_job_status("failed", error_details=f"Finalization error: {e}")
                                                await wait_for_pending_tasks(timeout=5.0)
                                            except Exception as e2:
                                                get_logger().error(f"Final fallback status update failed: {e2}")
                                        
                            except Exception as e:
                                get_logger().warning(f"Dashboard job tracking failed for comment, continuing without tracking: {e}")
                                # Fall through to execute without job tracking
                                if is_pr:
                                    await PRAgent().handle_request(
                                        url, body, notify=lambda: provider.add_eyes_reaction(
                                            comment_id, disable_eyes=disable_eyes
                                        )
                                    )
                                else:
                                    await PRAgent().handle_request(url, body)
                        else:
                            # Execute without job tracking (fallback or dashboard disabled)
                            get_logger().info("Executing comment command without dashboard tracking")
                            if is_pr:
                                await PRAgent().handle_request(
                                    url, body, notify=lambda: provider.add_eyes_reaction(
                                        comment_id, disable_eyes=disable_eyes
                                    )
                                )
                            else:
                                await PRAgent().handle_request(url, body)
                                
                    except Exception as e:
                        get_logger().error(f"Failed to handle comment command: {e}")
                        raise


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
