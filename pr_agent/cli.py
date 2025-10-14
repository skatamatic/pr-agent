import argparse
import asyncio
import os

from pr_agent.agent.pr_agent import PRAgent, commands
from pr_agent.algo.utils import get_version
from pr_agent.algo.pr_filters import check_pr_filters
from pr_agent.config_loader import get_settings
from pr_agent.log import get_logger, setup_logger

# Dashboard integration imports
try:
    from pr_agent.log.job_context import (
        job_context, JobType, extract_repository_from_url, 
        setup_dashboard_integration, update_job_status
    )
    DASHBOARD_AVAILABLE = True
except ImportError:
    DASHBOARD_AVAILABLE = False

log_level = os.environ.get("LOG_LEVEL", "INFO")
setup_logger(log_level)


def set_parser():
    parser = argparse.ArgumentParser(description='AI based pull request analyzer', usage=
    """\
    Usage: cli.py --pr-url=<URL on supported git hosting service> <command> [<args>].
    For example:
    - cli.py --pr_url=... review
    - cli.py --pr_url=... describe
    - cli.py --pr_url=... improve
    - cli.py --pr_url=... ask "write me a poem about this PR"
    - cli.py --pr_url=... reflect
    - cli.py --issue_url=... similar_issue
    - cli.py --pr_url/--issue_url= help_docs [<asked question>]

    Supported commands:
    - review / review_pr - Add a review that includes a summary of the PR and specific suggestions for improvement.

    - ask / ask_question [question] - Ask a question about the PR.

    - describe / describe_pr - Modify the PR title and description based on the PR's contents.

    - improve / improve_code - Suggest improvements to the code in the PR as pull request comments ready to commit.
    Extended mode ('improve --extended') employs several calls, and provides a more thorough feedback

    - reflect - Ask the PR author questions about the PR.

    - update_changelog - Update the changelog based on the PR's contents.

    - add_docs

    - generate_labels
    
    - help_docs - Ask a question, from either an issue or PR context, on a given repo (current context or a different one)


    Configuration:
    To edit any configuration parameter from 'configuration.toml', just add -config_path=<value>.
    For example: 'python cli.py --pr_url=... review --pr_reviewer.extra_instructions="focus on the file: ..."'
    """)
    parser.add_argument('--version', action='version', version=f'pr-agent {get_version()}')
    parser.add_argument('--pr_url', type=str, help='The URL of the PR to review', default=None)
    parser.add_argument('--issue_url', type=str, help='The URL of the Issue to review', default=None)
    parser.add_argument('command', type=str, help='The', choices=commands, default='review')
    parser.add_argument('rest', nargs=argparse.REMAINDER, default=[])
    return parser


def run_command(pr_url, command):
    # Preparing the command
    run_command_str = f"--pr_url={pr_url} {command.lstrip('/')}"
    args = set_parser().parse_args(run_command_str.split())

    # Run the command. Feedback will appear in GitHub PR comments
    run(args=args)


def run(inargs=None, args=None):
    parser = set_parser()
    if not args:
        args = parser.parse_args(inargs)
    if not args.pr_url and not args.issue_url:
        parser.print_help()
        return

    command = args.command.lower()
    get_settings().set("CONFIG.CLI_MODE", True)
    
    # Setup dashboard integration (error resilient)
    dashboard_enabled = False
    if DASHBOARD_AVAILABLE:
        try:
            dashboard_enabled = setup_dashboard_integration()
            get_logger().info(f"CLI execution starting - Dashboard integration: {'enabled' if dashboard_enabled else 'disabled'}")
        except Exception as e:
            get_logger().debug(f"Dashboard setup failed: {e}")

    # Determine target URL and extract repository
    target_url = args.issue_url or args.pr_url
    repository = None
    if DASHBOARD_AVAILABLE:
        try:
            repository = extract_repository_from_url(target_url)
            if repository:
                get_logger().debug(f"Extracted repository: {repository}")
        except Exception as e:
            get_logger().debug(f"Failed to extract repository from URL: {e}")

    async def inner():
        result = None
        try:
            # Apply PR filters before processing
            try:
                from pr_agent.git_providers.utils import get_git_provider_with_context
                git_provider = get_git_provider_with_context(target_url)
                filter_result = check_pr_filters(git_provider, command)
                
                if filter_result.should_terminate:
                    get_logger().error(f"PR filter triggered termination: {filter_result.reason}")
                    return False
                elif filter_result.should_skip:
                    get_logger().info(f"PR filter triggered skip: {filter_result.reason}")
                    return True
            except Exception as e:
                get_logger().error(f"Failed to apply PR filters, terminating for safety: {e}")
                return False
            
            # Create job context if dashboard integration is available
            if DASHBOARD_AVAILABLE and dashboard_enabled:
                try:
                    # Use job context for dashboard tracking
                    with job_context(
                        job_type=JobType.CLI,
                        source="cli",
                        repository=repository,
                        pr_url=target_url,
                        trigger_event="cli_command",
                        request_id=f"cli-{command}-{os.getpid()}"
                    ) as job_id:
                        get_logger().info(f"CLI job started with ID: {job_id}")
                        
                        try:
                            # Update job status to running
                            update_job_status("running")
                            
                            # Execute the PR-Agent command
                            if args.issue_url:
                                result = await asyncio.create_task(PRAgent().handle_request(args.issue_url, [command] + args.rest))
                            else:
                                result = await asyncio.create_task(PRAgent().handle_request(args.pr_url, [command] + args.rest))
                            
                            # Update job status based on result
                            if result:
                                update_job_status("completed", result_summary={"command": command, "success": True})
                                get_logger().info(f"CLI job {job_id} completed successfully")
                            else:
                                update_job_status("failed", error_details="Command returned no result")
                                get_logger().warning(f"CLI job {job_id} completed with no result")
                            
                            return result
                            
                        except Exception as e:
                            # Update job status to failed
                            update_job_status("failed", error_details=str(e))
                            get_logger().error(f"CLI job {job_id} failed: {e}")
                            raise
                            
                except Exception as e:
                    get_logger().warning(f"Dashboard job tracking failed, continuing without tracking: {e}")
                    # Fall through to execute without job tracking
            
            # Execute without job tracking (fallback or dashboard disabled)
            if result is None:
                get_logger().info("Executing CLI command without dashboard tracking")
                if args.issue_url:
                    result = await asyncio.create_task(PRAgent().handle_request(args.issue_url, [command] + args.rest))
                else:
                    result = await asyncio.create_task(PRAgent().handle_request(args.pr_url, [command] + args.rest))
            
            return result
            
        finally:
            # Cleanup dashboard tasks BEFORE the event loop closes
            if DASHBOARD_AVAILABLE:
                try:
                    get_logger().debug("Starting dashboard cleanup...")
                    from pr_agent.log.job_context import cleanup_all_dashboard_tasks
                    await cleanup_all_dashboard_tasks()
                    get_logger().debug("Dashboard cleanup completed")
                except Exception as e:
                    get_logger().debug(f"Dashboard cleanup error: {e}")  # Don't fail the main operation

    # Execute the async function with proper callback handling
    try:
        result = asyncio.run(inner())
        
        # Handle callbacks if enabled
        if get_settings().litellm.get("enable_callbacks", False):
            async def cleanup_callbacks():
                get_logger().debug("Waiting for event queue to complete")
                tasks = [task for task in asyncio.all_tasks() if task is not asyncio.current_task()]
                if tasks:
                    _, pending = await asyncio.wait(tasks, timeout=30)
                    if pending:
                        get_logger().warning(
                            f"{len(pending)} callback tasks({[task.get_coro() for task in pending]}) did not complete within timeout"
                        )
            
            asyncio.run(cleanup_callbacks())
        
        # Dashboard cleanup already handled within the event loop
        
        if not result:
            parser.print_help()
            
    except KeyboardInterrupt:
        get_logger().info("CLI execution interrupted by user")
        # Job status update and cleanup already handled within the event loop's finally block
    except Exception as e:
        get_logger().error(f"CLI execution failed: {e}")
        # Job status update and cleanup already handled within the event loop's finally block
        raise


if __name__ == '__main__':
    run()
