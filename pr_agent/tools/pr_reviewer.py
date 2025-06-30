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
        update_operation_ai_metrics, update_operation_multi_model_ai_metrics,
        extract_repository_from_url, set_operation_step
    )
    DASHBOARD_INTEGRATION_AVAILABLE = True
except ImportError:
    DASHBOARD_INTEGRATION_AVAILABLE = False
    get_logger().debug("Dashboard integration not available for PR Review tool")


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

        # Multi-model AI metrics tracking
        self.ai_models_metrics = {}  # {"model_name": {"input_tokens": int, "output_tokens": int}}

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
            "include_context": get_settings().get("csharp_code_context_service.enabled", False),
            "context": "",  # context empty for initial calculation
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
        get_logger().info('[Review] - Starting comprehensive PR review operation...')
        
        # Extract repository information for dashboard tracking
        repository = None
        if DASHBOARD_INTEGRATION_AVAILABLE:
            try:
                repository = extract_repository_from_url(self.pr_url)
            except Exception as e:
                get_logger().debug(f"Failed to extract repository from URL: {e}")

        # Create operation context for dashboard tracking (error resilient)
        if DASHBOARD_INTEGRATION_AVAILABLE:
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
                get_logger().info("[Review] - Executing PR review without dashboard tracking (context setup failed)")
                return await self._run_without_tracking()
            
            # Execute with dashboard tracking - let operation failures be tracked
            with operation_context_manager as operation_id:
                get_logger().info(f"[Review] - PR review operation started with ID: {operation_id}")
                return await self._run_with_tracking(operation_id)
        
        # Execute without operation tracking (dashboard disabled)
        get_logger().info("[Review] - Executing PR review without dashboard tracking (dashboard disabled)")
        return await self._run_without_tracking()

    async def _run_with_tracking(self, operation_id: str) -> None:
        """Run PR review with dashboard operation tracking"""
        try:
            # Update operation status to processing
            update_operation_status("processing")
            
            # Execute the streamlined workflow with step tracking
            result = await self._execute_streamlined_workflow()
            
            # Update operation status based on result
            if result is not None:
                update_operation_status("completed", result_data={
                    "review_generated": True,
                    "incremental": self.incremental.is_incremental,
                    "files_reviewed": len(self.git_provider.get_files()) if self.git_provider.get_files() else 0
                })
                get_logger().info(f"[Review] - PR review operation {operation_id} completed successfully")
            else:
                update_operation_status("failed", error_details="Review generation returned no result")
                get_logger().warning(f"[Review] - PR review operation {operation_id} completed with no result")
            
            return result
            
        except Exception as e:
            # Update operation status to failed
            update_operation_status("failed", error_details=str(e))
            get_logger().error(f"[Review] - PR review operation {operation_id} failed: {e}")
            raise

    async def _run_without_tracking(self) -> None:
        """Run PR review without dashboard tracking (fallback)"""
        return await self._execute_legacy_workflow()

    async def _execute_streamlined_workflow(self) -> None:
        """Execute the streamlined PR review workflow with step tracking"""
        try:
            # Step 1: Context and diff preparation
            if DASHBOARD_INTEGRATION_AVAILABLE:
                set_operation_step("Context")
            get_logger().info("[Context] - Preparing PR review context and diff...")
            await self._prepare_context_and_diff()
            
            # Step 2: Generate main review
            if DASHBOARD_INTEGRATION_AVAILABLE:
                set_operation_step("Generating")
            get_logger().info("[Generating] - Generating PR review...")
            await self._generate_review()
            
            # Step 3: Process review data
            if DASHBOARD_INTEGRATION_AVAILABLE:
                set_operation_step("Processing") 
            get_logger().info("[Processing] - Processing generated review...")
            result = await self._process_review_data()
            
            # Step 4: Dev time estimation (with insights capture)
            if DASHBOARD_INTEGRATION_AVAILABLE:
                set_operation_step("DevTime")
            get_logger().info("[DevTime] - Estimating time savings...")
            dev_hours_saved, dev_time_insights = await self._estimate_dev_time_saved_with_insights(result)
            
            # Capture insights for dashboard
            if DASHBOARD_INTEGRATION_AVAILABLE:
                insights_data = {
                    'dev_time_analysis': dev_time_insights,
                    'review_analysis': dev_time_insights.get('ai_estimation_result', None) if dev_time_insights else None,
                    'review_generation': getattr(self, '_generation_insights', None)
                }
                await self._send_insights(insights_data)
            
            # Step 5: Send aggregated AI metrics
            if DASHBOARD_INTEGRATION_AVAILABLE:
                get_logger().info("[AI] - Sending aggregated AI metrics...")
                self._send_aggregated_ai_metrics(dev_hours_saved)
            
            # Step 6: Publishing
            if DASHBOARD_INTEGRATION_AVAILABLE:
                set_operation_step("Publishing")
            get_logger().info("[Publishing] - Publishing PR review...")
            await self._publish_review_result(result, dev_hours_saved)
            
            return result
            
        except Exception as e:
            get_logger().error(f"[Review] - Error in streamlined PR review workflow: {e}")
            raise

    async def _execute_legacy_workflow(self) -> None:
        """Main PR review logic (extracted for reuse with/without tracking)"""
        try:
            get_logger().info("[Review] - Starting legacy PR review workflow...")
            return await self._execute_review_logic()
        except Exception as e:
            get_logger().error(f"[Review] - Error in legacy PR review workflow: {e}")
            raise

    async def _execute_review_logic(self) -> None:
        """Main PR review logic (extracted for reuse with/without tracking)"""
        try:
            if not self.git_provider.get_files():
                get_logger().info(f"[Review] - PR has no files: {self.pr_url}, skipping review")
                return None

            if self.incremental.is_incremental and not self._can_run_incremental_review():
                return None

            # if isinstance(self.args, list) and self.args and self.args[0] == 'auto_approve':
            #     get_logger().info(f'[Review] - Auto approve flow PR: {self.pr_url} ...')
            #     self.auto_approve_logic()
            #     return None

            get_logger().info(f'[Review] - Reviewing PR: {self.pr_url} ...')
            relevant_configs = {'pr_reviewer': dict(get_settings().pr_reviewer),
                                'config': dict(get_settings().config)}
            get_logger().debug("[Review] - Relevant configs", artifacts=relevant_configs)

            # ticket extraction if exists
            get_logger().info("[Review] - Extracting and caching PR tickets...")
            await extract_and_cache_pr_tickets(self.git_provider, self.vars)

            if self.incremental.is_incremental and hasattr(self.git_provider, "unreviewed_files_set") and not self.git_provider.unreviewed_files_set:
                get_logger().info(f"[Review] - Incremental review enabled for {self.pr_url} but no new files found")
                previous_review_url = ""
                if hasattr(self.git_provider, "previous_review"):
                    previous_review_url = self.git_provider.previous_review.html_url
                if get_settings().config.publish_output:
                    self.git_provider.publish_comment(f"Incremental Review Skipped\n"
                                    f"No files were changed since the [previous PR Review]({previous_review_url})")
                return None

            if get_settings().config.publish_output and not get_settings().config.get('is_auto_command', False):
                get_logger().info("[Review] - Publishing temporary 'preparing review' message...")
                self.git_provider.publish_comment("Preparing review...", is_temporary=True)

            get_logger().info("[Review] - Generating AI review prediction...")
            await retry_with_fallback_models(self._prepare_prediction, model_type=ModelType.REGULAR, tool_name='pr_reviewer')
            if not self.prediction:
                get_logger().warning("[Review] - No prediction generated, removing initial comment")
                self.git_provider.remove_initial_comment()
                return None

            get_logger().info("[Review] - Preparing final PR review format...")
            pr_review = self._prepare_pr_review()
            get_logger().debug(f"[Review] - PR review output prepared", artifact=pr_review)

            if get_settings().config.publish_output:
                get_logger().info("[Review] - Publishing review to PR...")
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
                get_logger().info("[Review] - Review published successfully")
            else:
                get_logger().info("[Review] - Review output not published (disabled)")
                get_settings().data = {"artifact": pr_review}
                return pr_review
                
            return pr_review
        except Exception as e:
            get_logger().error(f"[Review] - Failed to review PR: {e}")
            raise

    async def _prepare_prediction(self, model: str) -> None:
        get_logger().info(f"[Review] - Fetching PR diff for model: {model}")
        self.patches_diff = await get_pr_diff(self.git_provider,
                                        self.token_handler,
                                        model,
                                        add_line_numbers_to_hunks=True,
                                        disable_extra_lines=False,)

        if self.patches_diff:
            get_logger().debug(f"[Review] - PR diff fetched successfully", diff=self.patches_diff)
            get_logger().info(f"[Review] - Generating AI prediction using model: {model}")
            self.prediction = await self._get_prediction(model)
        else:
            get_logger().warning(f"[Review] - Empty diff for PR: {self.pr_url}")
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
            if DASHBOARD_INTEGRATION_AVAILABLE:
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
                    
                    get_logger().info(f"[AI] - Metrics updated - Input: {input_tokens}, Output: {output_tokens}, "
                                    f"Calls: {totals['call_count']}, Failed: {totals['failed_calls']}")
                    
                    # Track AI metrics for this model
                    self._track_ai_metrics(model, {
                        'input_tokens': input_tokens,
                        'output_tokens': output_tokens
                    })
                    
                    # Track AI metrics - use either multi-model or single model update
                    if hasattr(self, 'ai_models_metrics') and self.ai_models_metrics:
                        # Multi-model tracking (prepare for future multi-model support)
                        update_operation_multi_model_ai_metrics(self.ai_models_metrics)
                    else:
                        # Single model tracking (current case)
                        update_operation_ai_metrics(model, input_tokens, output_tokens)
                    
                except Exception as e:
                    get_logger().debug(f"Failed to update dashboard AI metrics: {e}")
            
            return response
            
        except Exception as e:
            # Track failed AI call if dashboard is available
            if DASHBOARD_INTEGRATION_AVAILABLE:
                try:
                    # Estimate tokens for failed call
                    from pr_agent.algo.token_handler import TokenHandler
                    token_handler = TokenHandler()
                    estimated_input_tokens = token_handler.get_token_count_from_string(system_prompt + user_prompt)
                    estimated_output_tokens = 0  # No output on failure
                    
                    # Track failed metrics
                    self._track_ai_metrics(model, {
                        'input_tokens': estimated_input_tokens,
                        'output_tokens': estimated_output_tokens
                    })
                    
                    update_operation_ai_metrics(model, estimated_input_tokens, estimated_output_tokens)
                except Exception as dashboard_e:
                    get_logger().debug(f"Failed to track failed AI call metrics: {dashboard_e}")
            
            get_logger().error(f"[AI] - Failed to get AI prediction: {e}")
            raise

        return response
    
    async def _prepare_context_and_diff(self):
        """Prepare context and diff for review (Step 1 of streamlined workflow)"""
        try:
            # Extract tickets if they exist
            await extract_and_cache_pr_tickets(self.git_provider, self.vars)
            
            # Check if we can proceed with incremental review
            if self.incremental.is_incremental and not self._can_run_incremental_review():
                raise Exception("Cannot run incremental review - missing required data")
            
            if self.incremental.is_incremental and hasattr(self.git_provider, "unreviewed_files_set") and not self.git_provider.unreviewed_files_set:
                get_logger().info(f"[Context] - Incremental review enabled but no new files found")
                previous_review_url = ""
                if hasattr(self.git_provider, "previous_review"):
                    previous_review_url = self.git_provider.previous_review.html_url
                if get_settings().config.publish_output:
                    self.git_provider.publish_comment(f"Incremental Review Skipped\n"
                                    f"No files were changed since the [previous PR Review]({previous_review_url})")
                raise Exception("No new files to review in incremental mode")
                
            get_logger().info(f"[Context] - Preparing context for PR: {self.pr_url}")
            
        except Exception as e:
            get_logger().error(f"[Context] - Failed to prepare context: {e}")
            raise
    
    async def _generate_review(self):
        """Generate the AI review (Step 2 of streamlined workflow)"""
        try:
            if not self.git_provider.get_files():
                raise Exception(f"PR has no files: {self.pr_url}")
            
            # Publish preparing message if not auto command
            if get_settings().config.publish_output and not get_settings().config.get('is_auto_command', False):
                self.git_provider.publish_comment("Preparing review...", is_temporary=True)
            
            # Generate prediction with fallback models
            await retry_with_fallback_models(self._prepare_prediction, model_type=ModelType.REGULAR, tool_name='pr_reviewer')
            
            if not self.prediction:
                self.git_provider.remove_initial_comment()
                raise Exception("Failed to generate review prediction")
            
            # Capture generation insights for dashboard
            self._generation_insights = {
                'prediction_length': len(self.prediction) if self.prediction else 0,
                'diff_length': len(self.patches_diff) if self.patches_diff else 0,
                'files_analyzed': len(self.git_provider.get_files()) if self.git_provider.get_files() else 0,
                'main_language': self.main_language,
                'review_type': 'incremental' if self.incremental.is_incremental else 'full'
            }
                
            get_logger().info(f"[Generating] - Review generation completed successfully")
            
        except Exception as e:
            get_logger().error(f"[Generating] - Failed to generate review: {e}")
            raise
    
    async def _process_review_data(self):
        """Process the generated review data (Step 3 of streamlined workflow)"""
        try:
            if not self.prediction:
                raise Exception("No prediction available to process")
            
            # Prepare the final PR review format
            pr_review = self._prepare_pr_review()
            get_logger().debug(f"[Processing] - PR review output prepared", artifact=pr_review)
            
            return pr_review
            
        except Exception as e:
            get_logger().error(f"[Processing] - Failed to process review data: {e}")
            raise
    
    async def _estimate_dev_time_saved_with_insights(self, review_result):
        """Estimate dev time saved with insights capture (Step 4 of streamlined workflow)"""
        try:
            get_logger().info("[DevTime] - Starting dev time estimation with insights...")
            
            # Calculate file metrics
            files_count = len(self.git_provider.get_files()) if self.git_provider.get_files() else 0
            
            # Try AI-powered estimation first if we have enough data
            if review_result and self.patches_diff:
                get_logger().info("[DevTime] - Using AI-powered time estimation...")
                
                # Calculate input/output tokens from the AI generation
                total_input_tokens = sum(data.get('input_tokens', 0) for data in self.ai_models_metrics.values())
                total_output_tokens = sum(data.get('output_tokens', 0) for data in self.ai_models_metrics.values())
                
                try:
                    # Get the FULL AI estimation result (not just the hours)
                    estimation_result = await self._estimate_review_dev_hours_saved_ai_full(
                        model=get_settings().config.model,
                        input_tokens=total_input_tokens,
                        output_tokens=total_output_tokens,
                        files_count=files_count,
                        diff=self.patches_diff,
                        review_content=review_result
                    )
                    
                    if estimation_result and 'final_assessment' in estimation_result:
                        # Extract the time estimate
                        dev_hours_saved = estimation_result['final_assessment'].get('total_developer_hours_saved', 1.0)
                        
                        # Send the complete AI estimation result as insights (review-specific)
                        # Include all AI analysis data and add additional metadata
                        dev_time_insights = dict(estimation_result)  # Copy all AI estimation fields
                        
                        # Add additional review-specific metrics
                        dev_time_insights['review_metrics'] = {
                            'estimated_hours': dev_hours_saved,
                            'files_reviewed': files_count,
                            'review_type': 'incremental' if self.incremental.is_incremental else 'full',
                            'model_used': get_settings().config.model,
                            'language': self.main_language,
                            'lines_in_diff': len(self.patches_diff.split('\n')) if self.patches_diff else 0,
                            'review_length': len(review_result) if review_result else 0
                        }
                        
                        get_logger().info(f"[DevTime] - AI estimation completed: {dev_hours_saved:.2f} hours saved", 
                                        artifacts={
                                            'confidence': estimation_result['final_assessment'].get('confidence_level', 'medium'),
                                            'key_factors': estimation_result['final_assessment'].get('key_factors', [])
                                        })
                        
                        return dev_hours_saved, dev_time_insights
                        
                except Exception as ai_error:
                    get_logger().warning(f"[DevTime] - AI estimation failed, using fallback: {ai_error}")
            
            # Fallback to heuristic estimation
            get_logger().info("[DevTime] - Using heuristic time estimation...")
            model = get_settings().config.model
            dev_hours_saved = self._estimate_review_dev_hours_saved(
                model=model,
                files_count=files_count
            )
            
            # Build basic insights for heuristic estimation
            dev_time_insights = {
                'estimation_type': 'heuristic_fallback',
                'review_metrics': {
                    'estimated_hours': dev_hours_saved,
                    'files_reviewed': files_count,
                    'review_type': 'incremental' if self.incremental.is_incremental else 'full',
                    'model_used': model,
                    'language': self.main_language,
                    'fallback_reason': 'Missing diff or review content for AI estimation'
                }
            }
            
            get_logger().info(f"[DevTime] - Estimated {dev_hours_saved:.2f} hours saved (heuristic)")
            return dev_hours_saved, dev_time_insights
            
        except Exception as e:
            get_logger().error(f"[DevTime] - Failed to estimate dev time saved: {e}")
            return 0.5, None  # Return reasonable fallback with error
    
    async def _send_insights(self, insights_data: dict):
        """Send insights to dashboard (Step 4.5 of streamlined workflow)"""
        try:
            get_logger().info(f"[Insights] - DEBUG: _send_insights called with data keys: {list(insights_data.keys()) if insights_data else 'None'}")
            
            from pr_agent.log.dashboard_client import get_dashboard_client
            
            dashboard_client = get_dashboard_client()
            get_logger().info(f"[Insights] - DEBUG: Dashboard client obtained: {dashboard_client is not None}")
            get_logger().info(f"[Insights] - DEBUG: Dashboard client enabled: {dashboard_client._enabled if dashboard_client else 'None'}")
            
            if not dashboard_client or not dashboard_client._enabled:
                get_logger().debug("[Insights] - Dashboard client not available, skipping insights")
                return
            
            # Clean up None values to avoid sending empty insights
            cleaned_insights = {}
            for category, data in insights_data.items():
                if data is not None:
                    cleaned_insights[category] = data
            
            get_logger().info(f"[Insights] - DEBUG: Cleaned insights keys: {list(cleaned_insights.keys())}")
            
            if not cleaned_insights:
                get_logger().debug("[Insights] - No insights data to send")
                return
            
            get_logger().info(f"[Insights] - Sending insights to dashboard: {list(cleaned_insights.keys())}", 
                             artifacts={'insights_categories': list(cleaned_insights.keys())})
            
            get_logger().info("[Insights] - DEBUG: About to call dashboard_client.update_operation_insights")
            await dashboard_client.update_operation_insights(cleaned_insights)
            get_logger().info("[Insights] - Successfully sent insights to dashboard")
            
        except Exception as e:
            get_logger().warning(f"[Insights] - Failed to send insights to dashboard: {e}")
            import traceback
            get_logger().warning(f"[Insights] - Traceback: {traceback.format_exc()}")
            # Don't fail the operation if insights sending fails
    
    def _track_ai_metrics(self, model: str, token_usage: dict):
        """Track AI metrics for aggregated reporting"""
        try:
            if not hasattr(self, 'ai_models_metrics'):
                self.ai_models_metrics = {}
            
            input_tokens = token_usage.get('input_tokens', 0)
            output_tokens = token_usage.get('output_tokens', 0)
            
            if model not in self.ai_models_metrics:
                self.ai_models_metrics[model] = {
                    'input_tokens': 0,
                    'output_tokens': 0
                }
            
            self.ai_models_metrics[model]['input_tokens'] += input_tokens
            self.ai_models_metrics[model]['output_tokens'] += output_tokens
            
            get_logger().debug(f"[AI] - Tracked metrics for {model}: +{input_tokens}in/+{output_tokens}out")
            
        except Exception as e:
            get_logger().debug(f"[AI] - Failed to track metrics: {e}")
    
    def _send_aggregated_ai_metrics(self, estimated_dev_hours_saved: float = None):
        """Send aggregated AI metrics to dashboard (Step 5 of streamlined workflow)"""
        try:
            if not DASHBOARD_INTEGRATION_AVAILABLE or not hasattr(self, 'ai_models_metrics'):
                return
            
            if self.ai_models_metrics:
                # Send multi-model metrics
                update_operation_multi_model_ai_metrics(
                    self.ai_models_metrics, 
                    estimated_dev_hours_saved
                )
                get_logger().info(f"[AI] - Sent aggregated metrics for {len(self.ai_models_metrics)} model(s)")
            
        except Exception as e:
            get_logger().debug(f"[AI] - Failed to send aggregated metrics: {e}")
    
    async def _publish_review_result(self, review_result, dev_hours_saved):
        """Publish the review result (Step 6 of streamlined workflow)"""
        try:
            if not review_result:
                get_logger().warning(f"[Publishing] - No review result to publish")
                return
            
            if get_settings().config.publish_output:
                # Publish the review
                if get_settings().pr_reviewer.persistent_comment and not self.incremental.is_incremental:
                    final_update_message = get_settings().pr_reviewer.final_update_message
                    self.git_provider.publish_persistent_comment(
                        review_result,
                        initial_header=f"{PRReviewHeader.REGULAR.value} 🔍",
                        update_header=True,
                        final_update_message=final_update_message,
                    )
                else:
                    self.git_provider.publish_comment(review_result)

                self.git_provider.remove_initial_comment()
                get_logger().info(f"[Publishing] - Review published successfully")
            else:
                get_logger().info(f"[Publishing] - Review output not published (disabled)")
                get_settings().data = {"artifact": review_result}
                
        except Exception as e:
            get_logger().error(f"[Publishing] - Failed to publish review: {e}")
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

    async def _estimate_review_dev_hours_saved_ai_full(self, model: str, input_tokens: int = None, 
                                                      output_tokens: int = None, files_count: int = 0,
                                                      diff: str = None, review_content: str = None) -> dict:
        """
        Estimate developer hours saved using AI-powered analysis - returns full AI estimation result
        """
        try:
            if diff and review_content:
                from pr_agent.algo.dev_time_estimator import DevTimeEstimator
                
                estimator = DevTimeEstimator(self.ai_handler, self.token_handler, self._track_ai_metrics)
                
                # Extract line counts from diff
                lines_added = 0
                lines_deleted = 0
                if diff:
                    for line in diff.split('\n'):
                        if line.startswith('+') and not line.startswith('+++'):
                            lines_added += 1
                        elif line.startswith('-') and not line.startswith('---'):
                            lines_deleted += 1
                
                get_logger().info(f"[DevTime] - Making AI call for review time estimation using model: {model}")
                
                # Get the FULL AI estimation result
                estimation_result = await estimator.estimate_review_time_savings(
                    diff=diff,
                    ai_review_content=review_content,
                    language=self.main_language,
                    files_changed=files_count,
                    lines_added=lines_added,
                    lines_deleted=lines_deleted,
                    model=model
                )
                
                get_logger().info(f"[DevTime] - Full AI estimation result received", 
                                artifacts={'estimation_result': estimation_result})
                
                return estimation_result
            
            # Fall back to None if no data
            return None
            
        except Exception as e:
            get_logger().debug(f"AI time estimation failed: {e}")
            return None

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
            
            estimator = DevTimeEstimator(self.ai_handler, self.token_handler, self._track_ai_metrics)
            
            # Extract line counts from diff
            lines_added = 0
            lines_deleted = 0
            if diff:
                for line in diff.split('\n'):
                    if line.startswith('+') and not line.startswith('+++'):
                        lines_added += 1
                    elif line.startswith('-') and not line.startswith('---'):
                        lines_deleted += 1
            
            # Use the general dev time estimation prompt for review
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
                
                get_logger().info(f"AI-powered review time estimation: {estimated_hours} hours (confidence: {confidence})", 
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
