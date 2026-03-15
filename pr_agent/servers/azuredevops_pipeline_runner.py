import asyncio
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


def get_setting_or_env(key: str, default: Union[str, bool, None] = None) -> Union[str, bool, None]:
    try:
        value = get_settings().get(key, default)
    except AttributeError:  # TBD still need to debug why this happens on Azure DevOps
        value = os.getenv(key, None) or os.getenv(key.upper(), None) or os.getenv(key.lower(), None) or default
    return value


def _resolve_pr_repo_name() -> str:
    """Resolve the actual repository where the PR lives.

    In a shared-pipeline / build-validation-policy setup the pipeline YAML
    lives in a *different* repo from the one the PR targets.
    Azure DevOps provides ``System.PullRequest.SourceRepositoryUri`` for
    exactly this case.  ``Build.Repository.Name`` refers to the repository
    that *hosts the pipeline YAML*, which is the wrong one.

    Fallback order:
      1. SYSTEM_PULLREQUEST_SOURCEREPOSITORYURI  (cross-repo build-validation)
      2. BUILD_REPOSITORY_NAME                   (same-repo pipeline)
    """
    source_repo_uri = os.environ.get('SYSTEM_PULLREQUEST_SOURCEREPOSITORYURI', '').strip()
    if source_repo_uri:
        # URI looks like https://dev.azure.com/{org}/{project}/_git/{repo}
        # or https://{org}.visualstudio.com/{project}/_git/{repo}
        parts = source_repo_uri.rstrip('/').split('/')
        try:
            git_idx = parts.index('_git')
            return parts[git_idx + 1]
        except (ValueError, IndexError):
            pass
    return os.environ.get('BUILD_REPOSITORY_NAME', '')


def _resolve_pr_project() -> str:
    """Resolve the Azure DevOps project that owns the PR's repository.

    ``System.PullRequest.SourceRepositoryUri`` encodes the project name,
    which may differ from ``System.TeamProject`` in cross-project
    build-validation scenarios.
    """
    source_repo_uri = os.environ.get('SYSTEM_PULLREQUEST_SOURCEREPOSITORYURI', '').strip()
    if source_repo_uri:
        parts = source_repo_uri.rstrip('/').split('/')
        try:
            git_idx = parts.index('_git')
            if git_idx >= 1:
                return parts[git_idx - 1]
        except (ValueError, IndexError):
            pass
    return os.environ.get('SYSTEM_TEAMPROJECT', '')


async def run_action():
    # ── Azure DevOps system variables (MUST come from the pipeline) ──
    BUILD_REASON = os.environ.get('BUILD_REASON')
    SYSTEM_PULLREQUEST_PULLREQUESTID = os.environ.get('SYSTEM_PULLREQUEST_PULLREQUESTID')
    SYSTEM_COLLECTIONURI = os.environ.get('SYSTEM_COLLECTIONURI')
    AZURE_DEVOPS_PAT = os.environ.get('AZURE_DEVOPS_PAT') or os.environ.get('SYSTEM_ACCESSTOKEN')

    # Resolve the *actual* PR repo and project (handles cross-repo build validation)
    PR_REPOSITORY_NAME = _resolve_pr_repo_name()
    PR_PROJECT = _resolve_pr_project()

    # ── Config sourcing: env vars override GCS-loaded settings ──
    OPENAI_KEY = os.environ.get('OPENAI_KEY') or os.environ.get('OPENAI.KEY')
    OPENAI_ORG = os.environ.get('OPENAI_ORG') or os.environ.get('OPENAI.ORG')

    # Ensure pipeline-provided DASHBOARD_URL / API_KEY override any GCS defaults
    # BEFORE dashboard integration is initialized.  GCS config may have stale or
    # placeholder values; the VM env file (sourced by step 2 of the pipeline)
    # carries the authoritative dashboard coordinates.
    env_dashboard_url = os.environ.get('DASHBOARD_URL', '').strip()
    env_dashboard_api_key = os.environ.get('DASHBOARD_API_KEY', '').strip()
    if env_dashboard_url:
        get_settings().set("DASHBOARD.URL", env_dashboard_url)
    if env_dashboard_api_key:
        get_settings().set("DASHBOARD.API_KEY", env_dashboard_api_key)

    # Setup dashboard integration (reads DASHBOARD.URL / DASHBOARD.API_KEY from
    # settings or env vars; error-resilient)
    dashboard_enabled = False
    if DASHBOARD_AVAILABLE:
        try:
            dashboard_enabled = setup_dashboard_integration()
            get_logger().info(f"Azure DevOps Pipeline execution starting - Dashboard integration: {'enabled' if dashboard_enabled else 'disabled'}")
        except Exception as e:
            get_logger().debug(f"Dashboard setup failed: {e}")

    # ── Validate required Azure system variables ──
    if not BUILD_REASON:
        print("BUILD_REASON not set")
        return
    if BUILD_REASON != 'PullRequest':
        print(f"BUILD_REASON is '{BUILD_REASON}', not 'PullRequest' - skipping")
        return
    for var_name, var_val in [
        ("SYSTEM_PULLREQUEST_PULLREQUESTID", SYSTEM_PULLREQUEST_PULLREQUESTID),
        ("PR_PROJECT (System.TeamProject / SourceRepositoryUri)", PR_PROJECT),
        ("PR_REPOSITORY_NAME (Build.Repository.Name / SourceRepositoryUri)", PR_REPOSITORY_NAME),
        ("SYSTEM_COLLECTIONURI", SYSTEM_COLLECTIONURI),
    ]:
        if not var_val:
            print(f"{var_name} not set")
            return
    if not AZURE_DEVOPS_PAT:
        print("AZURE_DEVOPS_PAT or SYSTEM_ACCESSTOKEN not set")
        return

    # ── Apply env-var overrides on top of GCS-loaded settings ──
    if OPENAI_KEY:
        get_settings().set("OPENAI.KEY", OPENAI_KEY)
    elif not get_settings().get("OPENAI.KEY", None):
        get_logger().info("OPENAI_KEY not in env or GCS config (ok if using non-OpenAI models)")
    if OPENAI_ORG:
        get_settings().set("OPENAI.ORG", OPENAI_ORG)

    # Azure DevOps PAT and org are per-build; always set from pipeline
    get_settings().set("AZURE_DEVOPS.PAT", AZURE_DEVOPS_PAT)
    get_settings().set("AZURE_DEVOPS.ORG", SYSTEM_COLLECTIONURI)

    # This IS the Azure DevOps pipeline runner -- always force the provider.
    # GCS config may still have the package default (github); override it.
    get_settings().set("CONFIG.GIT_PROVIDER", "azure")
    enable_output = get_setting_or_env("AZURE_DEVOPS_CONFIG.ENABLE_OUTPUT", True)
    get_settings().set("AZURE_DEVOPS_CONFIG.ENABLE_OUTPUT", enable_output)
    get_settings().set("CONFIG.PUBLISH_OUTPUT_PROGRESS", False)

    # Construct PR URL using the *actual* PR repo, not the pipeline repo.
    pr_url = f"{SYSTEM_COLLECTIONURI.rstrip('/')}/{PR_PROJECT}/_git/{PR_REPOSITORY_NAME}/pullrequest/{SYSTEM_PULLREQUEST_PULLREQUESTID}"

    build_repo = os.environ.get('BUILD_REPOSITORY_NAME', '?')
    if build_repo != PR_REPOSITORY_NAME:
        get_logger().info(
            f"Cross-repo build validation: pipeline repo='{build_repo}', "
            f"PR repo='{PR_REPOSITORY_NAME}' (project={PR_PROJECT})"
        )
    get_logger().info(f"Processing Azure DevOps PR: {pr_url}")

    try:
        get_logger().info("Applying repo settings")
        apply_repo_settings(pr_url)
        get_logger().info(f"enable_custom_labels: {get_settings().config.enable_custom_labels}")
    except Exception as e:
        get_logger().info(f"azure devops pipeline: failed to apply repo settings: {e}")

    # Re-assert per-run auth context after repo settings are applied.
    # Repo settings may include [azure_devops] or [config] overrides;
    # runtime pipeline auth and provider must win.
    get_settings().set("AZURE_DEVOPS.PAT", AZURE_DEVOPS_PAT)
    get_settings().set("AZURE_DEVOPS.ORG", SYSTEM_COLLECTIONURI)
    get_settings().set("CONFIG.GIT_PROVIDER", "azure")

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