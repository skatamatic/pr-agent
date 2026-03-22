import copy
from datetime import date
from functools import partial
from time import sleep
from typing import Tuple

from jinja2 import Environment, StrictUndefined

from pr_agent.algo.ai_handlers.base_ai_handler import BaseAiHandler
from pr_agent.algo.ai_handlers.litellm_ai_handler import LiteLLMAIHandler
from pr_agent.algo.pr_processing import get_pr_diff, retry_with_fallback_models
from pr_agent.algo.token_handler import TokenHandler, TokenUsageTracker
from pr_agent.algo.utils import ModelType, show_relevant_configurations
from pr_agent.config_loader import get_settings
from pr_agent.git_providers import GithubProvider, get_git_provider
from pr_agent.git_providers.git_provider import get_main_pr_language
from pr_agent.log import get_logger

# Dashboard integration imports
try:
    from pr_agent.log.job_context import (
        operation_context, OperationType, update_operation_status, 
        update_operation_ai_metrics, extract_repository_from_url
    )
    DASHBOARD_AVAILABLE = True
except ImportError:
    DASHBOARD_AVAILABLE = False

CHANGELOG_LINES = 50


class PRUpdateChangelog:
    def __init__(self, pr_url: str, cli_mode=False, args=None, ai_handler: partial[BaseAiHandler,] = LiteLLMAIHandler):

        self.git_provider = get_git_provider()(pr_url)
        self.main_language = get_main_pr_language(
            self.git_provider.get_languages(), self.git_provider.get_files()
        )
        self.commit_changelog = get_settings().pr_update_changelog.push_changelog_changes
        self._get_changelog_file()  # self.changelog_file_str

        self.ai_handler = ai_handler()
        self.ai_handler.main_pr_language = self.main_language

        self.patches_diff = None
        self.prediction = None
        self.cli_mode = cli_mode
        self.vars = {
            "title": self.git_provider.pr.title,
            "branch": self.git_provider.get_pr_branch(),
            "description": self.git_provider.get_pr_description(),
            "language": self.main_language,
            "diff": "",  # empty diff for initial calculation
            "pr_link": "",
            "changelog_file_str": self.changelog_file_str,
            "today": date.today(),
            "extra_instructions": get_settings().pr_update_changelog.extra_instructions,
            "commit_messages_str": self.git_provider.get_commit_messages(),
        }
        self.token_handler = TokenHandler(self.git_provider.pr,
                                          self.vars,
                                          get_settings().pr_update_changelog_prompt.system,
                                          get_settings().pr_update_changelog_prompt.user)

    async def run(self):
        # Extract repository information for dashboard tracking
        repository = None
        pr_url = self.git_provider.get_pr_url()
        if DASHBOARD_AVAILABLE:
            try:
                repository = extract_repository_from_url(pr_url)
            except Exception as e:
                get_logger().debug(f"Failed to extract repository from URL: {e}")

        # Create operation context for dashboard tracking (error resilient)
        if DASHBOARD_AVAILABLE:
            try:
                with operation_context(
                    operation_type=OperationType.UPDATING_CHANGELOG,
                    command="update_changelog",
                    repository=repository,
                    pr_url=pr_url,
                    installation_id=getattr(self.git_provider, 'installation_id', None),
                    sender=getattr(self.git_provider, 'sender', None)
                ) as operation_id:
                    get_logger().info(f"PR update changelog operation started with ID: {operation_id}")
                    return await self._run_with_tracking(operation_id)
            except Exception as e:
                get_logger().warning(f"Dashboard operation tracking failed, continuing without tracking: {e}")
                # Fall through to execute without tracking
        
        # Execute without operation tracking (fallback or dashboard disabled)
        get_logger().info("Executing PR update changelog without dashboard tracking")
        return await self._run_without_tracking()

    async def _run_with_tracking(self, operation_id: str):
        """Execute PR update changelog with dashboard operation tracking"""
        try:
            update_operation_status("processing")
            
            result = await self._execute_update_changelog()
            
            # Determine if changelog was actually updated
            changelog_updated = self.commit_changelog and hasattr(self, 'prediction') and self.prediction
            
            update_operation_status("completed", result_data={
                "changelog_updated": changelog_updated,
                "commit_changelog": self.commit_changelog,
                "language": self.main_language,
                "cli_mode": self.cli_mode
            })
            
            return result
            
        except Exception as e:
            update_operation_status("failed", error_details=str(e))
            raise

    async def _run_without_tracking(self):
        """Execute PR update changelog without dashboard tracking (fallback)"""
        return await self._execute_update_changelog()

    async def _execute_update_changelog(self):
        """Core PR update changelog execution logic"""
        get_logger().info('Updating the changelog...')
        relevant_configs = {'pr_update_changelog': dict(get_settings().pr_update_changelog),
                            'config': dict(get_settings().config)}
        get_logger().debug("Relevant configs", artifacts=relevant_configs)

        # currently only GitHub is supported for pushing changelog changes
        if get_settings().pr_update_changelog.push_changelog_changes and not hasattr(
            self.git_provider, "create_or_update_pr_file"
        ):
            get_logger().error(
                "Pushing changelog changes is not currently supported for this code platform"
            )
            if get_settings().config.publish_output:
                self.git_provider.publish_comment(
                    "Pushing changelog changes is not currently supported for this code platform"
                )
            return

        if get_settings().config.publish_output:
            self.git_provider.publish_comment("Preparing changelog updates...", is_temporary=True)

        await retry_with_fallback_models(self._prepare_prediction, model_type=ModelType.WEAK)

        new_file_content, answer = self._prepare_changelog_update()

        # Output the relevant configurations if enabled
        if get_settings().get('config', {}).get('output_relevant_configurations', False):
            answer += show_relevant_configurations(relevant_section='pr_update_changelog')

        get_logger().debug(f"PR output", artifact=answer)

        if get_settings().config.publish_output:
            self.git_provider.remove_initial_comment()
            if self.commit_changelog:
                self._push_changelog_update(new_file_content, answer)
            else:
                self.git_provider.publish_comment(f"**Changelog updates:** 🔄\n\n{answer}")

    async def _prepare_prediction(self, model: str):
        self.patches_diff = get_pr_diff(self.git_provider, self.token_handler, model)
        if self.patches_diff:
            get_logger().debug(f"PR diff", artifact=self.patches_diff)
            self.prediction = await self._get_prediction(model)
        else:
            get_logger().error(f"Error getting PR diff")
            self.prediction = ""

    async def _get_prediction(self, model: str):
        variables = copy.deepcopy(self.vars)
        variables["diff"] = self.patches_diff  # update diff
        if get_settings().pr_update_changelog.add_pr_link:
            variables["pr_link"] = self.git_provider.get_pr_url()
        environment = Environment(undefined=StrictUndefined)
        system_prompt = environment.from_string(get_settings().pr_update_changelog_prompt.system).render(variables)
        user_prompt = environment.from_string(get_settings().pr_update_changelog_prompt.user).render(variables)
        
        # Track AI metrics for dashboard (error resilient)
        token_tracker = TokenUsageTracker()
        
        try:
            response, finish_reason, token_usage = await self.ai_handler.chat_completion(
                model=model,
                temperature=get_settings().config.temperature,
                system=system_prompt,
                user=user_prompt
            )
            
            # Track token usage from successful call
            token_tracker.add_usage(token_usage, call_failed=False)
            
            # Update dashboard metrics if available
            if DASHBOARD_AVAILABLE:
                try:
                    totals = token_tracker.get_totals()
                    input_tokens = totals['input_tokens']
                    output_tokens = totals['output_tokens']
                    
                    # Use accurate token counts if available, otherwise estimate
                    if not token_tracker.has_usage():
                        get_logger().warning("No accurate token usage available, falling back to estimation")
                        # Fallback to tiktoken estimation
                        token_handler = TokenHandler()
                        input_tokens = token_handler.get_token_count_from_string(system_prompt + user_prompt)
                        output_tokens = token_handler.get_token_count_from_string(response)
                    
                    # Update AI metrics (no time estimation for changelog updates)
                    update_operation_ai_metrics(
                        model_used=model,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        estimated_dev_hours_saved=0.1  # Small fixed amount for changelog updates
                    )
                    
                    get_logger().info(f"AI metrics updated - Input: {input_tokens}, Output: {output_tokens}, "
                                    f"Calls: {totals['call_count']}, Failed: {totals['failed_calls']}")
                    
                except Exception as e:
                    get_logger().debug(f"Failed to track AI metrics for changelog: {e}")
            
            # post-process the response
            response = response.strip()
            if not response:
                return ""
            if response.startswith("```"):
                response_lines = response.splitlines()
                response_lines = response_lines[1:]
                response = "\n".join(response_lines)
            response = response.strip("`")
            return response
            
        except Exception as e:
            # Track failed AI call
            token_tracker.add_usage(None, call_failed=True)
            
            # Track failed AI call if dashboard is available
            if DASHBOARD_AVAILABLE:
                try:
                    # Estimate tokens for failed call
                    token_handler = TokenHandler()
                    input_tokens = token_handler.get_token_count_from_string(system_prompt + user_prompt)
                    
                    update_operation_ai_metrics(
                        model_used=model,
                        input_tokens=input_tokens,
                        output_tokens=0,
                        estimated_dev_hours_saved=0.0
                    )
                except:
                    pass  # Ignore dashboard errors during error handling
            raise

    def _prepare_changelog_update(self) -> Tuple[str, str]:
        answer = self.prediction.strip().strip("```").strip()  # noqa B005
        if hasattr(self, "changelog_file"):
            existing_content = self.changelog_file
        else:
            existing_content = ""
        if existing_content:
            new_file_content = answer + "\n\n" + self.changelog_file
        else:
            new_file_content = answer

        if not self.commit_changelog:
            answer += "\n\n\n>to commit the new content to the CHANGELOG.md file, please type:" \
                      "\n>'/update_changelog --pr_update_changelog.push_changelog_changes=true'\n"

        return new_file_content, answer

    def _push_changelog_update(self, new_file_content, answer):
        if get_settings().pr_update_changelog.get("skip_ci_on_push", True):
            commit_message = "[skip ci] Update CHANGELOG.md"
        else:
            commit_message = "Update CHANGELOG.md"
        self.git_provider.create_or_update_pr_file(
            file_path="CHANGELOG.md",
            branch=self.git_provider.get_pr_branch(),
            contents=new_file_content,
            message=commit_message,
        )

        sleep(5)  # wait for the file to be updated
        try:
            if get_settings().config.git_provider == "github":
                last_commit_id = list(self.git_provider.pr.get_commits())[-1]
                d = dict(
                    body="CHANGELOG.md update",
                    path="CHANGELOG.md",
                    line=max(2, len(answer.splitlines())),
                    start_line=1,
                )
                self.git_provider.pr.create_review(commit=last_commit_id, comments=[d])
        except Exception:
            # we can't create a review for some reason, let's just publish a comment
            self.git_provider.publish_comment(f"**Changelog updates: 🔄**\n\n{answer}")

    def _get_default_changelog(self):
        example_changelog = \
"""
Example:
## <current_date>

### Added
...
### Changed
...
### Fixed
...
"""
        return example_changelog

    def _get_changelog_file(self):
        try:
            self.changelog_file = self.git_provider.get_pr_file_content(
                "CHANGELOG.md", self.git_provider.get_pr_branch()
            )
            changelog_file_lines = self.changelog_file.splitlines()
            changelog_file_lines = changelog_file_lines[:CHANGELOG_LINES]
            self.changelog_file_str = "\n".join(changelog_file_lines)
        except Exception:
            self.changelog_file_str = ""
            self.changelog_file = ""

        if not self.changelog_file_str:
            self.changelog_file_str = self._get_default_changelog()
