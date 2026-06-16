import asyncio
import copy
import difflib
import re
import textwrap
import traceback
from datetime import datetime
from functools import partial
from typing import Dict, List, Optional

from jinja2 import Environment, StrictUndefined

from pr_agent.algo import MAX_TOKENS
from pr_agent.algo.ai_handlers.base_ai_handler import BaseAiHandler
from pr_agent.algo.ai_handlers.litellm_ai_handler import LiteLLMAIHandler
from pr_agent.algo.git_patch_processing import decouple_and_convert_to_hunks_with_lines_numbers
from pr_agent.algo.pr_processing import (add_ai_metadata_to_diff_files,
                                         get_pr_diff, get_pr_multi_diffs,
                                         retry_with_fallback_models,
                                         get_pr_context)
from pr_agent.algo.token_handler import TokenHandler
from pr_agent.algo.utils import (ModelType, load_yaml, replace_code_tags,
                                 show_relevant_configurations, get_max_tokens, clip_tokens, get_model)
from pr_agent.config_loader import get_settings
from pr_agent.git_providers import (AzureDevopsProvider, GithubProvider,
                                    GitLabProvider, get_git_provider,
                                    get_git_provider_with_context)
from pr_agent.git_providers.git_provider import get_main_pr_language, GitProvider
from pr_agent.log import get_logger
from pr_agent.servers.help import HelpMessage
from pr_agent.tools.pr_description import insert_br_after_x_chars

# Dashboard integration imports
try:
    from pr_agent.log.job_context import (
        operation_context, OperationType, 
        job_context, JobType, 
        set_operation_step, update_operation_multi_model_ai_metrics,
        extract_repository_from_url, update_operation_status
    )
    DASHBOARD_INTEGRATION_AVAILABLE = True
except ImportError:
    DASHBOARD_INTEGRATION_AVAILABLE = False
    get_logger().debug("Dashboard integration not available for PR Code Suggestions tool")


class PRCodeSuggestions:
    def __init__(self, pr_url: str, args: list = None, ai_handler: BaseAiHandler = LiteLLMAIHandler, cli_mode: bool = False):
        self.pr_url = pr_url
        self.cli_mode = cli_mode
        
        # Multi-model AI metrics tracking
        self.ai_models_metrics = {}  # {"model_name": {"input_tokens": int, "output_tokens": int}}
        
        # Initialize other attributes
        self.prediction = ""
        self.can_add_test_class = False
        self.num_code_suggestions = 0
        self.patches_diff = ""
        self.progress_response = None

        self.git_provider = get_git_provider_with_context(pr_url)
        self.main_language = get_main_pr_language(
            self.git_provider.get_languages(), self.git_provider.get_files()
        )

        # limit context specifically for the improve command, which has hard input to parse:
        max_context_tokens_improve = get_settings().pr_code_suggestions.get("max_context_tokens", 0)
        if max_context_tokens_improve:
            MAX_CONTEXT_TOKENS_IMPROVE = max_context_tokens_improve
            if get_settings().config.max_model_tokens > MAX_CONTEXT_TOKENS_IMPROVE:
                get_logger().info(f"Setting max_model_tokens to {MAX_CONTEXT_TOKENS_IMPROVE} for PR improve")
                get_settings().config.max_model_tokens_original = get_settings().config.max_model_tokens
                get_settings().config.max_model_tokens = MAX_CONTEXT_TOKENS_IMPROVE

        num_code_suggestions = int(get_settings().pr_code_suggestions.get("num_code_suggestions_per_chunk", 4))

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
        self.pr_description, self.pr_description_files = (
            self.git_provider.get_pr_description(split_changes_walkthrough=True))
        if (self.pr_description_files and get_settings().get("config.is_auto_command", False) and
                get_settings().get("config.enable_ai_metadata", False)):
            add_ai_metadata_to_diff_files(self.git_provider, self.pr_description_files)
            get_logger().debug(f"AI metadata added to the this command")
        else:
            get_settings().set("config.enable_ai_metadata", False)
            get_logger().debug(f"AI metadata is disabled for this command")

        # Load best practices from repository
        from pr_agent.algo.utils import get_best_practices_content
        best_practices_content = get_best_practices_content(self.git_provider)
        
        self.vars = {
            "title": self.git_provider.pr.title,
            "branch": self.git_provider.get_pr_branch(),
            "description": self.pr_description,
            "language": self.main_language,
            "diff": "",  # empty diff for initial calculation
            "diff_no_line_numbers": "",  # empty diff for initial calculation
            "num_code_suggestions": num_code_suggestions,
            "extra_instructions": get_settings().pr_code_suggestions.extra_instructions,
            "commit_messages_str": self.git_provider.get_commit_messages(),
            "relevant_best_practices": "",  # Legacy field - kept for compatibility
            "best_practices": best_practices_content,  # New field for best practices content
            "is_ai_metadata": get_settings().get("config.enable_ai_metadata", False),
            "focus_only_on_problems": get_settings().get("pr_code_suggestions.focus_only_on_problems", False),
            "date": datetime.now().strftime('%Y-%m-%d'),
            'duplicate_prompt_examples': get_settings().config.get('duplicate_prompt_examples', False),
            "include_context": get_settings().get("csharp_code_context_service.enabled", False),
            "context": "" # context empty for initial calculation
        }

        if get_settings().pr_code_suggestions.get("decouple_hunks", True):
            self.pr_code_suggestions_prompt_system = get_settings().pr_code_suggestions_prompt.system
            self.pr_code_suggestions_prompt_user = get_settings().pr_code_suggestions_prompt.user
        else:
            self.pr_code_suggestions_prompt_system = get_settings().pr_code_suggestions_prompt_not_decoupled.system
            self.pr_code_suggestions_prompt_user = get_settings().pr_code_suggestions_prompt_not_decoupled.user

        self.token_handler = TokenHandler(self.git_provider.pr,
                                          self.vars,
                                          self.pr_code_suggestions_prompt_system,
                                          self.pr_code_suggestions_prompt_user)

        self.progress = f"## Generating PR code suggestions\n\n"
        self.progress += f"""\nWork in progress ...<br>\n<img src="https://codium.ai/images/pr_agent/dual_ball_loading-crop.gif" width=48>"""
        self.progress_response = None

    async def run(self) -> bool:
        """Main entry point for code suggestions with dashboard operation tracking"""
        get_logger().info('Starting comprehensive code suggestions operation...')
        
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
                    operation_type=OperationType.GENERATING_SUGGESTIONS,
                    command="improve",
                    repository=repository,
                    pr_url=self.pr_url,
                    installation_id=getattr(self.git_provider, 'installation_id', None),
                    sender=getattr(self.git_provider, 'sender', None)
                )
            except Exception as e:
                get_logger().warning(f"Dashboard operation context setup failed, continuing without tracking: {e}")
                # Fall through to execute without tracking
                get_logger().debug("Executing code suggestions without dashboard tracking (context setup failed)")
                return await self._run_without_tracking()
            
            # Execute with dashboard tracking - let operation failures be tracked
            with operation_context_manager as operation_id:
                get_logger().debug(f"Code suggestions operation started with ID: {operation_id}")
                return await self._run_with_tracking(operation_id)
        
        # Execute without operation tracking (dashboard disabled)
        get_logger().debug("Executing code suggestions without dashboard tracking (dashboard disabled)")
        return await self._run_without_tracking()

    async def _fetch_context_and_diff(self):
        """Stage 1: Fetch PR diff and context data"""
        try:
            # Get PR diff using existing logic from prepare_prediction_main
            get_logger().info('[Context] - Fetching diff...')
            model = get_settings().config.model  # Use default model for tokenization
            
            if get_settings().pr_code_suggestions.decouple_hunks:
                self.patches_diff_list = await get_pr_multi_diffs(self.git_provider,
                                                            self.token_handler,
                                                            model,
                                                            max_calls=get_settings().pr_code_suggestions.max_number_of_calls,
                                                            add_line_numbers=True)
                self.patches_diff_list_no_line_numbers = self.remove_line_numbers(self.patches_diff_list)
            else:
                self.patches_diff_list_no_line_numbers = await get_pr_multi_diffs(self.git_provider,
                                                                            self.token_handler,
                                                                            model,
                                                                            max_calls=get_settings().pr_code_suggestions.max_number_of_calls,
                                                                            add_line_numbers=False)
                self.patches_diff_list = await self.convert_to_decoupled_with_line_numbers(
                    self.patches_diff_list_no_line_numbers, model)
                if not self.patches_diff_list:
                    self.patches_diff_list = await get_pr_multi_diffs(self.git_provider,
                                                                self.token_handler,
                                                                model,
                                                                max_calls=get_settings().pr_code_suggestions.max_number_of_calls,
                                                                add_line_numbers=True)

            # Fetch context if enabled
            if get_settings().csharp_code_context_service.enabled:
                get_logger().info('[Context] - Fetching additional code context...')
                self.context_data = await get_pr_context(self.git_provider)
                get_logger().info(f"[Context] - Code context retrieved successfully")
            else:
                get_logger().info('[Context] - Code context fetch is disabled')
                self.context_data = ""

            if not self.patches_diff_list:
                get_logger().warning(f"[Context] - Empty PR diff list")
                return None
                
            get_logger().debug(f"[Context] - Processing {len(self.patches_diff_list)} diff chunks")
            return {"patches_fetched": True, "context_fetched": bool(self.context_data)}
            
        except Exception as e:
            get_logger().error(f"[Context] - Failed to fetch context and diff: {e}")
            raise
    
    async def _generate_suggestions_with_data(self, data):
        """Stage 2: Generate AI suggestions"""
        try:
            # Log filtering configuration at start
            score_threshold = max(1, int(get_settings().pr_code_suggestions.suggestions_score_threshold))
            commitable_enabled = get_settings().pr_code_suggestions.commitable_code_suggestions
            
            get_logger().info('[Generating] - Starting AI code suggestions generation...')
            get_logger().debug(f"[Filtering] - Score threshold: {score_threshold}, Commitable: {commitable_enabled}")
            
            model = get_settings().config.model
            
            # Generate suggestions using existing logic from prepare_prediction_main
            # Skip self-reflection here since it's handled in Stage 3
            if get_settings().pr_code_suggestions.parallel_calls:
                prediction_list = await asyncio.gather(
                    *[self._get_prediction(model, patches_diff, patches_diff_no_line_numbers, skip_self_reflection=True) for
                      patches_diff, patches_diff_no_line_numbers in
                      zip(self.patches_diff_list, self.patches_diff_list_no_line_numbers)])
                self.prediction_list = prediction_list
            else:
                prediction_list = []
                for patches_diff, patches_diff_no_line_numbers in zip(self.patches_diff_list, self.patches_diff_list_no_line_numbers):
                    prediction = await self._get_prediction(model, patches_diff, patches_diff_no_line_numbers, skip_self_reflection=True)
                    prediction_list.append(prediction)

            # Consolidate suggestions using existing logic
            result_data = {"code_suggestions": []}
            for j, predictions in enumerate(prediction_list):
                if "code_suggestions" in predictions:
                    score_threshold = max(1, int(get_settings().pr_code_suggestions.suggestions_score_threshold))
                    for i, prediction in enumerate(predictions["code_suggestions"]):
                        try:
                            score = int(prediction.get("score", 1))
                            file_name = prediction.get("relevant_file", "unknown")
                            summary = prediction.get("one_sentence_summary", "no summary")[:50]
                            
                            # Add all suggestions to result_data - filtering will happen after reflection
                            result_data["code_suggestions"].append(prediction)
                            get_logger().debug(f"[Generating] - Added suggestion {i+1} in call {j+1}: score={score} | {file_name} | {summary}...")
                        except Exception as e:
                            get_logger().error(f"[Generating] - Error processing suggestion {i} in call {j}: {e}",
                                               artifact={"prediction": prediction})
            
            get_logger().info(f"[Generating] - Generated {len(result_data.get('code_suggestions', []))} total suggestions")
            self.data = result_data
            return result_data
            
        except Exception as e:
            get_logger().error(f"[Generating] - Failed to generate suggestions: {e}")
            raise
    
    async def _self_reflect_on_result(self, result):
        """Stage 3: Self-reflect on suggestions"""
        try:
            get_logger().info('[Reflecting] - Starting self-reflection on generated suggestions...')
            # Use existing self-reflection logic from _get_prediction
            if not result or not result.get('code_suggestions'):
                get_logger().info('[Reflecting] - No suggestions to reflect on, skipping')
                return result
                
            # Call self-reflection for each suggestion (simplified version)
            model = get_settings().config.model
            patches_diff = "\n\n".join(self.patches_diff_list) if self.patches_diff_list else ""
            
            # Perform self-reflection using existing logic
            get_logger().info(f'[Reflecting] - Calling self_reflect_on_suggestions with {len(result["code_suggestions"])} suggestions')
            response_reflect = await self.self_reflect_on_suggestions(
                result['code_suggestions'],
                patches_diff,
                model
            )
            get_logger().debug(f'[Reflecting] - Self-reflection returned: {len(response_reflect) if response_reflect else 0} characters')

            if response_reflect:
                get_logger().debug('[Reflecting] - Analyzing reflection response and updating scores...')
                await self.analyze_self_reflection_response(result, response_reflect)
                    
            else:
                get_logger().warning('[Reflecting] - Reflection failed, applying default scores')
                # Default scores if reflection fails
                for suggestion in result["code_suggestions"]:
                    suggestion["score"] = 7
                    suggestion["score_why"] = ""
            
            # FINAL FILTERING: Apply score threshold after all reflection stages are complete
            score_threshold = max(1, int(get_settings().pr_code_suggestions.suggestions_score_threshold))
            get_logger().info(f"[Final Filtering] - Applying final score threshold: {score_threshold}")
            
            original_count = len(result.get("code_suggestions", []))
            filtered_suggestions = []
            
            for i, suggestion in enumerate(result.get("code_suggestions", [])):
                current_score = suggestion.get("score", 0)
                file_name = suggestion.get("relevant_file", "unknown")
                summary = suggestion.get("one_sentence_summary", "no summary")[:50]
                
                if current_score >= score_threshold:
                    filtered_suggestions.append(suggestion)
                    get_logger().info(f"[Final Filtering] - ✅ ACCEPTED suggestion {i+1}: score={current_score} >= threshold={score_threshold} | {file_name} | {summary}...")
                else:
                    get_logger().info(f"[Final Filtering] - ❌ REJECTED suggestion {i+1}: score={current_score} < threshold={score_threshold} | {file_name} | {summary}...")
            
            result["code_suggestions"] = filtered_suggestions
            final_count = len(filtered_suggestions)
            
            get_logger().info(f"[Final Filtering] - Filtered suggestions: {original_count} → {final_count} (threshold: {score_threshold})")
            get_logger().info('[Reflecting] - Self-reflection completed successfully')
            return result
            
        except Exception as e:
            get_logger().error(f"[Reflecting] - Failed to self-reflect on suggestions: {e}")
            # Return original result if reflection fails
            return result
    
    async def _publish_result(self, result, dev_hours_saved):
        """Stage 5: Publish suggestions"""
        get_logger().info('[Publishing] - Starting to publish code suggestions')
        
        try:
            if result and result.get("code_suggestions"):
                await self.dual_publishing(result)
                get_logger().info(f'[Publishing] - Successfully published {len(result.get("code_suggestions", []))} code suggestions')
            else:
                await self.publish_no_suggestions()
                get_logger().info('[Publishing] - Published no suggestions message')
                
            # Send aggregated AI metrics after successful publishing
            if DASHBOARD_INTEGRATION_AVAILABLE:
                self._send_aggregated_ai_metrics(estimated_dev_hours_saved=dev_hours_saved)
            
        except Exception as e:
            get_logger().error(f'[Publishing] - Failed to publish suggestions: {e}')
            
            # Still send metrics even if publishing fails
            if DASHBOARD_INTEGRATION_AVAILABLE:
                self._send_aggregated_ai_metrics(estimated_dev_hours_saved=dev_hours_saved)
            
            raise
    
    async def _estimate_dev_time_saved(self, final_result):
        """Stage 4: Estimate developer time saved with proper operation tracking"""
        try:
            get_logger().info("[DevTime] - Starting AI-powered developer time saved estimation...")
            
            if not final_result or not final_result.get('code_suggestions'):
                get_logger().warning("[DevTime] - No suggestions available for time estimation")
                return 0.0
            
            # Get required data for estimation
            suggestions_count = len(final_result.get('code_suggestions', []))
            files_count = len(self.git_provider.get_files()) if hasattr(self, 'git_provider') else 1
            
            # Build content for AI estimation
            suggestions_content = str(final_result.get('code_suggestions', []))
            diff_content = "\n\n".join(self.patches_diff_list) if hasattr(self, 'patches_diff_list') and self.patches_diff_list else ''
            
            get_logger().info(f"[DevTime] - Time estimation inputs: {suggestions_count} suggestions, {files_count} files")
            
            # Let DevTimeEstimator choose the model based on config, fall back to reasoning model if needed
            estimation_model = get_settings().get("pr_dev_time_estimation.model", "")
            if estimation_model:
                model = estimation_model
                get_logger().info(f"[DevTime] - Using configured dev time estimation model: {model}")
            else:
                model = get_model('model_reasoning')
                get_logger().info(f"[DevTime] - No config model found, using reasoning model for dev time estimation: {model}")
            
            try:
                dev_hours_saved = await self._estimate_suggestions_dev_hours_saved_ai(
                    model=model,
                    input_tokens=0,  # Will be updated inside the method
                    output_tokens=0,  # Will be updated inside the method
                    files_count=files_count,
                    diff=diff_content,
                    suggestions_content=suggestions_content,
                    suggestions_count=suggestions_count,
                    track_metrics=True  # Enable AI metrics tracking for this operation
                )
                
                get_logger().info(f"[DevTime] - AI estimation completed: {dev_hours_saved} hours", 
                                 artifacts={
                                     'suggestions_count': suggestions_count,
                                     'files_count': files_count,
                                     'estimated_hours': dev_hours_saved,
                                     'model_used': model
                                 })
                
                return dev_hours_saved
                
            except Exception as ai_error:
                get_logger().warning(f"[DevTime] - AI estimation failed, using heuristic fallback: {ai_error}")
                
                # Fallback to heuristic estimation
                heuristic_result = self._estimate_suggestions_dev_hours_saved(
                    files_count, 
                    2000,  # Estimated tokens for heuristic
                    model
                )
                
                get_logger().info(f"[DevTime] - Heuristic estimation: {heuristic_result} hours")
                return heuristic_result
                
        except Exception as e:
            get_logger().error(f"[DevTime] - Dev time estimation operation failed: {e}")
            raise

    async def _estimate_dev_time_saved_with_insights(self, final_result):
        """Stage 4: Estimate developer time saved with full insights capture"""
        try:
            get_logger().info("[DevTime] - Starting AI-powered developer time saved estimation with insights...")
            
            if not final_result or not final_result.get('code_suggestions'):
                get_logger().warning("[DevTime] - No suggestions available for time estimation")
                return 0.0, None
            
            # Get required data for estimation
            suggestions_count = len(final_result.get('code_suggestions', []))
            files_count = len(self.git_provider.get_files()) if hasattr(self, 'git_provider') else 1
            
            # Build content for AI estimation
            suggestions_content = str(final_result.get('code_suggestions', []))
            diff_content = "\n\n".join(self.patches_diff_list) if hasattr(self, 'patches_diff_list') and self.patches_diff_list else ''
            
            get_logger().info(f"[DevTime] - Time estimation inputs: {suggestions_count} suggestions, {files_count} files")
            
            # Let DevTimeEstimator choose the model based on config, fall back to reasoning model if needed
            estimation_model = get_settings().get("pr_dev_time_estimation.model", "")
            if estimation_model:
                model = estimation_model
                get_logger().info(f"[DevTime] - Using configured dev time estimation model: {model}")
            else:
                model = get_model('model_reasoning')
                get_logger().info(f"[DevTime] - No config model found, using reasoning model for dev time estimation: {model}")
            
            # Initialize AI time estimator with callback for metrics tracking
            try:
                from pr_agent.algo.dev_time_estimator import DevTimeEstimator
                estimator = DevTimeEstimator(self.ai_handler, self.token_handler, self._track_ai_metrics)
                
            except Exception as e:
                get_logger().error("❌ Failed to initialize DevTimeEstimator", 
                                  artifacts={'error': str(e), 'error_type': type(e).__name__})
                return 0.0, None

            # Make AI estimation call with full insights
            try:
                get_logger().info("Making AI call for time savings estimation with insights...")
                
                estimation_result = await estimator.estimate_suggestions_time_savings(
                    diff=diff_content,
                    ai_suggestions_content=suggestions_content,
                    language=self.main_language,
                    files_changed=files_count,
                    lines_added=len([line for line in diff_content.split('\n') if line.startswith('+')]),
                    lines_deleted=len([line for line in diff_content.split('\n') if line.startswith('-')]),
                    suggestions_count=suggestions_count,
                    model=model
                )
                
                # Extract final hours estimate
                estimated_hours = 0.0
                if estimation_result and 'final_assessment' in estimation_result:
                    estimated_hours = estimation_result['final_assessment'].get('total_developer_hours_saved', 0.0)
                    # Cap the result at reasonable bounds (allow negative values for time wasted)
                    estimated_hours = max(-16.0, min(16.0, float(estimated_hours)))
                
                get_logger().info(f"[DevTime] - AI time estimation with insights completed: {estimated_hours} hours", 
                                 artifacts={'full_estimation_result': estimation_result})
                
                return estimated_hours, estimation_result
                
            except Exception as e:
                get_logger().error("❌ AI time estimation call failed", 
                                  artifacts={'error': str(e), 'error_type': type(e).__name__})
                return 0.0, None
                
        except Exception as e:
            get_logger().error(f"[DevTime] - Dev time estimation with insights failed: {e}")
            return 0.0, None

    async def _send_insights(self, insights_data: dict):
        """Send AI insights to dashboard for analysis and visualization"""
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
    
    async def _run_with_tracking(self, operation_id: str) -> bool:
        """Run code suggestions with dashboard operation tracking"""
        try:
            # Update operation status to processing
            update_operation_status("processing")
            
            # Execute the main streamlined workflow
            result = await self._execute_streamlined_workflow()
            
            # Update operation status based on result
            if result:
                update_operation_status("completed", result_data={
                    "suggestions_generated": True,
                    "suggestions_count": len(result.get('code_suggestions', [])) if result else 0
                })
                get_logger().info(f"Code suggestions operation {operation_id} completed successfully")
                return True
            else:
                update_operation_status("failed", error_details="Code suggestions generation returned no result")
                get_logger().warning(f"Code suggestions operation {operation_id} completed with no result")
                return False
            
        except Exception as e:
            # Update operation status to failed
            update_operation_status("failed", error_details=str(e))
            get_logger().error(f"Code suggestions operation {operation_id} failed: {e}")
            raise

    async def _execute_streamlined_workflow(self):
        """Execute the streamlined code suggestions workflow"""
        try:
            # Step 1: Context and diff
            if DASHBOARD_INTEGRATION_AVAILABLE:
                set_operation_step("Context")
            await self._fetch_context_and_diff()
            
            # Step 2: Generate suggestions
            if DASHBOARD_INTEGRATION_AVAILABLE:
                set_operation_step("Generating")
            result = await self._generate_suggestions_with_data({})
            
            # Step 3: Self-reflection (if needed)
            if DASHBOARD_INTEGRATION_AVAILABLE:
                set_operation_step("Reflecting") 
            result = await self._self_reflect_on_result(result)
            
            # Step 4: Time estimation (with insights capture)
            if DASHBOARD_INTEGRATION_AVAILABLE:
                set_operation_step("DevTime")
            dev_hours_saved, dev_time_insights = await self._estimate_dev_time_saved_with_insights(result)
            
            # Capture insights for dashboard
            if DASHBOARD_INTEGRATION_AVAILABLE:
                insights_data = {
                    'dev_time_analysis': dev_time_insights,
                    'self_reflection': getattr(self, '_self_reflection_insights', None)
                }
                await self._send_insights(insights_data)
            
            # Step 5: Publishing
            if DASHBOARD_INTEGRATION_AVAILABLE:
                set_operation_step("Publishing")
            await self._publish_result(result, dev_hours_saved)
            
            return result
            
        except Exception as e:
            get_logger().error(f"Error in streamlined code suggestions workflow: {e}")
            raise

    async def _run_without_tracking(self) -> bool:
        """Run code suggestions without dashboard tracking (fallback)"""
        return await self._execute_legacy_workflow()

    async def _execute_legacy_workflow(self) -> bool:
        try:
            if not self.git_provider.get_files():
                get_logger().info(f"PR has no files: {self.pr_url}, skipping code suggestions")
                return False

            get_logger().info('Generating code suggestions for PR...')
            relevant_configs = {'pr_code_suggestions': dict(get_settings().pr_code_suggestions),
                                'config': dict(get_settings().config)}
            get_logger().debug("Relevant configs", artifacts=relevant_configs)

            # publish "Preparing suggestions..." comments
            if (get_settings().config.publish_output and get_settings().config.publish_output_progress and
                    not get_settings().config.get('is_auto_command', False)):
                if self.git_provider.is_supported("gfm_markdown"):
                    self.progress_response = self.git_provider.publish_comment(self.progress)
                else:
                    self.git_provider.publish_comment("Preparing suggestions...", is_temporary=True)

            # # call the model to get the suggestions, and self-reflect on them
            # if not self.is_extended:
            #     data = await retry_with_fallback_models(self._prepare_prediction, model_type=ModelType.REGULAR)
            # else:
            get_logger().info('Preparing predicitions')
            data = await retry_with_fallback_models(self.prepare_prediction_main, model_type=ModelType.REGULAR, tool_name='pr_code_suggestions')
            if not data:
                data = {"code_suggestions": []}
            self.data = data

            # Handle the case where the PR has no suggestions
            if (data is None or 'code_suggestions' not in data or not data['code_suggestions']):
                await self.publish_no_suggestions()
                return False

            # publish the suggestions
            if get_settings().config.publish_output:
                # If a temporary comment was published, remove it
                self.git_provider.remove_initial_comment()

                # Publish table summarized suggestions
                if ((not get_settings().pr_code_suggestions.commitable_code_suggestions) and
                        self.git_provider.is_supported("gfm_markdown")):

                    # generate summarized suggestions
                    pr_body = self.generate_summarized_suggestions(data)
                    get_logger().debug(f"PR output", artifact=pr_body)

                    # require self-review
                    if get_settings().pr_code_suggestions.demand_code_suggestions_self_review:
                        pr_body = await self.add_self_review_text(pr_body)

                    # add usage guide
                    if (get_settings().pr_code_suggestions.enable_chat_text and get_settings().config.is_auto_command
                            and isinstance(self.git_provider, GithubProvider)):
                        pr_body += "\n\n>💡 Need additional feedback ? start a [PR chat](https://chromewebstore.google.com/detail/ephlnjeghhogofkifjloamocljapahnl) \n\n"
                    if get_settings().pr_code_suggestions.enable_help_text:
                        pr_body += "<hr>\n\n<details> <summary><strong>💡 Tool usage guide:</strong></summary><hr> \n\n"
                        pr_body += HelpMessage.get_improve_usage_guide()
                        pr_body += "\n</details>\n"

                    # Output the relevant configurations if enabled
                    if get_settings().get('config', {}).get('output_relevant_configurations', False):
                        pr_body += show_relevant_configurations(relevant_section='pr_code_suggestions')

                    # publish the PR comment
                    if get_settings().pr_code_suggestions.persistent_comment: # true by default
                        self.publish_persistent_comment_with_history(self.git_provider,
                                                                     pr_body,
                                                                     initial_header="## PR Code Suggestions ✨",
                                                                     update_header=True,
                                                                     name="suggestions",
                                                                     final_update_message=False,
                                                                     max_previous_comments=get_settings().pr_code_suggestions.max_history_len,
                                                                     progress_response=self.progress_response)
                    else:
                        if self.progress_response:
                            self.git_provider.edit_comment(self.progress_response, body=pr_body)
                        else:
                            self.git_provider.publish_comment(pr_body)

                    # dual publishing mode
                    if int(get_settings().pr_code_suggestions.dual_publishing_score_threshold) > 0:
                        await self.dual_publishing(data)
                else:
                    await self.push_inline_code_suggestions(data)
                    if self.progress_response:
                        self.git_provider.remove_comment(self.progress_response)
            else:
                get_logger().info('Code suggestions generated for PR, but not published since publish_output is False.')
                pr_body = self.generate_summarized_suggestions(data)
                get_settings().data = {"artifact": pr_body}
                return False
        except Exception as e:
            get_logger().error(f"Failed to generate code suggestions for PR, error: {e}",
                               artifact={"traceback": traceback.format_exc()})
            if get_settings().config.publish_output:
                if self.progress_response:
                    self.progress_response.delete()
                else:
                    try:
                        self.git_provider.remove_initial_comment()
                        self.git_provider.publish_comment(f"Failed to generate code suggestions for PR")
                    except Exception as e:
                        get_logger().exception(f"Failed to update persistent review, error: {e}")

        return True

    async def add_self_review_text(self, pr_body):
        text = get_settings().pr_code_suggestions.code_suggestions_self_review_text
        pr_body += f"\n\n- [ ]  {text}"
        approve_pr_on_self_review = get_settings().pr_code_suggestions.approve_pr_on_self_review
        fold_suggestions_on_self_review = get_settings().pr_code_suggestions.fold_suggestions_on_self_review
        if approve_pr_on_self_review and not fold_suggestions_on_self_review:
            pr_body += ' <!-- approve pr self-review -->'
        elif fold_suggestions_on_self_review and not approve_pr_on_self_review:
            pr_body += ' <!-- fold suggestions self-review -->'
        else:
            pr_body += ' <!-- approve and fold suggestions self-review -->'
        return pr_body

    async def publish_no_suggestions(self):
        pr_body = "## PR Code Suggestions ✨\n\nNo code suggestions found for the PR."
        if (get_settings().config.publish_output and
                get_settings().pr_code_suggestions.get('publish_output_no_suggestions', True)):
            get_logger().warning('No code suggestions found for the PR.')
            get_logger().debug(f"PR output", artifact=pr_body)
            if self.progress_response:
                self.git_provider.edit_comment(self.progress_response, body=pr_body)
            else:
                self.git_provider.publish_comment(pr_body)
        else:
            get_settings().data = {"artifact": ""}

    async def dual_publishing(self, data):
        data_above_threshold = {'code_suggestions': []}
        try:
            for suggestion in data['code_suggestions']:
                if int(suggestion.get('score', 0)) >= int(
                        get_settings().pr_code_suggestions.dual_publishing_score_threshold) \
                        and suggestion.get('improved_code'):
                    data_above_threshold['code_suggestions'].append(suggestion)
                    if not data_above_threshold['code_suggestions'][-1]['existing_code']:
                        get_logger().info(f'Identical existing and improved code for dual publishing found')
                        data_above_threshold['code_suggestions'][-1]['existing_code'] = suggestion[
                            'improved_code']
            if data_above_threshold['code_suggestions']:
                get_logger().info(
                    f"Publishing {len(data_above_threshold['code_suggestions'])} suggestions in dual publishing mode")
                await self.push_inline_code_suggestions(data_above_threshold)
        except Exception as e:
            get_logger().error(f"Failed to publish dual publishing suggestions, error: {e}")

    @staticmethod
    def publish_persistent_comment_with_history(git_provider: GitProvider,
                                                pr_comment: str,
                                                initial_header: str,
                                                update_header: bool = True,
                                                name='review',
                                                final_update_message=True,
                                                max_previous_comments=4,
                                                progress_response=None,
                                                only_fold=False):

        def _extract_link(comment_text: str):
            r = re.compile(r"<!--.*?-->")
            match = r.search(comment_text)

            up_to_commit_txt = ""
            if match:
                up_to_commit_txt = f" up to commit {match.group(0)[4:-3].strip()}"
            return up_to_commit_txt

        history_header = f"#### Previous suggestions\n"
        last_commit_num = git_provider.get_latest_commit_url().split('/')[-1][:7]
        if only_fold: # A user clicked on the 'self-review' checkbox
            text = get_settings().pr_code_suggestions.code_suggestions_self_review_text
            latest_suggestion_header = f"\n\n- [x]  {text}"
        else:
            latest_suggestion_header = f"Latest suggestions up to {last_commit_num}"
        latest_commit_html_comment = f"<!-- {last_commit_num} -->"
        found_comment = None

        if max_previous_comments > 0:
            try:
                prev_comments = list(git_provider.get_issue_comments())
                for comment in prev_comments:
                    if comment.body.startswith(initial_header):
                        prev_suggestions = comment.body
                        found_comment = comment
                        comment_url = git_provider.get_comment_url(comment)

                        if history_header.strip() not in comment.body:
                            # no history section
                            # extract everything between <table> and </table> in comment.body including <table> and </table>
                            table_index = comment.body.find("<table>")
                            if table_index == -1:
                                git_provider.edit_comment(comment, pr_comment)
                                continue
                            # find http link from comment.body[:table_index]
                            up_to_commit_txt = _extract_link(comment.body[:table_index])
                            prev_suggestion_table = comment.body[
                                                    table_index:comment.body.rfind("</table>") + len("</table>")]

                            tick = "✅ " if "✅" in prev_suggestion_table else ""
                            # surround with details tag
                            prev_suggestion_table = f"<details><summary>{tick}{name.capitalize()}{up_to_commit_txt}</summary>\n<br>{prev_suggestion_table}\n\n</details>"

                            new_suggestion_table = pr_comment.replace(initial_header, "").strip()

                            pr_comment_updated = f"{initial_header}\n{latest_commit_html_comment}\n\n"
                            pr_comment_updated += f"{latest_suggestion_header}\n{new_suggestion_table}\n\n___\n\n"
                            pr_comment_updated += f"{history_header}{prev_suggestion_table}\n"
                        else:
                            # get the text of the previous suggestions until the latest commit
                            sections = prev_suggestions.split(history_header.strip())
                            latest_table = sections[0].strip()
                            prev_suggestion_table = sections[1].replace(history_header, "").strip()

                            # get text after the latest_suggestion_header in comment.body
                            table_ind = latest_table.find("<table>")
                            up_to_commit_txt = _extract_link(latest_table[:table_ind])

                            latest_table = latest_table[table_ind:latest_table.rfind("</table>") + len("</table>")]
                            # enforce max_previous_comments
                            count = prev_suggestions.count(f"\n<details><summary>{name.capitalize()}")
                            count += prev_suggestions.count(f"\n<details><summary>✅ {name.capitalize()}")
                            if count >= max_previous_comments:
                                # remove the oldest suggestion
                                prev_suggestion_table = prev_suggestion_table[:prev_suggestion_table.rfind(
                                    f"<details><summary>{name.capitalize()} up to commit")]

                            tick = "✅ " if "✅" in latest_table else ""
                            # Add to the prev_suggestions section
                            last_prev_table = f"\n<details><summary>{tick}{name.capitalize()}{up_to_commit_txt}</summary>\n<br>{latest_table}\n\n</details>"
                            prev_suggestion_table = last_prev_table + "\n" + prev_suggestion_table

                            new_suggestion_table = pr_comment.replace(initial_header, "").strip()

                            pr_comment_updated = f"{initial_header}\n"
                            pr_comment_updated += f"{latest_commit_html_comment}\n\n"
                            pr_comment_updated += f"{latest_suggestion_header}\n\n{new_suggestion_table}\n\n"
                            pr_comment_updated += "___\n\n"
                            pr_comment_updated += f"{history_header}\n"
                            pr_comment_updated += f"{prev_suggestion_table}\n"

                        get_logger().info(f"Persistent mode - updating comment {comment_url} to latest {name} message")
                        if progress_response:  # publish to 'progress_response' comment, because it refreshes immediately
                            git_provider.edit_comment(progress_response, pr_comment_updated)
                            git_provider.remove_comment(comment)
                            comment = progress_response
                        else:
                            git_provider.edit_comment(comment, pr_comment_updated)
                        return comment
            except Exception as e:
                get_logger().exception(f"Failed to update persistent review, error: {e}")
                pass

        # if we are here, we did not find a previous comment to update
        body = pr_comment.replace(initial_header, "").strip()
        pr_comment = f"{initial_header}\n\n{latest_commit_html_comment}\n\n{body}\n\n"
        if progress_response:
            git_provider.edit_comment(progress_response, pr_comment)
            new_comment = progress_response
        else:
            new_comment = git_provider.publish_comment(pr_comment)
        return new_comment


    def extract_link(self, s):
        r = re.compile(r"<!--.*?-->")
        match = r.search(s)

        up_to_commit_txt = ""
        if match:
            up_to_commit_txt = f" up to commit {match.group(0)[4:-3].strip()}"
        return up_to_commit_txt

    async def _get_prediction(self, model: str, patches_diff: str, patches_diff_no_line_number: str, skip_self_reflection: bool = False) -> dict:
        get_logger().info(f"Starting AI code suggestions generation", 
                         artifacts={
                             'model': model,
                             'diff_lines': len(patches_diff.split('\n')) if patches_diff else 0,
                             'files_changed': len(self.git_provider.get_files()) if hasattr(self, 'git_provider') else 0,
                             'language': self.main_language
                         })
        
        # Prepare prompts
        variables = copy.deepcopy(self.vars)
        variables["diff"] = patches_diff
        variables["diff_no_line_numbers"] = patches_diff_no_line_number
        variables["context"] = self.context_data
        environment = Environment(undefined=StrictUndefined)
        
        try:
            system_prompt = environment.from_string(self.pr_code_suggestions_prompt_system).render(variables)
            user_prompt = environment.from_string(get_settings().pr_code_suggestions_prompt.user).render(variables)
        except Exception as e:
            get_logger().error(f"Failed to render AI prompts", 
                             artifacts={'error': str(e), 'variables_keys': list(variables.keys())})
            raise
        
        # Calculate token estimates
        prompt_tokens = 0
        try:
            prompt_tokens = self.token_handler.count_tokens(system_prompt + user_prompt)
            get_logger().info(f"AI prompt prepared - {prompt_tokens:,} tokens estimated")
        except Exception as e:
            get_logger().warning(f"Could not estimate prompt tokens: {e}")
            raise
        
        # Log full prompts at DEBUG level
        get_logger().debug(f"AI System Prompt ({len(system_prompt)} chars):", 
                          artifacts={'system_prompt': system_prompt})
        get_logger().debug(f"AI User Prompt ({len(user_prompt)} chars):", 
                          artifacts={'user_prompt': user_prompt})
        
        # Track AI metrics for dashboard
        from pr_agent.algo.token_handler import TokenUsageTracker
        token_tracker = TokenUsageTracker()
        
        # Make AI call
        get_logger().info(f"Making AI call to {model} for code suggestions...")
        try:
            response, finish_reason, token_usage = await self.ai_handler.chat_completion(
                model=model, 
                temperature=get_settings().config.temperature, 
                system=system_prompt, 
                user=user_prompt
            )
            
            # Track metrics for multi-model support
            self._track_ai_metrics(model, token_usage)
            
            # Log raw AI response at DEBUG level
            get_logger().debug(f"AI Raw Response ({len(response)} chars):", 
                              artifacts={
                                  'response': response,
                                  'finish_reason': finish_reason,
                                  'token_usage': token_usage
                              })
            
            # Get accurate token counts - prioritize AI handler token_usage over token_tracker
            input_tokens = token_usage.get('input_tokens', 0) if token_usage else 0
            output_tokens = token_usage.get('output_tokens', 0) if token_usage else 0
            
            # Only fall back to token_tracker if AI handler didn't provide token counts
            if not input_tokens and not output_tokens:
                totals = token_tracker.get_totals()
                input_tokens = totals.get('input_tokens', prompt_tokens)
                output_tokens = totals.get('output_tokens', 0)
                
                if not token_tracker.has_usage():
                    get_logger().warning("[Generating] - ⚠️ No token usage from AI handler or tracker, using estimates")
                    try:
                        output_tokens = self.token_handler.count_tokens(response)
                    except Exception as e:
                        get_logger().warning(f"[Generating] - ⚠️ Could not estimate output tokens: {e}")
            
            get_logger().info(f"[Generating] - AI call completed successfully", 
                             artifacts={
                                 'input_tokens': input_tokens,
                                 'output_tokens': output_tokens,
                                 'total_tokens': input_tokens + output_tokens,
                                 'finish_reason': finish_reason,
                                 'response_length': len(response)
                             })
        except Exception as e:
            # Track failed AI call metrics
            failed_token_usage = {
                'input_tokens': prompt_tokens,
                'output_tokens': 0
            }
            self._track_ai_metrics(model, failed_token_usage)
            
            get_logger().error(f"❌ AI call failed", 
                              artifacts={
                                  'error': str(e),
                                  'model': model,
                                  'estimated_input_tokens': prompt_tokens,
                                  'error_type': type(e).__name__
                              });
            raise
        
        # Store prompts for potential debugging
        if not get_settings().config.publish_output:
            get_settings().system_prompt = system_prompt
            get_settings().user_prompt = user_prompt

        # Parse AI response into structured suggestions
        get_logger().info("[Generating] - Parsing AI response into code suggestions...")
        try:
            data = self._prepare_pr_code_suggestions(response)
            suggestions_count = len(data.get("code_suggestions", []))
            
            if suggestions_count == 0:
                get_logger().warning("[Generating] - No code suggestions extracted from AI response")
            else:
                get_logger().info(f"[Generating] - Extracted {suggestions_count} code suggestions from AI response")
                
                # Log suggestion count only
                get_logger().debug(f"[Generating] - Generated {suggestions_count} suggestions")
                    
        except Exception as e:
            get_logger().error("[Generating] - Failed to parse AI response into suggestions", 
                              artifacts={'error': str(e), 'error_type': type(e).__name__})
            raise

        # Self-reflection on suggestions (only if not skipped)
        if not skip_self_reflection:
            try:
                get_logger().info("[Reflecting] - Starting self-reflection on generated suggestions...")
                model_reflect_with_reasoning = get_model('model_reasoning')
                fallbacks = get_settings().config.fallback_models
                    
                if model_reflect_with_reasoning == get_settings().config.model and model != get_settings().config.model and fallbacks and model == fallbacks[0]:
                    get_logger().warning(f"[Reflecting] - Using same model ({model}) for self-reflection as suggestions generation")
                    model_reflect_with_reasoning = model
                else:
                    get_logger().info(f"[Reflecting] - Using {model_reflect_with_reasoning} for self-reflection")
                
                response_reflect = await self.self_reflect_on_suggestions(
                    data["code_suggestions"],
                    patches_diff, 
                    model=model_reflect_with_reasoning
                )
                        
                if response_reflect:
                    get_logger().info("[Reflecting] - Self-reflection completed, analyzing results...")
                    get_logger().info(f"[Reflecting] - Response length: {len(response_reflect)} chars")
                    await self.analyze_self_reflection_response(data, response_reflect)
                            
                    # Count suggestions after self-reflection filtering
                    final_count = len([s for s in data.get("code_suggestions", []) if s.get("score", 0) > 0])
                    get_logger().info(f"[Reflecting] - Kept {final_count} suggestions (from {suggestions_count} original)")
                    
                    # Debug: Log scores after analyze_self_reflection_response
                    get_logger().info("[Reflecting] - Scores after analyze_self_reflection_response:")
                    for i, suggestion in enumerate(data["code_suggestions"]):
                        score = suggestion.get("score", "unknown")
                        file_name = suggestion.get("relevant_file", "unknown")
                        get_logger().info(f"[Reflecting] - Post-analysis suggestion {i+1}: score={score} | {file_name}")
                            
                else:
                    get_logger().warning("[Reflecting] - Self-reflection failed, using default scores")
                    get_logger().warning("[Reflecting] - ⚠️ OVERRIDING ALL SCORES TO 7 - This might be the problem!")
                    for i, suggestion in enumerate(data["code_suggestions"]):
                        suggestion["score"] = 7
                        suggestion["score_why"] = "Self-reflection unavailable"
                        
            except Exception as e:
                get_logger().error("[Reflecting] - Self-reflection process failed", 
                                  artifacts={'error': str(e), 'error_type': type(e).__name__})
                # Continue with original suggestions but log the issue
                for i, suggestion in enumerate(data["code_suggestions"]):
                    suggestion["score"] = 7
                    suggestion["score_why"] = "Self-reflection failed"
        else:
            get_logger().info("[Reflecting] - Skipping self-reflection (will be handled in separate stage)")
            # Don't override scores when skipping self-reflection - they may have been set by a previous stage
            get_logger().debug("[Reflecting] - Preserving existing scores from previous stage")

        # AI metrics are tracked via _track_ai_metrics() and sent via _send_aggregated_ai_metrics()

        final_suggestions_count = len(data.get("code_suggestions", []))
        get_logger().info(f"[Generating] - Code suggestions generation completed - {final_suggestions_count} suggestions ready")

        return data

    async def _estimate_suggestions_dev_hours_saved_ai(self, model: str, input_tokens: int = None, 
                                                     output_tokens: int = None, files_count: int = 0,
                                                     diff: str = None, suggestions_content: str = None,
                                                     suggestions_count: int = 0, track_metrics: bool = False) -> float:
        """
        Estimate developer hours saved using AI-powered analysis of the code suggestions
        """
        
        get_logger().info("Starting AI-powered time savings estimation", 
                         artifacts={
                             'model': model,
                             'suggestions_count': suggestions_count,
                             'files_count': files_count,
                             'input_tokens': input_tokens,
                             'output_tokens': output_tokens,
                             'has_diff': bool(diff),
                             'has_suggestions_content': bool(suggestions_content)
                         })
        
        # Validate required inputs
        if not diff or not suggestions_content:
            get_logger().warning("Missing required data for AI time estimation, falling back to heuristic calculation",
                               artifacts={
                                   'missing_diff': not diff,
                                   'missing_suggestions': not suggestions_content
                               })
            heuristic_result = self._estimate_suggestions_dev_hours_saved(files_count, input_tokens + output_tokens, model)
            get_logger().info(f"Heuristic fallback estimation: {heuristic_result} hours")
            return heuristic_result
        
        # Analyze diff complexity
        try:
            get_logger().info("Analyzing diff complexity for time estimation...")
            
            lines_added = 0
            lines_deleted = 0
            if diff:
                for line in diff.split('\n'):
                    if line.startswith('+') and not line.startswith('+++'):
                        lines_added += 1
                    elif line.startswith('-') and not line.startswith('---'):
                        lines_deleted += 1
            
            diff_stats = {
                'lines_added': lines_added,
                'lines_deleted': lines_deleted,
                'total_diff_lines': len(diff.split('\n')) if diff else 0,
                'language': self.main_language
            }
            
            get_logger().info(f"Diff analysis completed: +{lines_added}/-{lines_deleted} lines", 
                             artifacts=diff_stats)
            
            get_logger().debug("Diff content for time estimation:", 
                              artifacts={'diff_preview': diff[:500] + "..." if len(diff) > 500 else diff})
            
        except Exception as e:
            get_logger().error("❌ Failed to analyze diff complexity", 
                              artifacts={'error': str(e), 'error_type': type(e).__name__})
            heuristic_result = self._estimate_suggestions_dev_hours_saved(files_count, input_tokens + output_tokens, model)
            get_logger().info(f"Fallback to heuristic: {heuristic_result} hours")
            return heuristic_result

        # Initialize AI time estimator
        try:
            get_logger().info("Initializing AI time estimator...")
            from pr_agent.algo.dev_time_estimator import DevTimeEstimator
            estimator = DevTimeEstimator(self.ai_handler, self.token_handler, self._track_ai_metrics)
            
        except Exception as e:
            get_logger().error("❌ Failed to initialize DevTimeEstimator", 
                              artifacts={'error': str(e), 'error_type': type(e).__name__})
            heuristic_result = self._estimate_suggestions_dev_hours_saved(files_count, input_tokens + output_tokens, model)
            get_logger().info(f"Fallback to heuristic: {heuristic_result} hours")
            return heuristic_result

        # Make AI estimation call
        try:
            get_logger().info("Making AI call for time savings estimation...", 
                             artifacts={
                                 'estimation_inputs': {
                                     'language': self.main_language,
                                     'files_changed': files_count,
                                     'lines_added': lines_added,
                                     'lines_deleted': lines_deleted,
                                     'suggestions_count': suggestions_count,
                                     'model': model
                                 }
                             })
            
            get_logger().debug("Suggestions content for time estimation:", 
                              artifacts={'suggestions_preview': suggestions_content[:1000] + "..." if len(suggestions_content) > 1000 else suggestions_content})
            
            estimation_result = await estimator.estimate_suggestions_time_savings(
                diff=diff,
                ai_suggestions_content=suggestions_content,
                language=self.main_language,
                files_changed=files_count,
                lines_added=lines_added,
                lines_deleted=lines_deleted,
                suggestions_count=suggestions_count,
                model=model
            )
            
            get_logger().debug("[DevTime] - Raw AI estimation result:", 
                              artifacts={'estimation_result': estimation_result})
            
            # Track metrics if requested (for single operation tracking)
            if track_metrics and DASHBOARD_INTEGRATION_AVAILABLE:
                try:
                    # Try to get token usage from the estimator result or estimate
                    actual_input_tokens = estimation_result.get('token_usage', {}).get('input_tokens', 0)
                    actual_output_tokens = estimation_result.get('token_usage', {}).get('output_tokens', 0)
                    
                    # If no token data in result, try to estimate based on content
                    if not actual_input_tokens and not actual_output_tokens:
                        try:
                            # Estimate tokens based on the content we sent
                            prompt_content = f"{diff}\n{suggestions_content}"
                            actual_input_tokens = self.token_handler.count_tokens(prompt_content) if hasattr(self, 'token_handler') else 2000
                            # Estimate output tokens (typical AI response is smaller)
                            actual_output_tokens = actual_input_tokens // 4  # Conservative estimate
                        except Exception as token_error:
                            get_logger().warning(f"Failed to estimate tokens for time estimation: {token_error}")
                            actual_input_tokens = 2000  # Default estimate
                            actual_output_tokens = 500   # Default estimate
                    
                    get_logger().info(f"[DevTime] - Tracking AI metrics for dev time estimation", 
                                     artifacts={
                                         'model': model,
                                         'input_tokens': actual_input_tokens,
                                         'output_tokens': actual_output_tokens,
                                         'total_tokens': actual_input_tokens + actual_output_tokens
                                     })
                    
                    # Track these metrics via the callback which will aggregate them properly
                    self._track_ai_metrics(model, {
                        'input_tokens': actual_input_tokens,
                        'output_tokens': actual_output_tokens
                    })
                    
                except Exception as metric_error:
                    get_logger().warning(f"Failed to track AI metrics for dev time estimation: {metric_error}")
            
        except Exception as e:
            get_logger().error("❌ AI time estimation call failed", 
                              artifacts={
                                  'error': str(e),
                                  'error_type': type(e).__name__,
                                  'model': model
                              })
            heuristic_result = self._estimate_suggestions_dev_hours_saved(files_count, input_tokens + output_tokens, model)
            get_logger().info(f"Fallback to heuristic: {heuristic_result} hours")
            return heuristic_result

        # Process AI estimation result
        if estimation_result and 'final_assessment' in estimation_result:
            try:
                estimated_hours = estimation_result['final_assessment'].get('total_developer_hours_saved', 1.0)
                confidence = estimation_result['final_assessment'].get('confidence_level', 'medium')
                
                # Validate the estimation result (allow negative values - they represent time wasted)
                if not isinstance(estimated_hours, (int, float)):
                    get_logger().warning(f"Invalid AI estimation result: {estimated_hours}, using fallback")
                    heuristic_result = self._estimate_suggestions_dev_hours_saved(files_count, input_tokens + output_tokens, model)
                    get_logger().info(f"Fallback to heuristic: {heuristic_result} hours")
                    return heuristic_result
                
                # Cap the result at reasonable bounds (allow negative values for time wasted)
                capped_hours = max(-16.0, min(16.0, float(estimated_hours)))
                if capped_hours != estimated_hours:
                    get_logger().warning(f"AI estimation ({estimated_hours}h) was outside bounds, capped to {capped_hours}h")
                
                get_logger().info(f"[DevTime] - AI time estimation completed successfully: {capped_hours} hours", 
                                 artifacts={
                                     'estimated_hours': capped_hours,
                                     'confidence_level': confidence,
                                     'original_estimate': estimated_hours,
                                     'was_capped': capped_hours != estimated_hours,
                                     'estimation_breakdown': estimation_result.get('reasoning', 'No breakdown available')
                                 })
                
                get_logger().debug("[DevTime] - Complete AI estimation details:", 
                                  artifacts={'full_estimation_result': estimation_result})
                
                return capped_hours
                
            except Exception as e:
                get_logger().error("❌ Failed to process AI estimation result", 
                                  artifacts={
                                      'error': str(e),
                                      'error_type': type(e).__name__,
                                      'raw_result': estimation_result
                                  })
                heuristic_result = self._estimate_suggestions_dev_hours_saved(files_count, input_tokens + output_tokens, model)
                get_logger().info(f"Fallback to heuristic: {heuristic_result} hours")
                return heuristic_result
                
        else:
            get_logger().warning("⚠️ AI estimation returned invalid or empty result", 
                               artifacts={'raw_result': estimation_result})
            heuristic_result = self._estimate_suggestions_dev_hours_saved(files_count, input_tokens + output_tokens, model)
            get_logger().info(f"Fallback to heuristic: {heuristic_result} hours")
            return heuristic_result

    def _estimate_suggestions_dev_hours_saved(self, files_count: int, total_tokens: int, model: str) -> float:
        """Estimate developer hours saved for code suggestions based on complexity (heuristic fallback)"""
        
        get_logger().info("Using heuristic time estimation method", 
                         artifacts={
                             'files_count': files_count,
                             'total_tokens': total_tokens,
                             'model': model
                         })
        
        try:
            # Base time for code suggestions (finding and implementing improvements)
            base_hours = 1.0
            
            # Scale by file count - more files means more potential improvements
            if files_count > 50:
                file_multiplier = 4.0
                file_reasoning = "Very large codebase (50+ files)"
            elif files_count > 20:
                file_multiplier = 2.5
                file_reasoning = "Large codebase (20-50 files)"
            elif files_count > 10:
                file_multiplier = 1.5
                file_reasoning = "Medium codebase (10-20 files)"
            elif files_count > 5:
                file_multiplier = 1.2
                file_reasoning = "Small-medium codebase (5-10 files)"
            else:
                file_multiplier = 1.0
                file_reasoning = "Small codebase (≤5 files)"
            
            # Scale by token complexity - more tokens indicate more complex analysis
            if total_tokens > 8000:
                token_multiplier = 2.0
                token_reasoning = "Very complex analysis (8000+ tokens)"
            elif total_tokens > 4000:
                token_multiplier = 1.5
                token_reasoning = "Complex analysis (4000-8000 tokens)"
            elif total_tokens > 2000:
                token_multiplier = 1.2
                token_reasoning = "Moderate analysis (2000-4000 tokens)"
            else:
                token_multiplier = 1.0
                token_reasoning = "Simple analysis (≤2000 tokens)"
            
            # Model quality adjustment
            if 'gpt-4' in model.lower() or 'claude-3' in model.lower():
                model_multiplier = 1.3
                model_reasoning = "High-quality model (GPT-4/Claude-3)"
            elif 'gpt-3.5' in model.lower():
                model_multiplier = 1.0
                model_reasoning = "Standard model (GPT-3.5)"
            else:
                model_multiplier = 0.8
                model_reasoning = "Conservative estimate (other model)"
            
            estimated_hours = base_hours * file_multiplier * token_multiplier * model_multiplier
            
            # Cap at reasonable bounds (allow negative values for time wasted)
            final_hours = max(-8.0, min(8.0, round(estimated_hours, 2)))
            was_capped = final_hours != round(estimated_hours, 2)
            
            get_logger().info(f"Heuristic calculation completed: {final_hours} hours", 
                             artifacts={
                                 'calculation_breakdown': {
                                     'base_hours': base_hours,
                                     'file_multiplier': file_multiplier,
                                     'file_reasoning': file_reasoning,
                                     'token_multiplier': token_multiplier,
                                     'token_reasoning': token_reasoning,
                                     'model_multiplier': model_multiplier,
                                     'model_reasoning': model_reasoning,
                                     'raw_calculation': base_hours * file_multiplier * token_multiplier * model_multiplier,
                                     'final_result': final_hours,
                                     'was_capped': was_capped
                                 }
                             })
            
            if was_capped:
                get_logger().warning(f"⚠️ Heuristic estimate was capped (bounds: 0.1-8.0 hours)")
            
            return final_hours
            
        except Exception as e:
            get_logger().error("❌ Error in heuristic time estimation", 
                              artifacts={'error': str(e), 'error_type': type(e).__name__})
            get_logger().warning("⚠️ Using default fallback: 1.0 hours")
            return 1.0  # Default fallback

    async def analyze_self_reflection_response(self, data, response_reflect):
        get_logger().info("[Reflecting] - Analyzing self-reflection response and applying scores to suggestions")
        
        # Parse the YAML response from self-reflection
        try:
            get_logger().debug("[Reflecting] - Parsing reflection response as YAML", 
                              artifacts={'response_preview': response_reflect[:200] + "..." if len(response_reflect) > 200 else response_reflect})
            
            response_reflect_yaml = load_yaml(response_reflect)
            code_suggestions_feedback = response_reflect_yaml.get("code_suggestions", [])
            
            get_logger().info(f"[Reflecting] - Parsed reflection feedback for {len(code_suggestions_feedback)} suggestions")
            
            if not code_suggestions_feedback:
                get_logger().warning("[Reflecting] - No feedback found in self-reflection response")
                self._apply_default_scores(data["code_suggestions"])
                return
                
        except Exception as e:
            get_logger().error("[Reflecting] - Failed to parse self-reflection YAML response", 
                              artifacts={'error': str(e), 'error_type': type(e).__name__})
            self._apply_default_scores(data["code_suggestions"])
            return

        # Validate response structure
        if len(code_suggestions_feedback) != len(data["code_suggestions"]):
            get_logger().warning(f"[Reflecting] - Feedback count mismatch: {len(code_suggestions_feedback)} feedback vs {len(data['code_suggestions'])} suggestions")
            self._apply_default_scores(data["code_suggestions"])
            return

        # Apply feedback to each suggestion
        scoring_stats = {
            'processed': 0,
            'scored_successfully': 0,
            'line_validation_failures': 0,
            'processing_errors': 0,
            'duplicate_code_issues': 0,
            'score_distribution': {}
        }
        
        get_logger().info("[Reflecting] - Applying reflection feedback to suggestions...")
        
        for i, suggestion in enumerate(data["code_suggestions"]):
            suggestion_file = suggestion.get('relevant_file', f'suggestion_{i+1}')
            
            try:
                scoring_stats['processed'] += 1
                feedback = code_suggestions_feedback[i]
                
                # Extract score and reasoning
                original_score = feedback.get("suggestion_score", 7)
                score_reasoning = feedback.get("why", "No reasoning provided")
                
                # Debug: Log what we extracted from feedback
                get_logger().info(f"[DEBUG] - Feedback for suggestion {i+1}: suggestion_score={original_score} | feedback_keys={list(feedback.keys())}")
                
                # Handle new commit eligibility scoring system (0-10) vs old boolean system
                commit_eligibility_score = feedback.get("commit_eligibility_score")
                commit_eligibility_reason = feedback.get("commit_eligibility_reason", "No eligibility reasoning provided")
                
                if commit_eligibility_score is not None:
                    # New scoring system (0-10)
                    # Ensure score is an integer between 0-10
                    commit_eligibility_score = max(0, min(10, int(commit_eligibility_score)))
                    
                    # Compare against threshold to determine if committable
                    eligibility_threshold = get_settings().pr_code_suggestions.commit_eligibility_threshold
                    commit_eligible = commit_eligibility_score >= eligibility_threshold
                    
                    suggestion["commit_eligibility_score"] = commit_eligibility_score
                    suggestion["commit_eligibility_reason"] = commit_eligibility_reason
                else:
                    # Fallback to old boolean system for backward compatibility
                    commit_eligible = feedback.get("commit_eligible", True)
                    suggestion["commit_eligibility_score"] = 7 if commit_eligible else 3  # Default mapping
                    suggestion["commit_eligibility_reason"] = "Legacy boolean system - no detailed reasoning available"
                
                # Apply the reflected score (filtering will happen later in _self_reflect_on_result)
                suggestion["score"] = original_score
                suggestion["score_why"] = score_reasoning
                suggestion["commit_eligible"] = commit_eligible
                
                # Debug: Log the score assignment
                get_logger().info(f"[DEBUG] - Applied score to suggestion {i+1}: original_score={original_score} | file={suggestion_file}")

                # Handle missing line number information
                if 'relevant_lines_start' not in suggestion:
                    relevant_lines_start = feedback.get('relevant_lines_start', -1)
                    relevant_lines_end = feedback.get('relevant_lines_end', -1)
                    suggestion['relevant_lines_start'] = relevant_lines_start
                    suggestion['relevant_lines_end'] = relevant_lines_end
                    
                    if relevant_lines_start < 0 or relevant_lines_end < 0:
                        suggestion["score"] = 0
                        scoring_stats['line_validation_failures'] += 1

                # Validate the suggestion for duplicated code
                suggestion = self.validate_one_liner_suggestion_not_repeating_code(suggestion)

                # Check for duplicate existing/improved code
                try:
                    if suggestion.get('existing_code') == suggestion.get('improved_code'):
                        scoring_stats['duplicate_code_issues'] += 1
                        
                        if get_settings().pr_code_suggestions.commitable_code_suggestions:
                            suggestion['improved_code'] = ""  # Keep existing_code for location
                        else:
                            suggestion['existing_code'] = ""
                            
                except Exception as e:
                    get_logger().warning(f"[Reflecting] - Error checking duplicate code for suggestion {i+1}: {e}")

                # Track score distribution
                final_score = suggestion.get("score", 0)
                score_key = str(final_score)
                scoring_stats['score_distribution'][score_key] = scoring_stats['score_distribution'].get(score_key, 0) + 1
                scoring_stats['scored_successfully'] += 1

            except Exception as e:
                scoring_stats['processing_errors'] += 1
                
                # Apply default fallback scoring
                suggestion["score"] = 7
                suggestion["score_why"] = f"Processing error: {str(e)}"
                suggestion["commit_eligible"] = True  # Default to True when processing fails
                suggestion["commit_eligibility_score"] = 7  # Default score
                suggestion["commit_eligibility_reason"] = "Default eligibility due to processing error"
                scoring_stats['score_distribution']['7'] = scoring_stats['score_distribution'].get('7', 0) + 1

        # Log overall scoring statistics
        high_scores = sum(count for score, count in scoring_stats['score_distribution'].items() if int(score) >= 8)
        medium_scores = sum(count for score, count in scoring_stats['score_distribution'].items() if 5 <= int(score) < 8)
        low_scores = sum(count for score, count in scoring_stats['score_distribution'].items() if int(score) < 5)
        
        get_logger().info("[Reflecting] - Self-reflection analysis completed", 
                         artifacts={
                             'total_processed': scoring_stats['processed'],
                             'successfully_scored': scoring_stats['scored_successfully'],
                             'issues_found': {
                                 'processing_errors': scoring_stats['processing_errors'],
                                 'line_validation_failures': scoring_stats['line_validation_failures'],
                                 'duplicate_code_issues': scoring_stats['duplicate_code_issues']
                             },
                             'quality_summary': {
                                 'high_quality': high_scores,
                                 'medium_quality': medium_scores,
                                 'low_quality': low_scores
                             },
                             'score_distribution': scoring_stats['score_distribution']
                         })
        
        # Calculate commit eligibility statistics
        commit_eligible_count = sum(1 for suggestion in data.get("code_suggestions", []) if suggestion.get("commit_eligible", True))
        commit_ineligible_count = scoring_stats['processed'] - commit_eligible_count
        
        # Capture self-reflection insights for dashboard
        self._self_reflection_insights = {
            'analysis_statistics': scoring_stats,
            'quality_breakdown': {
                'high_quality_suggestions': high_scores,
                'medium_quality_suggestions': medium_scores,  
                'low_quality_suggestions': low_scores,
                'total_suggestions': scoring_stats['processed']
            },
            'commit_eligibility_breakdown': {
                'commit_eligible_suggestions': commit_eligible_count,
                'commit_ineligible_suggestions': commit_ineligible_count,
                'total_suggestions': scoring_stats['processed']
            },
            'score_distribution': scoring_stats['score_distribution'],
            'processing_summary': {
                'successfully_analyzed': scoring_stats['scored_successfully'],
                'processing_errors': scoring_stats['processing_errors'],
                'line_validation_failures': scoring_stats['line_validation_failures'],
                'duplicate_code_issues': scoring_stats['duplicate_code_issues']
            },
            'individual_suggestions': [
                {
                    'suggestion_summary': suggestion.get('one_sentence_summary', ''),
                    'file': suggestion.get('relevant_file', ''),
                    'score': suggestion.get('score', 0),
                    'commit_eligible': suggestion.get('commit_eligible', True),
                    'commit_eligibility_score': suggestion.get('commit_eligibility_score', 7),
                    'commit_eligibility_reason': suggestion.get('commit_eligibility_reason', ''),
                    'reasoning': suggestion.get('score_why', '')
                }
                for suggestion in data.get("code_suggestions", [])
            ]
        }

    def _apply_default_scores(self, suggestions):
        """Apply default scores when reflection analysis fails"""
        get_logger().warning("[Reflecting] - Applying default scores to all suggestions (score=7)")
        
        for i, suggestion in enumerate(suggestions):
            suggestion["score"] = 7
            suggestion["score_why"] = "Default score - reflection analysis failed"
            suggestion["commit_eligible"] = True  # Default to True when reflection fails
            suggestion["commit_eligibility_score"] = 7  # Default score
            suggestion["commit_eligibility_reason"] = "Default eligibility due to reflection analysis failure"
            
        get_logger().info(f"[Reflecting] - Applied default scores to {len(suggestions)} suggestions")

    @staticmethod
    def _truncate_if_needed(suggestion):
        max_code_suggestion_length = get_settings().get("PR_CODE_SUGGESTIONS.MAX_CODE_SUGGESTION_LENGTH", 0)
        suggestion_truncation_message = get_settings().get("PR_CODE_SUGGESTIONS.SUGGESTION_TRUNCATION_MESSAGE", "")
        if max_code_suggestion_length > 0:
            if len(suggestion['improved_code']) > max_code_suggestion_length:
                get_logger().info(f"Truncated suggestion from {len(suggestion['improved_code'])} "
                                  f"characters to {max_code_suggestion_length} characters")
                suggestion['improved_code'] = suggestion['improved_code'][:max_code_suggestion_length]
                suggestion['improved_code'] += f"\n{suggestion_truncation_message}"
        return suggestion

    def _prepare_pr_code_suggestions(self, predictions: str) -> Dict:
        get_logger().info("[Generating] - Processing and validating AI predictions into structured suggestions")
        
        # Parse YAML predictions
        try:
            get_logger().debug("[Generating] - Parsing AI response as YAML", 
                              artifacts={'response_preview': predictions[:200] + "..." if len(predictions) > 200 else predictions})
            
            data = load_yaml(predictions.strip(),
                             keys_fix_yaml=["relevant_file", "suggestion_content", "existing_code", "improved_code"],
                             first_key="code_suggestions", last_key="label")
            
            if isinstance(data, list):
                data = {'code_suggestions': data}
                get_logger().debug("[Generating] - Converted list format to dictionary format")
            
            raw_suggestions_count = len(data.get('code_suggestions', []))
            get_logger().info(f"[Generating] - Successfully parsed {raw_suggestions_count} raw suggestions from AI")
            
        except Exception as e:
            get_logger().error("[Generating] - Failed to parse AI predictions YAML", 
                              artifacts={'error': str(e), 'error_type': type(e).__name__})
            return {'code_suggestions': []}

        # Validation and filtering statistics
        validation_stats = {
            'raw_suggestions': len(data.get('code_suggestions', [])),
            'missing_required_keys': 0,
            'duplicate_summaries': 0,
            'const_let_filtered': 0,
            'missing_code_blocks': 0,
            'truncated_suggestions': 0,
            'processing_errors': 0,
            'final_valid_suggestions': 0
        }
        
        # Track required keys and filtering
        required_keys = ['one_sentence_summary', 'label', 'relevant_file']
        suggestion_list = []
        one_sentence_summary_list = []
        focus_on_problems = get_settings().get("pr_code_suggestions.focus_only_on_problems", False)
        
        get_logger().info(f"[Generating] - Starting suggestion validation (focus_on_problems: {focus_on_problems})")

        for i, suggestion in enumerate(data.get('code_suggestions', [])):
            suggestion_file = suggestion.get('relevant_file', f'suggestion_{i+1}')
            
            try:
                # Validate required keys
                missing_keys = [key for key in required_keys if key not in suggestion]
                if missing_keys:
                    validation_stats['missing_required_keys'] += 1
                    continue

                # Apply focus-on-problems filtering
                if focus_on_problems:
                    CRITICAL_LABEL = 'critical'
                    original_label = suggestion.get('label', '')
                    if CRITICAL_LABEL in original_label.lower():
                        suggestion['label'] = 'possible issue'

                # Check for duplicate summaries
                summary = suggestion.get('one_sentence_summary', '')
                if summary in one_sentence_summary_list:
                    validation_stats['duplicate_summaries'] += 1
                    continue

                # Filter out const/let suggestions (specific business logic)
                suggestion_content = suggestion.get('suggestion_content', '')
                if ('const' in suggestion_content and 'instead' in suggestion_content and 'let' in suggestion_content):
                    validation_stats['const_let_filtered'] += 1
                    continue

                # Validate code blocks exist
                has_existing_code = 'existing_code' in suggestion and suggestion['existing_code']
                has_improved_code = 'improved_code' in suggestion and suggestion['improved_code']
                
                if not (has_existing_code and has_improved_code):
                    validation_stats['missing_code_blocks'] += 1
                    continue

                # Apply truncation if needed
                original_length = len(suggestion.get('improved_code', ''))
                suggestion = self._truncate_if_needed(suggestion)
                new_length = len(suggestion.get('improved_code', ''))
                
                if new_length != original_length:
                    validation_stats['truncated_suggestions'] += 1

                # Suggestion is valid - add to final list
                one_sentence_summary_list.append(summary)
                suggestion_list.append(suggestion)
                validation_stats['final_valid_suggestions'] += 1

            except Exception as e:
                validation_stats['processing_errors'] += 1

        # Update data with validated suggestions
        data['code_suggestions'] = suggestion_list
        
        # Calculate filtering efficiency
        kept_percentage = (validation_stats['final_valid_suggestions'] / max(1, validation_stats['raw_suggestions'])) * 100
        
        get_logger().info("[Generating] - Suggestion validation completed", 
                         artifacts={
                             'validation_summary': validation_stats,
                             'kept_percentage': round(kept_percentage, 1),
                             'final_count': validation_stats['final_valid_suggestions']
                         })
        
        if validation_stats['processing_errors'] > 0:
            get_logger().warning(f"[Generating] - {validation_stats['processing_errors']} suggestions had processing errors")
        
        return data

    async def push_inline_code_suggestions(self, data):
        # Starting to format and publish code suggestions to PR
        
        # Handle empty suggestions case
        if not data.get('code_suggestions'):
            get_logger().warning("⚠️ No suggestions available to publish")
            
            no_suggestions_message = 'No suggestions found to improve this PR.'
            
            try:
                if self.progress_response:
                    get_logger().info("Updating existing progress comment with 'no suggestions' message")
                    result = self.git_provider.edit_comment(self.progress_response, body=no_suggestions_message)
                    get_logger().info("Progress comment updated successfully")
                    return result
                else:
                    get_logger().info("Publishing new comment with 'no suggestions' message")
                    result = self.git_provider.publish_comment(no_suggestions_message)
                    get_logger().info("No suggestions comment published successfully")
                    return result
            except Exception as e:
                get_logger().error("❌ Failed to publish 'no suggestions' message", 
                                  artifacts={
                                      'error': str(e),
                                      'error_type': type(e).__name__,
                                      'has_progress_response': bool(self.progress_response)
                                  })
                return None

        # Process and format suggestions for publishing
        code_suggestions = []
        detailed_suggestions_data = []  # Collect all suggestion details for combined logging
        formatting_stats = {
            'total_suggestions': len(data['code_suggestions']),
            'successfully_formatted': 0,
            'formatting_errors': 0,
            'dedented_code_snippets': 0,
            'scored_suggestions': 0,
            'unscored_suggestions': 0
        }
        
        # Formatting suggestions for GitHub publication
        for i, suggestion in enumerate(data['code_suggestions']):
            suggestion_file = suggestion.get('relevant_file', f'suggestion_{i+1}')
            
            try:
                # Processing suggestion for publication
                pass

                # Extract and validate suggestion fields
                relevant_file = suggestion['relevant_file'].strip()
                relevant_lines_start = int(suggestion['relevant_lines_start'])
                relevant_lines_end = int(suggestion['relevant_lines_end'])
                content = suggestion['suggestion_content'].rstrip()
                new_code_snippet = suggestion['improved_code'].rstrip()
                label = suggestion['label'].strip()
                score = suggestion.get('score')

                # Collect suggestion details for combined logging
                if get_settings().config.verbosity_level >= 2:
                    detailed_suggestions_data.append({
                        'suggestion_number': i+1,
                        'full_suggestion': suggestion,
                        'file': relevant_file,
                        'lines': f"{relevant_lines_start}-{relevant_lines_end}",
                        'content_preview': content[:100],
                        'code_length': len(new_code_snippet),
                        'label': label,
                        'score': score
                    })

                # Apply code deindentation if needed
                original_code_snippet = new_code_snippet
                if new_code_snippet:
                    new_code_snippet = self.dedent_code(relevant_file, relevant_lines_start, new_code_snippet)

                    if new_code_snippet != original_code_snippet:
                        formatting_stats['dedented_code_snippets'] += 1
                        # Indentation adjustment completed (verbose logging removed)

                # Format suggestion body for GitHub
                # Check if suggestion is eligible for commit (has commit button)
                commit_eligible = suggestion.get('commit_eligible', True)  # Default to True for backward compatibility
                code_block_type = "suggestion" if commit_eligible else "diff"
                
                if score:
                    body = f"**Suggestion:** {content} [{label}, importance: {score}]\n```{code_block_type}\n{new_code_snippet}\n```"
                    formatting_stats['scored_suggestions'] += 1
                else:
                    body = f"**Suggestion:** {content} [{label}]\n```{code_block_type}\n{new_code_snippet}\n```"
                    formatting_stats['unscored_suggestions'] += 1

                # Create formatted suggestion for publishing
                formatted_suggestion = {
                    'body': body,
                    'relevant_file': relevant_file,
                                         'relevant_lines_start': relevant_lines_start,
                                         'relevant_lines_end': relevant_lines_end,
                    'original_suggestion': suggestion
                }
                
                code_suggestions.append(formatted_suggestion)
                formatting_stats['successfully_formatted'] += 1

            except Exception as e:
                formatting_stats['formatting_errors'] += 1
                get_logger().error(f"❌ Error formatting suggestion {i+1}", 
                                  artifacts={
                                      'error': str(e),
                                      'error_type': type(e).__name__,
                                      'suggestion': suggestion,
                                      'file': suggestion_file
                                  })

        # Log all detailed suggestions data in a single entry
        if detailed_suggestions_data and get_settings().config.verbosity_level >= 2:
            get_logger().info(f"Detailed suggestions data for {len(detailed_suggestions_data)} suggestions:", 
                             artifacts={
                                 'all_suggestions': detailed_suggestions_data,
                                 'formatting_stats': formatting_stats,
                                 'total_processed': len(data['code_suggestions'])
                             })
        
        if not code_suggestions:
            get_logger().error("❌ No suggestions were successfully formatted for publication")
            return None
        
        try:
            is_successful = self.git_provider.publish_code_suggestions(code_suggestions)
            
            if is_successful:
                return is_successful
                
        except Exception as e:
            get_logger().error("❌ Error during batch publishing", 
                              artifacts={
                                  'error': str(e),
                                  'error_type': type(e).__name__,
                                  'suggestions_count': len(code_suggestions)
                              })

        # Fallback: Publish suggestions individually
        individual_publish_stats = {
            'attempted': len(code_suggestions),
            'successful': 0,
            'failed': 0
        }
        
        for i, code_suggestion in enumerate(code_suggestions):
            try:
                individual_result = self.git_provider.publish_code_suggestions([code_suggestion])
                
                if individual_result:
                    individual_publish_stats['successful'] += 1
                else:
                    individual_publish_stats['failed'] += 1
                    
            except Exception as e:
                individual_publish_stats['failed'] += 1
                get_logger().error(f"❌ Error publishing individual suggestion {i+1}", 
                                  artifacts={
                                      'error': str(e),
                                      'error_type': type(e).__name__,
                                      'suggestion_file': code_suggestion.get('relevant_file', 'unknown')
                                  })

        if individual_publish_stats['successful'] == 0:
            get_logger().error("❌ Failed to publish any suggestions to the PR")
            
        return individual_publish_stats['successful'] > 0

    def dedent_code(self, relevant_file, relevant_lines_start, new_code_snippet):
        # Handle empty code snippet
        if not new_code_snippet or not new_code_snippet.strip():
            return new_code_snippet
            
        try:
            # Get diff files from git provider
            self.diff_files = self.git_provider.diff_files if self.git_provider.diff_files \
                else self.git_provider.get_diff_files()
            
            original_initial_line = None
            target_file_found = False
            
            # Find the target file in diff files
            for file_idx, file in enumerate(self.diff_files):
                if file.filename.strip() == relevant_file:
                    target_file_found = True
                    
                    # Check if head_file exists
                    if not file.head_file:
                        get_logger().warning(f"⚠️ Target file has no head_file content, cannot adjust indentation: {file.filename}")
                        return new_code_snippet
                    
                    # Split file into lines and validate line number
                    file_lines = file.head_file.splitlines()
                    total_lines = len(file_lines)
                    
                    if relevant_lines_start > total_lines:
                        get_logger().warning(f"⚠️ Target line number {relevant_lines_start} exceeds file length {total_lines}, cannot adjust indentation")
                        return new_code_snippet
                    
                    # Get the original line for indentation reference (1-based to 0-based)
                    original_initial_line = file_lines[relevant_lines_start - 1]
                    break
            
            # Handle case where target file wasn't found
            if not target_file_found:
                get_logger().warning(f"⚠️ Target file not found in diff files: {relevant_file}")
                return new_code_snippet
            
            # Process indentation if we found the original line
            if original_initial_line is not None:
                # Get the first line of the suggested code
                suggested_lines = new_code_snippet.splitlines()
                if not suggested_lines:
                    return new_code_snippet
                    
                suggested_initial_line = suggested_lines[0]
                
                # Calculate indentation spaces
                original_initial_spaces = len(original_initial_line) - len(original_initial_line.lstrip())
                suggested_initial_spaces = len(suggested_initial_line) - len(suggested_initial_line.lstrip())
                delta_spaces = original_initial_spaces - suggested_initial_spaces
                
                # Apply indentation adjustment if needed
                if delta_spaces > 0:
                    indent_str = delta_spaces * " "
                    new_code_snippet = textwrap.indent(new_code_snippet, indent_str).rstrip('\n')
                # No logging for successful indentation adjustments (too verbose)
            else:
                get_logger().warning("⚠️ Could not determine original line indentation, returning code unchanged")
                
        except Exception as e:
            get_logger().error(f"❌ Error during code indentation adjustment for {relevant_file}:{relevant_lines_start}: {e}")

        return new_code_snippet

    def validate_one_liner_suggestion_not_repeating_code(self, suggestion):
        
        try:
            # Extract and validate suggestion components
            existing_code = suggestion.get('existing_code', '').strip()
            new_code = suggestion.get('improved_code', '').strip()
            relevant_file = suggestion.get('relevant_file', '').strip()
            
            # Handle ellipsis case (partial code snippets)
            if '...' in existing_code:
                return suggestion
            
            # Validate required components
            if not existing_code or not new_code or not relevant_file:
                return suggestion

            # Get diff files for validation
            diff_files = self.git_provider.get_diff_files()
            target_file_found = False
            
            # Find target file in diff files
            for file_idx, file in enumerate(diff_files):
                if file.filename.strip() == relevant_file:
                    target_file_found = True
                    
                    # Validate file content availability
                    if not file.head_file:
                        return suggestion
                    
                    head_file = file.head_file
                    base_file = file.base_file if file.base_file else ""
                    
                    # Perform duplication analysis
                    existing_in_base = existing_code in base_file if base_file else False
                    existing_in_head = existing_code in head_file
                    new_in_head = new_code in head_file
                    
                    # Apply validation logic: reject if suggesting code that was removed and re-added
                    if existing_in_base and not existing_in_head and new_in_head:
                        original_score = suggestion.get("score", "unknown")
                        suggestion["score"] = 0
                        
                        pass
                    
                    break
            
            # Handle case where target file wasn't found
            if not target_file_found:
                return suggestion
                
        except Exception as e:
            pass

        return suggestion

    def remove_line_numbers(self, patches_diff_list: List[str]) -> List[str]:
        get_logger().info("Starting line number removal from patches", 
                         artifacts={
                             'total_patches': len(patches_diff_list),
                             'input_patches_total_length': sum(len(patch) for patch in patches_diff_list)
                         })
        
        # Handle empty input
        if not patches_diff_list:
            get_logger().warning("⚠️ No patches provided for line number removal")
            return []
        
        try:
            processing_stats = {
                'total_patches': len(patches_diff_list),
                'lines_processed': 0,
                'lines_cleared': 0,
                'numeric_lines_removed': 0,
                'digit_prefixed_lines_processed': 0,
                'processing_errors': 0
            }
            
            self.patches_diff_list_no_line_numbers = []
            
            for patch_idx, patches_diff in enumerate(patches_diff_list):
                get_logger().debug(f"Processing patch {patch_idx + 1}/{len(patches_diff_list)}", 
                                  artifacts={
                                      'patch_index': patch_idx,
                                      'patch_length': len(patches_diff),
                                      'patch_preview': patches_diff[:200] + "..." if len(patches_diff) > 200 else patches_diff
                                  })
                
                try:
                    patches_diff_lines = patches_diff.splitlines()
                    original_line_count = len(patches_diff_lines)
                    lines_modified_in_patch = 0
                    
                    for i, line in enumerate(patches_diff_lines):
                        processing_stats['lines_processed'] += 1
                        
                        # Skip empty lines
                        if not line.strip():
                            continue
                        
                        # Handle purely numeric lines
                        if line.isnumeric():
                            patches_diff_lines[i] = ''
                            processing_stats['lines_cleared'] += 1
                            processing_stats['numeric_lines_removed'] += 1
                            lines_modified_in_patch += 1
                            
                            get_logger().debug(f"🔢 Removed numeric line: '{line}' at position {i}")
                            
                        # Handle lines starting with digits
                        elif line and line[0].isdigit():
                            original_line = line
                            processing_stats['digit_prefixed_lines_processed'] += 1
                            
                            # Find the first non-digit character
                            for j, char in enumerate(line):
                                if not char.isdigit():
                                    # Extract content after the first non-digit character
                                    new_line_content = line[j + 1:] if j + 1 < len(line) else ''
                                    patches_diff_lines[i] = new_line_content
                                    lines_modified_in_patch += 1
                                    
                                    get_logger().debug(f"🔧 Processed digit-prefixed line", 
                                                      artifacts={
                                                          'line_index': i,
                                                          'original_line': original_line[:100],
                                                          'extracted_content': new_line_content[:100],
                                                          'digit_prefix_length': j
                                                      })
                                    break
                    
                    # Reconstruct the patch
                    processed_patch = '\n'.join(patches_diff_lines)
                    self.patches_diff_list_no_line_numbers.append(processed_patch)
                    
                    get_logger().debug(f"✅ Patch {patch_idx + 1} processed successfully", 
                                      artifacts={
                                          'original_lines': original_line_count,
                                          'lines_modified': lines_modified_in_patch,
                                          'processed_patch_length': len(processed_patch),
                                          'size_reduction': len(patches_diff) - len(processed_patch)
                                      })
                    
                except Exception as e:
                    processing_stats['processing_errors'] += 1
                    get_logger().error(f"❌ Error processing patch {patch_idx + 1}", 
                                      artifacts={
                                          'error': str(e),
                                          'error_type': type(e).__name__,
                                          'patch_index': patch_idx,
                                          'patch_preview': patches_diff[:300] if patches_diff else 'Empty patch'
                                      })
                    
                    # Add original patch as fallback
                    self.patches_diff_list_no_line_numbers.append(patches_diff)
            
            # Calculate final statistics
            output_total_length = sum(len(patch) for patch in self.patches_diff_list_no_line_numbers)
            input_total_length = sum(len(patch) for patch in patches_diff_list)
            size_reduction = input_total_length - output_total_length
            reduction_percentage = (size_reduction / max(1, input_total_length)) * 100
            
            get_logger().info("Line number removal completed", 
                             artifacts={
                                 'processing_summary': processing_stats,
                                 'size_metrics': {
                                     'input_total_length': input_total_length,
                                     'output_total_length': output_total_length,
                                     'size_reduction_bytes': size_reduction,
                                     'reduction_percentage': round(reduction_percentage, 2)
                                 },
                                 'success_rate': f"{((processing_stats['total_patches'] - processing_stats['processing_errors']) / max(1, processing_stats['total_patches']) * 100):.1f}%"
                             })
            
            if processing_stats['processing_errors'] > 0:
                get_logger().warning(f"⚠️ {processing_stats['processing_errors']} patches had processing errors")
            
            if reduction_percentage > 50:
                get_logger().info(f"Significant size reduction achieved: {reduction_percentage:.1f}%")
            elif reduction_percentage < 5:
                get_logger().info(f"Minimal size reduction: {reduction_percentage:.1f}% (few line numbers to remove)")
            
            return self.patches_diff_list_no_line_numbers
            
        except Exception as e:
            get_logger().error("❌ Critical error during line number removal", 
                              artifacts={
                                  'error': str(e),
                                  'error_type': type(e).__name__,
                                  'input_patches_count': len(patches_diff_list),
                                  'fallback_strategy': 'returning original patches'
                              })
            
            get_logger().warning("⚠️ Falling back to original patches due to processing error")
            return patches_diff_list

    async def prepare_prediction_main(self, model: str) -> dict:
        get_logger().info("Starting main prediction preparation workflow", 
                         artifacts={
                             'model': model,
                             'decouple_hunks': get_settings().pr_code_suggestions.decouple_hunks,
                             'max_calls': get_settings().pr_code_suggestions.max_number_of_calls,
                             'parallel_calls': get_settings().pr_code_suggestions.parallel_calls,
                             'context_service_enabled': get_settings().csharp_code_context_service.enabled
                         })
        
        workflow_stats = {
            'diff_fetch_strategy': 'unknown',
            'patches_retrieved': 0,
            'context_fetched': False,
            'ai_calls_made': 0,
            'suggestions_before_filtering': 0,
            'suggestions_after_filtering': 0,
            'score_threshold': 0,
            'parallel_execution': False
        }
        
        # Phase 1: Fetch PR diff using appropriate strategy
        try:
            if get_settings().pr_code_suggestions.decouple_hunks:
                workflow_stats['diff_fetch_strategy'] = 'decoupled_hunks'
                get_logger().info("Using decoupled hunks strategy for diff fetching")
                
                self.patches_diff_list = await get_pr_multi_diffs(
                    self.git_provider,
                    self.token_handler,
                    model,
                    max_calls=get_settings().pr_code_suggestions.max_number_of_calls,
                    add_line_numbers=True
                )
                
                workflow_stats['patches_retrieved'] = len(self.patches_diff_list)
                get_logger().info(f"✅ Retrieved {len(self.patches_diff_list)} patches with line numbers")
                
                # Remove line numbers from patches
                self.patches_diff_list_no_line_numbers = self.remove_line_numbers(self.patches_diff_list)
                
                get_logger().debug("Created patches without line numbers from decoupled hunks")

            else:
                workflow_stats['diff_fetch_strategy'] = 'non_decoupled_hunks'
                get_logger().info("Using non-decoupled hunks strategy for diff fetching")
                
                # First get patches without line numbers
                self.patches_diff_list_no_line_numbers = await get_pr_multi_diffs(
                    self.git_provider,
                    self.token_handler,
                    model,
                    max_calls=get_settings().pr_code_suggestions.max_number_of_calls,
                    add_line_numbers=False
                )
                
                get_logger().info(f"✅ Retrieved {len(self.patches_diff_list_no_line_numbers)} patches without line numbers")
                
                # Convert to decoupled with line numbers
                get_logger().info("Converting to decoupled patches with line numbers...")
                self.patches_diff_list = await self.convert_to_decoupled_with_line_numbers(
                    self.patches_diff_list_no_line_numbers, model
                )
                
                if not self.patches_diff_list:
                    get_logger().warning("⚠️ Conversion to decoupled hunks failed, falling back to decoupled strategy")
                    workflow_stats['diff_fetch_strategy'] = 'fallback_to_decoupled'
                    
                    self.patches_diff_list = await get_pr_multi_diffs(
                        self.git_provider,
                        self.token_handler,
                        model,
                        max_calls=get_settings().pr_code_suggestions.max_number_of_calls,
                        add_line_numbers=True
                    )
                    
                    get_logger().info(f"Fallback successful: retrieved {len(self.patches_diff_list)} patches")
                else:
                    get_logger().info(f"✅ Conversion successful: {len(self.patches_diff_list)} decoupled patches created")
                
                workflow_stats['patches_retrieved'] = len(self.patches_diff_list)
                
        except Exception as e:
            get_logger().error("❌ Critical error during diff fetching", 
                              artifacts={
                                  'error': str(e),
                                  'error_type': type(e).__name__,
                                  'strategy': workflow_stats['diff_fetch_strategy']
                              })
            return None
        
        # Phase 2: Fetch context if enabled
        try:
            if get_settings().csharp_code_context_service.enabled:
                self.context_data = await get_pr_context(self.git_provider)
                context_length = len(self.context_data) if self.context_data else 0
                workflow_stats['context_fetched'] = True
                
                if context_length > 0:
                    get_logger().info(f"Context fetched for {context_length} characters")
            else:
                self.context_data = ""
                workflow_stats['context_fetched'] = False
                
        except Exception as e:
            get_logger().error("❌ Error fetching context", 
                              artifacts={
                                  'error': str(e),
                                  'error_type': type(e).__name__
                              })
            self.context_data = ""
            workflow_stats['context_fetched'] = False

        # Phase 3: Process patches and make AI predictions
        if not self.patches_diff_list:
            get_logger().warning("⚠️ No patches available for processing")
            workflow_stats['ai_calls_made'] = 0
            self.data = None
            return None
        
        get_logger().info(f"Processing {len(self.patches_diff_list)} patches for AI predictions", 
                         artifacts={
                             'total_patches': len(self.patches_diff_list),
                             'patches_preview': [patch[:100] + "..." if len(patch) > 100 else patch 
                                               for patch in self.patches_diff_list[:3]]  # Show first 3 patches
                         })
        
        try:
            # Determine execution strategy
            parallel_enabled = get_settings().pr_code_suggestions.parallel_calls
            workflow_stats['parallel_execution'] = parallel_enabled
            
            if parallel_enabled:
                get_logger().info("Using parallel AI prediction strategy")
                
                prediction_list = await asyncio.gather(
                    *[self._get_prediction(model, patches_diff, patches_diff_no_line_numbers) for
                      patches_diff, patches_diff_no_line_numbers in
                      zip(self.patches_diff_list, self.patches_diff_list_no_line_numbers)]
                )
                
                get_logger().info(f"Parallel predictions completed: {len(prediction_list)} results")
                
            else:
                get_logger().info("Using sequential AI prediction strategy")
                
                prediction_list = []
                for idx, (patches_diff, patches_diff_no_line_numbers) in enumerate(
                    zip(self.patches_diff_list, self.patches_diff_list_no_line_numbers)
                ):
                    get_logger().debug(f"Making AI call {idx + 1}/{len(self.patches_diff_list)}")
                    
                    prediction = await self._get_prediction(model, patches_diff, patches_diff_no_line_numbers)
                    prediction_list.append(prediction)

                get_logger().info(f"✅ Sequential predictions completed: {len(prediction_list)} results")
            
            self.prediction_list = prediction_list
            workflow_stats['ai_calls_made'] = len(prediction_list)
            
        except Exception as e:
            get_logger().error("❌ Error during AI prediction phase", 
                              artifacts={
                                  'error': str(e),
                                  'error_type': type(e).__name__,
                                  'parallel_mode': parallel_enabled,
                                  'patches_count': len(self.patches_diff_list)
                              })
            return None
        
                # Phase 4: Aggregate and filter suggestions
        try:
            data = {"code_suggestions": []}
            score_threshold = max(1, int(get_settings().pr_code_suggestions.suggestions_score_threshold))
            workflow_stats['score_threshold'] = score_threshold
            
            filtering_stats = {
                'total_predictions': len(prediction_list),
                'predictions_with_suggestions': 0,
                'raw_suggestions_count': 0,
                'passed_threshold': 0,
                'below_threshold': 0,
                'processing_errors': 0
            }
            
            get_logger().info(f"[Generating] - Aggregating suggestions with score threshold: {score_threshold}")
            
            for j, predictions in enumerate(prediction_list):
                if "code_suggestions" in predictions:
                    filtering_stats['predictions_with_suggestions'] += 1
                    call_suggestions = predictions["code_suggestions"]
                    filtering_stats['raw_suggestions_count'] += len(call_suggestions)
                    
                    for i, prediction in enumerate(call_suggestions):
                        try:
                            # Add all suggestions - filtering will happen after reflection
                            data["code_suggestions"].append(prediction)
                            filtering_stats['passed_threshold'] += 1  # Count all as "passed" for now
                                
                        except Exception as e:
                            filtering_stats['processing_errors'] += 1
            
            # Update workflow stats
            workflow_stats['suggestions_before_filtering'] = filtering_stats['raw_suggestions_count']
            workflow_stats['suggestions_after_filtering'] = filtering_stats['passed_threshold']
            
            self.data = data
            
            # Log final aggregation results
            success_rate = (filtering_stats['passed_threshold'] / max(1, filtering_stats['raw_suggestions_count'])) * 100
            
            get_logger().info("[Generating] - Suggestion aggregation completed", 
                             artifacts={
                                 'summary': {
                                     'total_suggestions': filtering_stats['raw_suggestions_count'],
                                     'passed_threshold': filtering_stats['passed_threshold'],
                                     'filtered_out': filtering_stats['below_threshold'],
                                     'success_rate': f"{success_rate:.1f}%"
                                 }
                             })
            
            if filtering_stats['processing_errors'] > 0:
                get_logger().warning(f"[Generating] - {filtering_stats['processing_errors']} suggestions had processing errors")
            
            if success_rate < 30:
                get_logger().warning(f"[Generating] - Low suggestion success rate: {success_rate:.1f}%")
            
        except Exception as e:
            get_logger().error("[Generating] - Error during suggestion aggregation", 
                              artifacts={'error': str(e), 'error_type': type(e).__name__})
            self.data = None
            return None
        
        # Final workflow summary
        get_logger().info("[Generating] - Main prediction workflow completed", 
                         artifacts={
                             'workflow_summary': workflow_stats,
                             'final_suggestions': len(data["code_suggestions"])
                         })
        
        if not data["code_suggestions"]:
            get_logger().warning("[Generating] - No suggestions survived the complete workflow")
        
        return data

    async def convert_to_decoupled_with_line_numbers(self, patches_diff_list_no_line_numbers, model) -> List[str]:
        with get_logger().contextualize(sub_feature='convert_to_decoupled_with_line_numbers'):
            try:
                patches_diff_list = []
                for patch_prompt in patches_diff_list_no_line_numbers:
                    file_prefix = "## File: "
                    patches = patch_prompt.strip().split(f"\n{file_prefix}")
                    patches_new = copy.deepcopy(patches)
                    for i in range(len(patches_new)):
                        if i == 0:
                            prefix = patches_new[i].split("\n@@")[0].strip()
                        else:
                            prefix = file_prefix + patches_new[i].split("\n@@")[0][1:]
                            prefix = prefix.strip()
                        patches_new[i] = prefix + '\n\n' + decouple_and_convert_to_hunks_with_lines_numbers(patches_new[i],
                                                                                                          file=None).strip()
                        patches_new[i] = patches_new[i].strip()
                    patch_final = "\n\n\n".join(patches_new)
                    if model in MAX_TOKENS:
                        max_tokens_full = MAX_TOKENS[
                            model]  # note - here we take the actual max tokens, without any reductions. we do aim to get the full documentation website in the prompt
                    else:
                        max_tokens_full = get_max_tokens(model)
                    delta_output = 2000
                    token_count = self.token_handler.count_tokens(patch_final)
                    if token_count > max_tokens_full - delta_output:
                        get_logger().warning(
                            f"Token count {token_count} exceeds the limit {max_tokens_full - delta_output}. clipping the tokens")
                        patch_final = clip_tokens(patch_final, max_tokens_full - delta_output)
                    patches_diff_list.append(patch_final)
                return patches_diff_list
            except Exception as e:
                get_logger().exception(f"Error converting to decoupled with line numbers",
                                       artifact={'patches_diff_list_no_line_numbers': patches_diff_list_no_line_numbers})
                return []

    def generate_summarized_suggestions(self, data: Dict) -> str:
        try:
            pr_body = "## PR Code Suggestions ✨\n\n"

            if len(data.get('code_suggestions', [])) == 0:
                pr_body += "No suggestions found to improve this PR."
                return pr_body

            if get_settings().config.is_auto_command:
                pr_body += "Explore these optional code suggestions:\n\n"

            language_extension_map_org = get_settings().language_extension_map_org
            extension_to_language = {}
            for language, extensions in language_extension_map_org.items():
                for ext in extensions:
                    extension_to_language[ext] = language

            pr_body += "<table>"
            header = f"Suggestion"
            delta = 66
            header += "&nbsp; " * delta
            pr_body += f"""<thead><tr><td><strong>Category</strong></td><td align=left><strong>{header}</strong></td><td align=center><strong>Impact</strong></td></tr>"""
            pr_body += """<tbody>"""
            suggestions_labels = dict()
            # add all suggestions related to each label
            for suggestion in data['code_suggestions']:
                label = suggestion['label'].strip().strip("'").strip('"')
                if label not in suggestions_labels:
                    suggestions_labels[label] = []
                suggestions_labels[label].append(suggestion)

            # sort suggestions_labels by the suggestion with the highest score
            suggestions_labels = dict(
                sorted(suggestions_labels.items(), key=lambda x: max([s['score'] for s in x[1]]), reverse=True))
            # sort the suggestions inside each label group by score
            for label, suggestions in suggestions_labels.items():
                suggestions_labels[label] = sorted(suggestions, key=lambda x: x['score'], reverse=True)

            counter_suggestions = 0
            for label, suggestions in suggestions_labels.items():
                num_suggestions = len(suggestions)
                pr_body += f"""<tr><td rowspan={num_suggestions}>{label.capitalize()}</td>\n"""
                for i, suggestion in enumerate(suggestions):

                    relevant_file = suggestion['relevant_file'].strip()
                    relevant_lines_start = int(suggestion['relevant_lines_start'])
                    relevant_lines_end = int(suggestion['relevant_lines_end'])
                    range_str = ""
                    if relevant_lines_start == relevant_lines_end:
                        range_str = f"[{relevant_lines_start}]"
                    else:
                        range_str = f"[{relevant_lines_start}-{relevant_lines_end}]"

                    try:
                        code_snippet_link = self.git_provider.get_line_link(relevant_file, relevant_lines_start,
                                                                            relevant_lines_end)
                    except:
                        code_snippet_link = ""
                    # add html table for each suggestion

                    suggestion_content = suggestion['suggestion_content'].rstrip()
                    CHAR_LIMIT_PER_LINE = 84
                    suggestion_content = insert_br_after_x_chars(suggestion_content, CHAR_LIMIT_PER_LINE)
                    # pr_body += f"<tr><td><details><summary>{suggestion_content}</summary>"
                    existing_code = suggestion['existing_code'].rstrip() + "\n"
                    improved_code = suggestion['improved_code'].rstrip() + "\n"

                    diff = difflib.unified_diff(existing_code.split('\n'),
                                                improved_code.split('\n'), n=999)
                    patch_orig = "\n".join(diff)
                    patch = "\n".join(patch_orig.splitlines()[5:]).strip('\n')

                    example_code = ""
                    example_code += f"```diff\n{patch.rstrip()}\n```\n"
                    if i == 0:
                        pr_body += f"""<td>\n\n"""
                    else:
                        pr_body += f"""<tr><td>\n\n"""
                    suggestion_summary = suggestion['one_sentence_summary'].strip().rstrip('.')
                    if "'<" in suggestion_summary and ">'" in suggestion_summary:
                        # escape the '<' and '>' characters, otherwise they are interpreted as html tags
                        get_logger().info(f"Escaped suggestion summary: {suggestion_summary}")
                        suggestion_summary = suggestion_summary.replace("'<", "`<")
                        suggestion_summary = suggestion_summary.replace(">'", ">`")
                    if '`' in suggestion_summary:
                        suggestion_summary = replace_code_tags(suggestion_summary)

                    pr_body += f"""
**{suggestion_content}**

[{relevant_file} {range_str}]({code_snippet_link})

{example_code.rstrip()}
"""
                    if suggestion.get('score_why'):
                        pr_body += f"<details><summary>Suggestion importance[1-10]: {suggestion['score']}</summary>\n\n"
                        pr_body += f"__\n\nWhy: {suggestion['score_why']}\n\n"
                        pr_body += f"</details>"

                    pr_body += f"</details>"

                    # # add another column for 'score'
                    score_int = int(suggestion.get('score', 0))
                    score_str = f"{score_int}"
                    if get_settings().pr_code_suggestions.new_score_mechanism:
                        score_str = self.get_score_str(score_int)
                    pr_body += f"</td><td align=center>{score_str}\n\n"

                    pr_body += f"</td></tr>"
                    counter_suggestions += 1

                # pr_body += "</details>"
                # pr_body += """</td></tr>"""
            pr_body += """</tr></tbody></table>"""
            return pr_body
        except Exception as e:
            get_logger().info(f"Failed to publish summarized code suggestions, error: {e}")
            return ""

    def get_score_str(self, score: int) -> str:
        th_high = get_settings().pr_code_suggestions.get('new_score_mechanism_th_high', 9)
        th_medium = get_settings().pr_code_suggestions.get('new_score_mechanism_th_medium', 7)
        if score >= th_high:
            return "High"
        elif score >= th_medium:
            return "Medium"
        else:  # score < 7
            return "Low"

    async def self_reflect_on_suggestions(self,
                                          suggestion_list: List,
                                          patches_diff: str,
                                          model: str,
                                          prev_suggestions_str: str = "",
                                          dedicated_prompt: str = "") -> str:
        
        if not suggestion_list:
            get_logger().warning("[Reflecting] - No suggestions provided for self-reflection")
            return ""

        get_logger().info(f"[Reflecting] - Starting AI self-reflection on {len(suggestion_list)} suggestions using {model}")

        # Prepare suggestion string for prompt
        try:
            suggestion_str = ""
            for i, suggestion in enumerate(suggestion_list):
                suggestion_str += f"suggestion {i + 1}: " + str(suggestion) + '\n\n'
                              
        except Exception as e:
            get_logger().error("[Reflecting] - Failed to prepare suggestions for reflection", 
                              artifacts={'error': str(e), 'error_type': type(e).__name__})
            return ""

        # Build prompt variables
        try:
            # Load best practices for reflection
            from pr_agent.algo.utils import get_best_practices_content
            best_practices_content = get_best_practices_content(self.git_provider)
            
            variables = {
                'suggestion_list': suggestion_list,
                'suggestion_str': suggestion_str,
                "diff": patches_diff,
                'num_code_suggestions': len(suggestion_list),
                'prev_suggestions_str': prev_suggestions_str,
                "is_ai_metadata": get_settings().get("config.enable_ai_metadata", False),
                'duplicate_prompt_examples': get_settings().config.get('duplicate_prompt_examples', False),
                "include_context": get_settings().get("csharp_code_context_service.enabled", False),
                "context": self.context_data,
                "best_practices": best_practices_content
            }
            
            environment = Environment(undefined=StrictUndefined)

            # Choose prompt template
            if dedicated_prompt:
                get_logger().info(f"[Reflecting] - Using dedicated reflection prompt: {dedicated_prompt}")
                system_prompt_reflect = environment.from_string(
                    get_settings().get(dedicated_prompt).system).render(variables)
                user_prompt_reflect = environment.from_string(
                    get_settings().get(dedicated_prompt).user).render(variables)
            else:
                get_logger().info("[Reflecting] - Using standard reflection prompt")
                system_prompt_reflect = environment.from_string(
                    get_settings().pr_code_suggestions_reflect_prompt.system).render(variables)
                user_prompt_reflect = environment.from_string(
                    get_settings().pr_code_suggestions_reflect_prompt.user).render(variables)
                    
        except Exception as e:
            get_logger().error("[Reflecting] - Failed to build reflection prompts", 
                              artifacts={'error': str(e), 'error_type': type(e).__name__})
            return ""

        # Calculate token estimates
        prompt_tokens = 0
        try:
            prompt_tokens = self.token_handler.count_tokens(system_prompt_reflect + user_prompt_reflect)
            get_logger().info(f"[Reflecting] - Reflection prompt prepared - {prompt_tokens:,} tokens estimated")
        except Exception as e:
            get_logger().warning(f"[Reflecting] - Could not estimate reflection prompt tokens: {e}")
        
        # Log prompts at DEBUG level only
        get_logger().debug("[Reflecting] - Reflection System Prompt:", 
                          artifacts={'system_prompt': system_prompt_reflect})
        get_logger().debug("[Reflecting] - Reflection User Prompt:", 
                          artifacts={'user_prompt': user_prompt_reflect})

        # Track AI metrics for self-reflection
        from pr_agent.algo.token_handler import TokenUsageTracker
        reflection_token_tracker = TokenUsageTracker()
        
        # Make AI reflection call
        get_logger().info(f"[Reflecting] - Making AI reflection call to {model}...")
        try:
            with get_logger().contextualize(command="self_reflect_on_suggestions"):
                response_reflect, finish_reason_reflect, token_usage = await self.ai_handler.chat_completion(
                    model=model,
                    system=system_prompt_reflect,
                    user=user_prompt_reflect
                )
                
                # Track metrics for multi-model support
                self._track_ai_metrics(model, token_usage)
                
                # Log raw reflection response at DEBUG level only
                get_logger().debug("[Reflecting] - Reflection response received:", 
                                  artifacts={'response': response_reflect, 'finish_reason': finish_reason_reflect})
                
                get_logger().info("[Reflecting] - AI reflection call completed successfully")
                
        except Exception as e:
            get_logger().error("[Reflecting] - AI reflection call failed", 
                              artifacts={'error': str(e), 'error_type': type(e).__name__})
            return ""

        get_logger().info("[Reflecting] - Self-reflection completed successfully - response ready for analysis")
        return response_reflect

    async def _prepare_prediction(self, model: str) -> dict:
        get_logger().info("Preparing PR diff for AI analysis...")
        
        self.patches_diff = get_pr_diff(self.git_provider,
                                        self.token_handler,
                                        model,
                                        add_line_numbers_to_hunks=True,
                                        disable_extra_lines=False)
        self.patches_diff_list = [self.patches_diff]
        self.patches_diff_no_line_number = self.remove_line_numbers([self.patches_diff])[0]

        if self.patches_diff:
            get_logger().debug(f"🔍 PR diff prepared", artifact=self.patches_diff)
            self.prediction = await self._get_prediction(model, self.patches_diff, self.patches_diff_no_line_number)
        else:
            get_logger().warning(f"⚠️ Empty PR diff - no changes to analyze")
            self.prediction = None

        return self.prediction

    def _track_ai_metrics(self, model: str, token_usage: dict):
        """Track AI metrics for multiple models"""
        get_logger().debug(f"[AI] - _track_ai_metrics called with model: {model}, token_usage: {token_usage}")
        
        if not token_usage:
            get_logger().debug(f"[AI] - No token usage provided for {model} - skipping tracking")
            return
        
        input_tokens = token_usage.get('input_tokens', 0)
        output_tokens = token_usage.get('output_tokens', 0)
        
        get_logger().debug(f"[AI] - Extracted tokens for {model}: input={input_tokens}, output={output_tokens}")
        
        if model not in self.ai_models_metrics:
            self.ai_models_metrics[model] = {"input_tokens": 0, "output_tokens": 0}
            get_logger().debug(f"[AI] - Initialized metrics tracking for new model: {model}")
        
        self.ai_models_metrics[model]["input_tokens"] += input_tokens
        self.ai_models_metrics[model]["output_tokens"] += output_tokens
        
        get_logger().debug(f"[AI] - Updated metrics for {model}: total_input={self.ai_models_metrics[model]['input_tokens']}, "
                          f"total_output={self.ai_models_metrics[model]['output_tokens']}")
        get_logger().debug(f"[AI] - Current ai_models_metrics: {self.ai_models_metrics}")

    def _send_aggregated_ai_metrics(self, estimated_dev_hours_saved: Optional[float] = None):
        """Send aggregated AI metrics to dashboard"""
        get_logger().debug(f"[AI] - _send_aggregated_ai_metrics called - Dashboard available: {DASHBOARD_INTEGRATION_AVAILABLE}, "
                          f"Metrics count: {len(self.ai_models_metrics) if self.ai_models_metrics else 0}")
        
        if not DASHBOARD_INTEGRATION_AVAILABLE:
            get_logger().debug("[AI] - Dashboard integration not available - skipping AI metrics")
            return
            
        if not self.ai_models_metrics:
            get_logger().debug("[AI] - No AI metrics to send - ai_models_metrics is empty")
            return
        
        try:
            # Log what we're sending
            get_logger().debug(f"[AI] - Sending AI metrics: {self.ai_models_metrics}")
            
            update_operation_multi_model_ai_metrics(
                models_data=self.ai_models_metrics,
                estimated_dev_hours_saved=estimated_dev_hours_saved
            )
            
            # Log summary
            total_input = sum(data.get('input_tokens', 0) for data in self.ai_models_metrics.values())
            total_output = sum(data.get('output_tokens', 0) for data in self.ai_models_metrics.values())
            models_used = list(self.ai_models_metrics.keys())
            
            get_logger().info(f"[AI] - Sent aggregated metrics for models: {models_used}, "
                            f"Total tokens: {total_input + total_output} "
                            f"(Input: {total_input}, Output: {total_output})")
            
        except Exception as e:
            get_logger().warning(f"[AI] - Failed to send aggregated AI metrics: {e}")