import copy
import datetime
import traceback
from collections import OrderedDict
from functools import partial
from typing import List, Tuple

from jinja2 import Environment, StrictUndefined

from pr_agent.algo.ai_handlers.base_ai_handler import BaseAiHandler
from pr_agent.algo.ai_handlers.litellm_ai_handler import LiteLLMAIHandler
from pr_agent.algo.pr_processing import (add_ai_metadata_to_diff_files,
                                         get_pr_diff,
                                         retry_with_fallback_models)
from pr_agent.algo.token_handler import TokenHandler
from pr_agent.algo.utils import (ModelType, PRReviewHeader,
                                 convert_to_markdown_v2, github_action_output,
                                 load_yaml, show_relevant_configurations)
from pr_agent.config_loader import get_settings
from pr_agent.git_providers import (get_git_provider,
                                    get_git_provider_with_context)
from pr_agent.git_providers.git_provider import (IncrementalPR,
                                                 get_main_pr_language)
from pr_agent.log import get_logger
from pr_agent.servers.help import HelpMessage
from pr_agent.tools.ticket_pr_compliance_check import (
    extract_and_cache_pr_tickets, extract_tickets)

# Dashboard integration imports
try:
    from pr_agent.log.job_context import (
        operation_context, OperationType, update_operation_status, 
        update_operation_ai_metrics, extract_repository_from_url
    )
    DASHBOARD_AVAILABLE = True
except ImportError:
    DASHBOARD_AVAILABLE = False


class PRReviewer:
    """
    The PRReviewer class is responsible for reviewing a pull request and generating feedback using an AI model.
    """

    def __init__(self, pr_url: str, is_answer: bool = False, is_auto: bool = False, args: list = None,
                 ai_handler: partial[BaseAiHandler,] = LiteLLMAIHandler):
        """
        Initialize the PRReviewer object with the necessary attributes and objects to review a pull request.

        Args:
            pr_url (str): The URL of the pull request to be reviewed.
            is_answer (bool, optional): Indicates whether the review is being done in answer mode. Defaults to False.
            is_auto (bool, optional): Indicates whether the review is being done in automatic mode. Defaults to False.
            ai_handler (BaseAiHandler): The AI handler to be used for the review. Defaults to None.
            args (list, optional): List of arguments passed to the PRReviewer class. Defaults to None.
        """
        self.git_provider = get_git_provider_with_context(pr_url)
        self.args = args
        self.incremental = self.parse_incremental(args)  # -i command
        if self.incremental and self.incremental.is_incremental:
            self.git_provider.get_incremental_commits(self.incremental)

        self.main_language = get_main_pr_language(
            self.git_provider.get_languages(), self.git_provider.get_files()
        )
        self.pr_url = pr_url
        self.is_answer = is_answer
        self.is_auto = is_auto

        if self.is_answer and not self.git_provider.is_supported("get_issue_comments"):
            raise Exception(f"Answer mode is not supported for {get_settings().config.git_provider} for now")
        # Handle both class and instance cases for ai_handler
        if isinstance(ai_handler, type):
            # ai_handler is a class, instantiate it
            self.ai_handler = ai_handler()
        else:
            # ai_handler is already an instance, use it directly
            self.ai_handler = ai_handler
        self.ai_handler.main_pr_language = self.main_language
        self.patches_diff = None
        self.prediction = None
        answer_str, question_str = self._get_user_answers()
        self.pr_description, self.pr_description_files = (
            self.git_provider.get_pr_description(split_changes_walkthrough=True))
        if (self.pr_description_files and get_settings().get("config.is_auto_command", False) and
                get_settings().get("config.enable_ai_metadata", False)):
            add_ai_metadata_to_diff_files(self.git_provider, self.pr_description_files)
            get_logger().debug(f"AI metadata added to the this command")
        else:
            get_settings().set("config.enable_ai_metadata", False)
            get_logger().debug(f"AI metadata is disabled for this command")

        self.vars = {
            "title": self.git_provider.pr.title,
            "branch": self.git_provider.get_pr_branch(),
            "description": self.pr_description,
            "language": self.main_language,
            "diff": "",  # empty diff for initial calculation
            "num_pr_files": self.git_provider.get_num_of_files(),
            "num_max_findings": get_settings().pr_reviewer.num_max_findings,
            "require_score": get_settings().pr_reviewer.require_score_review,
            "require_tests": get_settings().pr_reviewer.require_tests_review,
            "require_estimate_effort_to_review": get_settings().pr_reviewer.require_estimate_effort_to_review,
            'require_can_be_split_review': get_settings().pr_reviewer.require_can_be_split_review,
            'require_security_review': get_settings().pr_reviewer.require_security_review,
            'question_str': question_str,
            'answer_str': answer_str,
            "extra_instructions": get_settings().pr_reviewer.extra_instructions,
            "commit_messages_str": self.git_provider.get_commit_messages(),
            "custom_labels": "",
            "enable_custom_labels": get_settings().config.enable_custom_labels,
            "is_ai_metadata":  get_settings().get("config.enable_ai_metadata", False),
            "related_tickets": get_settings().get('related_tickets', []),
            'duplicate_prompt_examples': get_settings().config.get('duplicate_prompt_examples', False),
            "date": datetime.datetime.now().strftime('%Y-%m-%d'),
        }

        self.token_handler = TokenHandler(
            self.git_provider.pr,
            self.vars,
            get_settings().pr_review_prompt.system,
            get_settings().pr_review_prompt.user
        )

    def parse_incremental(self, args: List[str]):
        is_incremental = False
        if args and len(args) >= 1:
            arg = args[0]
            if arg == "-i":
                is_incremental = True
        incremental = IncrementalPR(is_incremental)
        return incremental

    async def run(self) -> None:
        # Extract repository information for dashboard tracking
        repository = None
        if DASHBOARD_AVAILABLE:
            try:
                repository = extract_repository_from_url(self.pr_url)
            except Exception as e:
                get_logger().debug(f"Failed to extract repository from URL: {e}")

        # Create operation context for dashboard tracking (error resilient)
        if DASHBOARD_AVAILABLE:
            try:
                # Only catch operation context setup errors, not operation execution errors
                operation_context_manager = operation_context(
                    operation_type=OperationType.GENERATING_REVIEW,
                    command="review",
                    repo=repository,
                    pr_url=self.pr_url,
                    installation_id=getattr(self.git_provider, 'installation_id', None),
                    sender=getattr(self.git_provider, 'sender', None)
                )
            except Exception as e:
                get_logger().warning(f"Dashboard operation context setup failed, continuing without tracking: {e}")
                # Fall through to execute without tracking
                get_logger().info("Executing PR review without dashboard tracking (context setup failed)")
                return await self._run_without_tracking()
            
            # Execute with dashboard tracking - let operation failures be tracked
            with operation_context_manager as operation_id:
                get_logger().info(f"PR review operation started with ID: {operation_id}")
                return await self._run_with_tracking(operation_id)
        
        # Execute without operation tracking (dashboard disabled)
        get_logger().info("Executing PR review without dashboard tracking (dashboard disabled)")
        return await self._run_without_tracking()

    async def _run_with_tracking(self, operation_id: str) -> None:
        """Run PR review with dashboard operation tracking"""
        try:
            # Update operation status to processing
            update_operation_status("processing")
            
            # Execute the main review logic
            result = await self._execute_review_logic()
            
            # Update operation status based on result
            if result is not None:
                update_operation_status("completed", result_data={
                    "review_generated": True,
                    "incremental": self.incremental.is_incremental,
                    "files_reviewed": len(self.git_provider.get_files()) if self.git_provider.get_files() else 0
                })
                get_logger().info(f"PR review operation {operation_id} completed successfully")
            else:
                update_operation_status("failed", error_details="Review generation returned no result")
                get_logger().warning(f"PR review operation {operation_id} completed with no result")
            
            return result
            
        except Exception as e:
            # Update operation status to failed
            update_operation_status("failed", error_details=str(e))
            get_logger().error(f"PR review operation {operation_id} failed: {e}")
            raise

    async def _run_without_tracking(self) -> None:
        """Run PR review without dashboard tracking (fallback)"""
        return await self._execute_review_logic()

    async def _execute_review_logic(self) -> None:
        """Main PR review logic (extracted for reuse with/without tracking)"""
        try:
            if not self.git_provider.get_files():
                get_logger().info(f"PR has no files: {self.pr_url}, skipping review")
                return None

            if self.incremental.is_incremental and not self._can_run_incremental_review():
                return None

            # if isinstance(self.args, list) and self.args and self.args[0] == 'auto_approve':
            #     get_logger().info(f'Auto approve flow PR: {self.pr_url} ...')
            #     self.auto_approve_logic()
            #     return None

            get_logger().info(f'Reviewing PR: {self.pr_url} ...')
            relevant_configs = {'pr_reviewer': dict(get_settings().pr_reviewer),
                                'config': dict(get_settings().config)}
            get_logger().debug("Relevant configs", artifacts=relevant_configs)

            # ticket extraction if exists
            await extract_and_cache_pr_tickets(self.git_provider, self.vars)

            if self.incremental.is_incremental and hasattr(self.git_provider, "unreviewed_files_set") and not self.git_provider.unreviewed_files_set:
                get_logger().info(f"Incremental review is enabled for {self.pr_url} but there are no new files")
                previous_review_url = ""
                if hasattr(self.git_provider, "previous_review"):
                    previous_review_url = self.git_provider.previous_review.html_url
                if get_settings().config.publish_output:
                    self.git_provider.publish_comment(f"Incremental Review Skipped\n"
                                    f"No files were changed since the [previous PR Review]({previous_review_url})")
                return None

            if get_settings().config.publish_output and not get_settings().config.get('is_auto_command', False):
                self.git_provider.publish_comment("Preparing review...", is_temporary=True)

            await retry_with_fallback_models(self._prepare_prediction, model_type=ModelType.REGULAR)
            if not self.prediction:
                self.git_provider.remove_initial_comment()
                return None

            pr_review = self._prepare_pr_review()
            get_logger().debug(f"PR output", artifact=pr_review)

            if get_settings().config.publish_output:
                # publish the review
                if get_settings().pr_reviewer.persistent_comment and not self.incremental.is_incremental:
                    final_update_message = get_settings().pr_reviewer.final_update_message
                    self.git_provider.publish_persistent_comment(pr_review,
                                                                 initial_header=f"{PRReviewHeader.REGULAR.value} 🔍",
                                                                 update_header=True,
                                                                 final_update_message=final_update_message, )
                else:
                    self.git_provider.publish_comment(pr_review)

                self.git_provider.remove_initial_comment()
            else:
                get_logger().info("Review output is not published")
                get_settings().data = {"artifact": pr_review}
                return pr_review
                
            return pr_review
        except Exception as e:
            get_logger().error(f"Failed to review PR: {e}")
            raise

    async def _prepare_prediction(self, model: str) -> None:
        self.patches_diff = await get_pr_diff(self.git_provider,
                                        self.token_handler,
                                        model,
                                        add_line_numbers_to_hunks=True,
                                        disable_extra_lines=False,)

        if self.patches_diff:
            get_logger().debug(f"PR diff", diff=self.patches_diff)
            self.prediction = await self._get_prediction(model)
        else:
            get_logger().warning(f"Empty diff for PR: {self.pr_url}")
            self.prediction = None

    async def _get_prediction(self, model: str) -> str:
        """
        Generate an AI prediction for the pull request review.

        Args:
            model: A string representing the AI model to be used for the prediction.

        Returns:
            A string representing the AI prediction for the pull request review.
        """
        variables = copy.deepcopy(self.vars)
        variables["diff"] = self.patches_diff  # update diff

        environment = Environment(undefined=StrictUndefined)
        system_prompt = environment.from_string(get_settings().pr_review_prompt.system).render(variables)
        user_prompt = environment.from_string(get_settings().pr_review_prompt.user).render(variables)

        # Track AI metrics for dashboard (error resilient)
        from pr_agent.algo.token_handler import TokenUsageTracker
        
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
                        from pr_agent.algo.token_handler import TokenHandler
                        token_handler = TokenHandler()
                        input_tokens = token_handler.get_token_count_from_string(system_prompt + user_prompt)
                        output_tokens = token_handler.get_token_count_from_string(response)
                    
                    # Estimate developer time saved for review operation using AI analysis
                    try:
                        estimated_hours = await self._estimate_review_dev_hours_saved_ai(
                            model=model,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            files_count=len(self.git_provider.get_files()) if self.git_provider.get_files() else 0,
                            diff=self.patches_diff,
                            review_content=response
                        )
                    except Exception as e:
                        get_logger().debug(f"AI time estimation failed, using fallback: {e}")
                        estimated_hours = self._estimate_review_dev_hours_saved(
                            model=model,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            files_count=len(self.git_provider.get_files()) if self.git_provider.get_files() else 0
                        )
                    
                    # Update AI metrics
                    update_operation_ai_metrics(
                        model_used=model,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        estimated_dev_hours_saved=estimated_hours
                    )
                    
                    get_logger().info(f"AI metrics updated - Input: {input_tokens}, Output: {output_tokens}, "
                                    f"Calls: {totals['call_count']}, Failed: {totals['failed_calls']}")
                    
                except Exception as e:
                    get_logger().debug(f"Failed to track AI metrics for review: {e}")
            
            return response
            
        except Exception as e:
            # Track failed AI call
            token_tracker.add_usage(None, call_failed=True)
            
            # Track failed AI call if dashboard is available
            if DASHBOARD_AVAILABLE:
                try:
                    # Estimate tokens for failed call
                    from pr_agent.algo.token_handler import TokenHandler
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

    def _estimate_review_dev_hours_saved(self, model: str, input_tokens: int = None, 
                                       output_tokens: int = None, files_count: int = 0) -> float:
        """
        Estimate developer hours saved for PR review operation
        """
        try:
            # Base time for manual PR review (varies by complexity)
            base_review_hours = 0.5  # 30 minutes base
            
            # Adjust based on number of files
            if files_count > 20:
                base_review_hours = 2.0  # 2 hours for large PRs
            elif files_count > 10:
                base_review_hours = 1.0  # 1 hour for medium PRs
            elif files_count > 5:
                base_review_hours = 0.75  # 45 minutes for small-medium PRs
            
            # Adjust based on token complexity (if available)
            complexity_multiplier = 1.0
            if input_tokens and output_tokens:
                total_tokens = input_tokens + output_tokens
                if total_tokens > 3000:
                    complexity_multiplier = 1.5  # Complex review
                elif total_tokens > 1500:
                    complexity_multiplier = 1.2  # Medium complexity
                elif total_tokens < 500:
                    complexity_multiplier = 0.8  # Simple review
            
            # Adjust based on model capability
            model_multiplier = 1.0
            model_lower = model.lower()
            if any(name in model_lower for name in ['gpt-4', 'claude-3-opus', 'claude-3-5-sonnet']):
                model_multiplier = 1.3  # High-quality models save more time
            elif any(name in model_lower for name in ['gpt-3.5', 'claude-3-sonnet']):
                model_multiplier = 1.0  # Standard models
            else:
                model_multiplier = 0.8  # Lower capability models
            
            # Calculate final estimate
            estimated_hours = base_review_hours * complexity_multiplier * model_multiplier
            
            # Cap at reasonable bounds (allow negative values for time wasted)
            return max(-4.0, min(4.0, estimated_hours))
            
        except Exception as e:
            get_logger().debug(f"Failed to estimate review dev hours: {e}")
            return 0.5  # Default fallback

    async def _estimate_review_dev_hours_saved_ai(self, model: str, input_tokens: int = None, 
                                                 output_tokens: int = None, files_count: int = 0,
                                                 diff: str = None, review_content: str = None) -> float:
        """
        Estimate developer hours saved using AI-powered analysis of the review
        """
        try:
            if not diff or not review_content:
                # Fall back to heuristic if we don't have the necessary data
                return self._estimate_review_dev_hours_saved(model, input_tokens, output_tokens, files_count)
            
            from pr_agent.algo.dev_time_estimator import DevTimeEstimator
            
            estimator = DevTimeEstimator(self.ai_handler, self.token_handler)
            
            # Extract line counts from diff
            lines_added = 0
            lines_deleted = 0
            if diff:
                for line in diff.split('\n'):
                    if line.startswith('+') and not line.startswith('+++'):
                        lines_added += 1
                    elif line.startswith('-') and not line.startswith('---'):
                        lines_deleted += 1
            
            estimation_result = await estimator.estimate_review_time_savings(
                diff=diff,
                ai_review_content=review_content,
                language=self.main_language,
                files_changed=files_count,
                lines_added=lines_added,
                lines_deleted=lines_deleted,
                model=model
            )
            
            if estimation_result and 'final_assessment' in estimation_result:
                estimated_hours = estimation_result['final_assessment'].get('total_developer_hours_saved', 1.0)
                confidence = estimation_result['final_assessment'].get('confidence_level', 'medium')
                
                get_logger().info(f"AI-powered time estimation: {estimated_hours} hours (confidence: {confidence})", 
                                artifacts={'estimation_details': estimation_result})
                return float(estimated_hours)
            else:
                # Fall back to heuristic if AI estimation fails
                return self._estimate_review_dev_hours_saved(model, input_tokens, output_tokens, files_count)
            
        except Exception as e:
            get_logger().debug(f"AI time estimation failed: {e}")
            return self._estimate_review_dev_hours_saved(model, input_tokens, output_tokens, files_count)

    def _prepare_pr_review(self) -> str:
        """
        Prepare the PR review by processing the AI prediction and generating a markdown-formatted text that summarizes
        the feedback.
        """
        first_key = 'review'
        last_key = 'security_concerns'
        data = load_yaml(self.prediction.strip(),
                         keys_fix_yaml=["ticket_compliance_check", "estimated_effort_to_review_[1-5]:", "security_concerns:", "key_issues_to_review:",
                                        "relevant_file:", "relevant_line:", "suggestion:"],
                         first_key=first_key, last_key=last_key)
        github_action_output(data, 'review')

        if 'review' not in data:
            get_logger().exception("Failed to parse review data", artifact={"data": data})
            return ""

        # move data['review'] 'key_issues_to_review' key to the end of the dictionary
        if 'key_issues_to_review' in data['review']:
            key_issues_to_review = data['review'].pop('key_issues_to_review')
            data['review']['key_issues_to_review'] = key_issues_to_review

        incremental_review_markdown_text = None
        # Add incremental review section
        if self.incremental.is_incremental:
            last_commit_url = f"{self.git_provider.get_pr_url()}/commits/" \
                              f"{self.git_provider.incremental.first_new_commit_sha}"
            incremental_review_markdown_text = f"Starting from commit {last_commit_url}"

        markdown_text = convert_to_markdown_v2(data, self.git_provider.is_supported("gfm_markdown"),
                                            incremental_review_markdown_text,
                                               git_provider=self.git_provider,
                                               files=self.git_provider.get_diff_files())

        # Add help text if gfm_markdown is supported
        if self.git_provider.is_supported("gfm_markdown") and get_settings().pr_reviewer.enable_help_text:
            markdown_text += "<hr>\n\n<details> <summary><strong>💡 Tool usage guide:</strong></summary><hr> \n\n"
            markdown_text += HelpMessage.get_review_usage_guide()
            markdown_text += "\n</details>\n"

        # Output the relevant configurations if enabled
        if get_settings().get('config', {}).get('output_relevant_configurations', False):
            markdown_text += show_relevant_configurations(relevant_section='pr_reviewer')

        # Add custom labels from the review prediction (effort, security)
        self.set_review_labels(data)

        if markdown_text == None or len(markdown_text) == 0:
            markdown_text = ""

        return markdown_text

    def _get_user_answers(self) -> Tuple[str, str]:
        """
        Retrieves the question and answer strings from the discussion messages related to a pull request.

        Returns:
            A tuple containing the question and answer strings.
        """
        question_str = ""
        answer_str = ""

        if self.is_answer:
            discussion_messages = self.git_provider.get_issue_comments()

            for message in discussion_messages.reversed:
                if "Questions to better understand the PR:" in message.body:
                    question_str = message.body
                elif '/answer' in message.body:
                    answer_str = message.body

                if answer_str and question_str:
                    break

        return question_str, answer_str

    def _get_previous_review_comment(self):
        """
        Get the previous review comment if it exists.
        """
        try:
            if hasattr(self.git_provider, "get_previous_review"):
                return self.git_provider.get_previous_review(
                    full=not self.incremental.is_incremental,
                    incremental=self.incremental.is_incremental,
                )
        except Exception as e:
            get_logger().exception(f"Failed to get previous review comment, error: {e}")

    def _remove_previous_review_comment(self, comment):
        """
        Remove the previous review comment if it exists.
        """
        try:
            if comment:
                self.git_provider.remove_comment(comment)
        except Exception as e:
            get_logger().exception(f"Failed to remove previous review comment, error: {e}")

    def _can_run_incremental_review(self) -> bool:
        """
        Checks if we can run incremental review according the various configurations and previous review.
        """
        # checking if running is auto mode but there are no new commits
        if self.is_auto and not self.incremental.first_new_commit_sha:
            get_logger().info(f"Incremental review is enabled for {self.pr_url} but there are no new commits")
            return False

        if not hasattr(self.git_provider, "get_incremental_commits"):
            get_logger().info(f"Incremental review is not supported for {get_settings().config.git_provider}")
            return False
        # checking if there are enough commits to start the review
        num_new_commits = len(self.incremental.commits_range)
        num_commits_threshold = get_settings().pr_reviewer.minimal_commits_for_incremental_review
        not_enough_commits = num_new_commits < num_commits_threshold
        # checking if the commits are not too recent to start the review
        recent_commits_threshold = datetime.datetime.now() - datetime.timedelta(
            minutes=get_settings().pr_reviewer.minimal_minutes_for_incremental_review
        )
        last_seen_commit_date = (
            self.incremental.last_seen_commit.commit.author.date if self.incremental.last_seen_commit else None
        )
        all_commits_too_recent = (
            last_seen_commit_date > recent_commits_threshold if self.incremental.last_seen_commit else False
        )
        # check all the thresholds or just one to start the review
        condition = any if get_settings().pr_reviewer.require_all_thresholds_for_incremental_review else all
        if condition((not_enough_commits, all_commits_too_recent)):
            get_logger().info(
                f"Incremental review is enabled for {self.pr_url} but didn't pass the threshold check to run:"
                f"\n* Number of new commits = {num_new_commits} (threshold is {num_commits_threshold})"
                f"\n* Last seen commit date = {last_seen_commit_date} (threshold is {recent_commits_threshold})"
            )
            return False
        return True

    def set_review_labels(self, data):
        if not get_settings().config.publish_output:
            return

        if not get_settings().pr_reviewer.require_estimate_effort_to_review:
            get_settings().pr_reviewer.enable_review_labels_effort = False # we did not generate this output
        if not get_settings().pr_reviewer.require_security_review:
            get_settings().pr_reviewer.enable_review_labels_security = False # we did not generate this output

        if (get_settings().pr_reviewer.enable_review_labels_security or
                get_settings().pr_reviewer.enable_review_labels_effort):
            try:
                review_labels = []
                if get_settings().pr_reviewer.enable_review_labels_effort:
                    estimated_effort = data['review']['estimated_effort_to_review_[1-5]']
                    estimated_effort_number = 0
                    if isinstance(estimated_effort, str):
                        try:
                            estimated_effort_number = int(estimated_effort.split(',')[0])
                        except ValueError:
                            get_logger().warning(f"Invalid estimated_effort value: {estimated_effort}")
                    elif isinstance(estimated_effort, int):
                        estimated_effort_number = estimated_effort
                    else:
                        get_logger().warning(f"Unexpected type for estimated_effort: {type(estimated_effort)}")
                    if 1 <= estimated_effort_number <= 5:  # 1, because ...
                        review_labels.append(f'Review effort {estimated_effort_number}/5')
                if get_settings().pr_reviewer.enable_review_labels_security and get_settings().pr_reviewer.require_security_review:
                    security_concerns = data['review']['security_concerns']  # yes, because ...
                    security_concerns_bool = 'yes' in security_concerns.lower() or 'true' in security_concerns.lower()
                    if security_concerns_bool:
                        review_labels.append('Possible security concern')

                current_labels = self.git_provider.get_pr_labels(update=True)
                if not current_labels:
                    current_labels = []
                get_logger().debug(f"Current labels:\n{current_labels}")
                if current_labels:
                    current_labels_filtered = [label for label in current_labels if
                                               not label.lower().startswith('review effort') and not label.lower().startswith(
                                                   'possible security concern')]
                else:
                    current_labels_filtered = []
                new_labels = review_labels + current_labels_filtered
                if (current_labels or review_labels) and sorted(new_labels) != sorted(current_labels):
                    get_logger().info(f"Setting review labels:\n{review_labels + current_labels_filtered}")
                    self.git_provider.publish_labels(new_labels)
                else:
                    get_logger().info(f"Review labels are already set:\n{review_labels + current_labels_filtered}")
            except Exception as e:
                get_logger().error(f"Failed to set review labels, error: {e}")

    def auto_approve_logic(self):
        """
        Auto-approve a pull request if it meets the conditions for auto-approval.
        """
        if get_settings().config.enable_auto_approval:
            is_auto_approved = self.git_provider.auto_approve()
            if is_auto_approved:
                get_logger().info("Auto-approved PR")
                self.git_provider.publish_comment("Auto-approved PR")
        else:
            get_logger().info("Auto-approval option is disabled")
            self.git_provider.publish_comment("Auto-approval option for PR-Agent is disabled. "
                                              "You can enable it via a [configuration file](https://github.com/Codium-ai/pr-agent/blob/main/docs/REVIEW.md#auto-approval-1)")
