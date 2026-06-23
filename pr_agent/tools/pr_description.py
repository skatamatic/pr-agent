import asyncio
import copy
import re
import traceback
from functools import partial
from typing import List, Tuple, Optional

import yaml
from jinja2 import Environment, StrictUndefined

from pr_agent.algo.ai_handlers.base_ai_handler import BaseAiHandler
from pr_agent.algo.ai_handlers.litellm_ai_handler import LiteLLMAIHandler
from pr_agent.algo.pr_processing import (OUTPUT_BUFFER_TOKENS_HARD_THRESHOLD,
                                         get_pr_diff,
                                         get_pr_diff_multiple_patchs,
                                         retry_with_fallback_models)
from pr_agent.algo.token_handler import TokenHandler
from pr_agent.algo.utils import (ModelType, PRDescriptionHeader, clip_tokens,
                                 get_max_tokens, get_user_labels, load_yaml,
                                 set_custom_labels,
                                 show_relevant_configurations)
from pr_agent.config_loader import get_settings
from pr_agent.git_providers import (GithubProvider, get_git_provider,
                                    get_git_provider_with_context)
from pr_agent.git_providers.git_provider import get_main_pr_language
from pr_agent.log import get_logger
from pr_agent.servers.help import HelpMessage
from pr_agent.tools.ticket_pr_compliance_check import (
    extract_and_cache_pr_tickets, extract_ticket_links_from_pr_description,
    extract_tickets)

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
    get_logger().debug("Dashboard integration not available for PR Description tool")


def should_publish_pr_description() -> bool:
    """Return True when generated PR descriptions should be written to the PR."""
    if not get_settings().config.publish_output:
        return False
    publish_description = get_settings().pr_description.get("publish_description", True)
    if isinstance(publish_description, str):
        return publish_description.strip().lower() not in {"false", "0", "no", "off"}
    return publish_description is not False


class PRDescription:
    def __init__(self, pr_url: str, args: list = None,
                 ai_handler: partial[BaseAiHandler,] = LiteLLMAIHandler):
        """
        Initialize the PRDescription object with the necessary attributes and objects for generating a PR description
        using an AI model.
        Args:
            pr_url (str): The URL of the pull request.
            args (list, optional): List of arguments passed to the PRDescription class. Defaults to None.
        """
        # Initialize the git provider and main PR language
        self.git_provider = get_git_provider_with_context(pr_url)
        self.main_pr_language = get_main_pr_language(
            self.git_provider.get_languages(), self.git_provider.get_files()
        )
        self.pr_id = self.git_provider.get_pr_id()
        self.keys_fix = ["filename:", "language:", "changes_summary:", "changes_title:", "description:", "title:"]

        if get_settings().pr_description.enable_semantic_files_types and not self.git_provider.is_supported(
                "gfm_markdown"):
            get_logger().debug(f"Disabling semantic files types for {self.pr_id}, gfm_markdown not supported.")
            get_settings().pr_description.enable_semantic_files_types = False

        # Initialize the AI handler
        # Handle both class and instance cases for ai_handler
        if isinstance(ai_handler, type):
            # ai_handler is a class, instantiate it
            self.ai_handler = ai_handler()
        else:
            # ai_handler is already an instance, use it directly
            self.ai_handler = ai_handler
        self.ai_handler.main_pr_language = self.main_pr_language

        # Multi-model AI metrics tracking
        self.ai_models_metrics = {}  # {"model_name": {"input_tokens": int, "output_tokens": int}}

        # Initialize the variables dictionary
        self.COLLAPSIBLE_FILE_LIST_THRESHOLD = get_settings().pr_description.get("collapsible_file_list_threshold", 8)
        self.vars = {
            "title": self.git_provider.pr.title,
            "branch": self.git_provider.get_pr_branch(),
            "description": self.git_provider.get_pr_description(full=False),
            "language": self.main_pr_language,
            "diff": "",  # empty diff for initial calculation
            "extra_instructions": get_settings().pr_description.extra_instructions,
            "commit_messages_str": self.git_provider.get_commit_messages(),
            "enable_custom_labels": get_settings().config.enable_custom_labels,
            "custom_labels_class": "",  # will be filled if necessary in 'set_custom_labels' function
            "enable_semantic_files_types": get_settings().pr_description.enable_semantic_files_types,
            "related_tickets": "",
            "include_file_summary_changes": len(self.git_provider.get_diff_files()) <= self.COLLAPSIBLE_FILE_LIST_THRESHOLD,
            "duplicate_prompt_examples": get_settings().config.get("duplicate_prompt_examples", False),
            "enable_pr_diagram": get_settings().pr_description.get("enable_pr_diagram", False),
        }

        self.user_description = self.git_provider.get_user_description()

        # Initialize the token handler
        self.token_handler = TokenHandler(
            self.git_provider.pr,
            self.vars,
            get_settings().pr_description_prompt.system,
            get_settings().pr_description_prompt.user,
        )

        # Initialize patches_diff and prediction attributes
        self.patches_diff = None
        self.prediction = None
        self.file_label_dict = None

    async def run(self):
        # Extract repository information for dashboard tracking
        repository = None
        pr_url = self.git_provider.get_pr_url()
        if DASHBOARD_INTEGRATION_AVAILABLE:
            try:
                repository = extract_repository_from_url(pr_url)
            except Exception as e:
                get_logger().debug(f"Failed to extract repository from URL: {e}")

        # Create operation context for dashboard tracking (error resilient)
        if DASHBOARD_INTEGRATION_AVAILABLE:
            try:
                # Only catch operation context setup errors, not operation execution errors
                operation_context_manager = operation_context(
                    operation_type=OperationType.GENERATING_DESCRIPTION,
                    command="describe",
                    repository=repository,
                    pr_url=pr_url,
                    installation_id=getattr(self.git_provider, 'installation_id', None),
                    sender=getattr(self.git_provider, 'sender', None)
                )
            except Exception as e:
                get_logger().warning(f"Dashboard operation context setup failed, continuing without tracking: {e}")
                # Fall through to execute without tracking
                get_logger().debug("Executing PR description without dashboard tracking (context setup failed)")
                return await self._run_without_tracking()
            
            # Execute with dashboard tracking - let operation failures be tracked
            with operation_context_manager as operation_id:
                get_logger().debug(f"PR description operation started with ID: {operation_id}")
                return await self._run_with_tracking(operation_id)
        
        # Execute without operation tracking (dashboard disabled)
        get_logger().debug("Executing PR description without dashboard tracking (dashboard disabled)")
        return await self._run_without_tracking()

    async def _run_with_tracking(self, operation_id: str):
        """Run PR description with dashboard operation tracking"""
        try:
            # Update operation status to processing
            update_operation_status("processing")
            
            # Execute the streamlined workflow with step tracking
            result = await self._execute_streamlined_workflow()
            
            # Update operation status based on result
            if result is not None:
                update_operation_status("completed", result_data={
                    "description_generated": True,
                    "files_processed": len(self.git_provider.get_files()) if self.git_provider.get_files() else 0,
                    "used_markers": get_settings().pr_description.use_description_markers
                })
                get_logger().info(f"PR description operation {operation_id} completed successfully")
            else:
                update_operation_status("failed", error_details="Description generation returned no result")
                get_logger().warning(f"PR description operation {operation_id} completed with no result")
            
            return result
            
        except Exception as e:
            # Update operation status to failed
            update_operation_status("failed", error_details=str(e))
            get_logger().error(f"PR description operation {operation_id} failed: {e}")
            raise

    async def _run_without_tracking(self):
        """Run PR description without dashboard tracking (fallback)"""
        return await self._execute_legacy_workflow()

    async def _execute_streamlined_workflow(self):
        """Execute the streamlined PR description workflow with step tracking"""
        try:
            # Step 1: Context and diff preparation
            if DASHBOARD_INTEGRATION_AVAILABLE:
                set_operation_step("Context")
            get_logger().debug("[Context] - Preparing PR description context and diff...")
            await self._prepare_context_and_tickets()
            
            # Step 2: Generate main description
            if DASHBOARD_INTEGRATION_AVAILABLE:
                set_operation_step("Generating")
            get_logger().debug("[Generating] - Generating PR description...")
            await self._generate_description()
            
            # Step 3: Prepare and process data
            if DASHBOARD_INTEGRATION_AVAILABLE:
                set_operation_step("Processing")
            get_logger().debug("[Processing] - Processing generated description...")
            result = await self._process_description_data()
            
            # Step 4: Dev time estimation (with insights capture)
            if DASHBOARD_INTEGRATION_AVAILABLE:
                set_operation_step("DevTime")
            get_logger().debug("[DevTime] - Estimating time savings...")
            dev_hours_saved, dev_time_insights = await self._estimate_dev_time_saved_with_insights(result)
            
            # Capture insights for dashboard
            if DASHBOARD_INTEGRATION_AVAILABLE:
                insights_data = {
                    'dev_time_analysis': dev_time_insights,  # Pass through the full AI estimation result
                    'description_generation': getattr(self, '_generation_insights', None)
                }
                await self._send_insights(insights_data)
            
            # Step 5: Send aggregated AI metrics
            if DASHBOARD_INTEGRATION_AVAILABLE:
                get_logger().debug("[AI] - Sending aggregated AI metrics...")
                self._send_aggregated_ai_metrics(dev_hours_saved)
            
            # Step 6: Publishing
            if DASHBOARD_INTEGRATION_AVAILABLE:
                set_operation_step("Publishing")
            get_logger().info("[Publishing] - Publishing PR description...")
            await self._publish_description_result(result, dev_hours_saved)
            
            return result
            
        except Exception as e:
            get_logger().error(f"Error in streamlined PR description workflow: {e}")
            raise

    async def _execute_legacy_workflow(self):
        """Main PR description logic (extracted for reuse with/without tracking)"""
        try:
            get_logger().info(f"Generating a PR description for pr_id: {self.pr_id}")
            relevant_configs = {'pr_description': dict(get_settings().pr_description),
                                'config': dict(get_settings().config)}
            get_logger().debug("Relevant configs", artifact=relevant_configs)
            if get_settings().config.publish_output and not get_settings().config.get('is_auto_command', False):
                self.git_provider.publish_comment("Preparing PR description...", is_temporary=True)

            # ticket extraction if exists
            await extract_and_cache_pr_tickets(self.git_provider, self.vars)

            await retry_with_fallback_models(self._prepare_prediction, ModelType.WEAK, tool_name='pr_description')

            if self.prediction:
                self._prepare_data()
            else:
                get_logger().warning(f"Empty prediction, PR: {self.pr_id}")
                self.git_provider.remove_initial_comment()
                return None

            if get_settings().pr_description.enable_semantic_files_types:
                self.file_label_dict = self._prepare_file_labels()

            pr_labels, pr_file_changes = [], []
            if get_settings().pr_description.publish_labels:
                pr_labels = self._prepare_labels()
            else:
                get_logger().debug(f"Publishing labels disabled")

            if get_settings().pr_description.use_description_markers:
                pr_title, pr_body, changes_walkthrough, pr_file_changes = self._prepare_pr_answer_with_markers()
            else:
                pr_title, pr_body, changes_walkthrough, pr_file_changes = self._prepare_pr_answer()
                if not self.git_provider.is_supported(
                        "publish_file_comments") or not get_settings().pr_description.inline_file_summary:
                    pr_body += "\n\n" + changes_walkthrough
            get_logger().debug("PR output", artifact={"title": pr_title, "body": pr_body})

            # Add help text if gfm_markdown is supported
            if self.git_provider.is_supported("gfm_markdown") and get_settings().pr_description.enable_help_text:
                pr_body += "<hr>\n\n<details> <summary><strong>✨ Describe tool usage guide:</strong></summary><hr> \n\n"
                pr_body += HelpMessage.get_describe_usage_guide()
                pr_body += "\n</details>\n"
            elif get_settings().pr_description.enable_help_comment and self.git_provider.is_supported("gfm_markdown"):
                if isinstance(self.git_provider, GithubProvider):
                    pr_body += ('\n\n___\n\n> <details> <summary>  Need help?</summary><li>Type <code>/help how to ...</code> '
                                'in the comments thread for any questions about PR-Agent usage.</li><li>Check out the '
                                '<a href="https://qodo-merge-docs.qodo.ai/usage-guide/">documentation</a> '
                                'for more information.</li></details>')
                else: # gitlab
                    pr_body += ("\n\n___\n\n<details><summary>Need help?</summary>- Type <code>/help how to ...</code> in the comments "
                                "thread for any questions about PR-Agent usage.<br>- Check out the "
                                "<a href='https://qodo-merge-docs.qodo.ai/usage-guide/'>documentation</a> for more information.</details>")
            # elif get_settings().pr_description.enable_help_comment:
            #     pr_body += '\n\n___\n\n> 💡 **PR-Agent usage**: Comment `/help "your question"` on any pull request to receive relevant information'

            # Output the relevant configurations if enabled
            if get_settings().get('config', {}).get('output_relevant_configurations', False):
                pr_body += show_relevant_configurations(relevant_section='pr_description')

            if should_publish_pr_description():

                # publish labels
                if get_settings().pr_description.publish_labels and pr_labels and self.git_provider.is_supported("get_labels"):
                    original_labels = self.git_provider.get_pr_labels(update=True)
                    get_logger().debug(f"original labels", artifact=original_labels)
                    user_labels = get_user_labels(original_labels)
                    new_labels = pr_labels + user_labels
                    get_logger().debug(f"published labels", artifact=new_labels)
                    if sorted(new_labels) != sorted(original_labels):
                        self.git_provider.publish_labels(new_labels)
                    else:
                        get_logger().debug(f"Labels are the same, not updating")

                # publish description
                if get_settings().pr_description.publish_description_as_comment:
                    full_markdown_description = f"## Title\n\n{pr_title}\n\n___\n{pr_body}"
                    if get_settings().pr_description.publish_description_as_comment_persistent:
                        self.git_provider.publish_persistent_comment(full_markdown_description,
                                                                     initial_header="## Title",
                                                                     update_header=True,
                                                                     name="describe",
                                                                     final_update_message=False, )
                    else:
                        self.git_provider.publish_comment(full_markdown_description)
                else:
                    self.git_provider.publish_description(pr_title, pr_body)

                    # publish final update message
                    if (get_settings().pr_description.final_update_message and not get_settings().config.get('is_auto_command', False)):
                        latest_commit_url = self.git_provider.get_latest_commit_url()
                        if latest_commit_url:
                            pr_url = self.git_provider.get_pr_url()
                            update_comment = f"**[PR Description]({pr_url})** updated to latest commit ({latest_commit_url})"
                            self.git_provider.publish_comment(update_comment)
                self.git_provider.remove_initial_comment()
                return pr_body
            else:
                get_logger().info('PR description generated, but not published (publish_output or publish_description disabled).')
                get_settings().data = {"artifact": pr_body}
                return pr_body
        except Exception as e:
            get_logger().error(f"Error generating PR description {self.pr_id}: {e}",
                               artifact={"traceback": traceback.format_exc()})
            raise

    async def _prepare_prediction(self, model: str) -> None:
        if get_settings().pr_description.use_description_markers and 'pr_agent:' not in self.user_description:
            get_logger().info("Markers were enabled, but user description does not contain markers. Skipping AI prediction")
            return None

        large_pr_handling = get_settings().pr_description.enable_large_pr_handling and "pr_description_only_files_prompts" in get_settings()
        output = await get_pr_diff(self.git_provider, self.token_handler, model, large_pr_handling=large_pr_handling, return_remaining_files=True)
        if isinstance(output, tuple):
            patches_diff, remaining_files_list = output
        else:
            patches_diff = output
            remaining_files_list = []

        if not large_pr_handling or patches_diff:
            self.patches_diff = patches_diff
            if patches_diff:
                # generate the prediction
                get_logger().debug(f"PR diff", artifact=self.patches_diff)
                self.prediction = await self._get_prediction(model, patches_diff, prompt="pr_description_prompt")

                # extend the prediction with additional files not shown
                if get_settings().pr_description.enable_semantic_files_types:
                    self.prediction = await self.extend_uncovered_files(self.prediction)
            else:
                get_logger().error(f"Error getting PR diff {self.pr_id}",
                                   artifact={"traceback": traceback.format_exc()})
                self.prediction = None
        else:
            # get the diff in multiple patches, with the token handler only for the files prompt
            get_logger().debug('large_pr_handling for describe')
            token_handler_only_files_prompt = TokenHandler(
                self.git_provider.pr,
                self.vars,
                get_settings().pr_description_only_files_prompts.system,
                get_settings().pr_description_only_files_prompts.user,
            )
            (patches_compressed_list, total_tokens_list, deleted_files_list, remaining_files_list, file_dict,
             files_in_patches_list) = get_pr_diff_multiple_patchs(
                self.git_provider, token_handler_only_files_prompt, model)

            # get the files prediction for each patch
            if not get_settings().pr_description.async_ai_calls:
                results = []
                for i, patches in enumerate(patches_compressed_list):  # sync calls
                    patches_diff = "\n".join(patches)
                    get_logger().debug(f"PR diff number {i + 1} for describe files")
                    prediction_files = await self._get_prediction(model, patches_diff,
                                                                  prompt="pr_description_only_files_prompts")
                    results.append(prediction_files)
            else:  # async calls
                tasks = []
                for i, patches in enumerate(patches_compressed_list):
                    if patches:
                        patches_diff = "\n".join(patches)
                        get_logger().debug(f"PR diff number {i + 1} for describe files")
                        task = asyncio.create_task(
                            self._get_prediction(model, patches_diff, prompt="pr_description_only_files_prompts"))
                        tasks.append(task)
                # Wait for all tasks to complete
                results = await asyncio.gather(*tasks)
            file_description_str_list = []
            for i, result in enumerate(results):
                prediction_files = result.strip().removeprefix('```yaml').strip('`').strip()
                if load_yaml(prediction_files, keys_fix_yaml=self.keys_fix) and prediction_files.startswith('pr_files'):
                    prediction_files = prediction_files.removeprefix('pr_files:').strip()
                    file_description_str_list.append(prediction_files)
                else:
                    get_logger().debug(f"failed to generate predictions in iteration {i + 1} for describe files")

            # generate files_walkthrough string, with proper token handling
            token_handler_only_description_prompt = TokenHandler(
                self.git_provider.pr,
                self.vars,
                get_settings().pr_description_only_description_prompts.system,
                get_settings().pr_description_only_description_prompts.user)
            files_walkthrough = "\n".join(file_description_str_list)
            files_walkthrough_prompt = copy.deepcopy(files_walkthrough)
            MAX_EXTRA_FILES_TO_PROMPT = 50
            if remaining_files_list:
                files_walkthrough_prompt += "\n\nNo more token budget. Additional unprocessed files:"
                for i, file in enumerate(remaining_files_list):
                    files_walkthrough_prompt += f"\n- {file}"
                    if i >= MAX_EXTRA_FILES_TO_PROMPT:
                        get_logger().debug(f"Too many remaining files, clipping to {MAX_EXTRA_FILES_TO_PROMPT}")
                        files_walkthrough_prompt += f"\n... and {len(remaining_files_list) - MAX_EXTRA_FILES_TO_PROMPT} more"
                        break
            if deleted_files_list:
                files_walkthrough_prompt += "\n\nAdditional deleted files:"
                for i, file in enumerate(deleted_files_list):
                    files_walkthrough_prompt += f"\n- {file}"
                    if i >= MAX_EXTRA_FILES_TO_PROMPT:
                        get_logger().debug(f"Too many deleted files, clipping to {MAX_EXTRA_FILES_TO_PROMPT}")
                        files_walkthrough_prompt += f"\n... and {len(deleted_files_list) - MAX_EXTRA_FILES_TO_PROMPT} more"
                        break
            tokens_files_walkthrough = len(
                token_handler_only_description_prompt.encoder.encode(files_walkthrough_prompt))
            total_tokens = token_handler_only_description_prompt.prompt_tokens + tokens_files_walkthrough
            max_tokens_model = get_max_tokens(model)
            if total_tokens > max_tokens_model - OUTPUT_BUFFER_TOKENS_HARD_THRESHOLD:
                # clip files_walkthrough to git the tokens within the limit
                files_walkthrough_prompt = clip_tokens(files_walkthrough_prompt,
                                                       max_tokens_model - OUTPUT_BUFFER_TOKENS_HARD_THRESHOLD - token_handler_only_description_prompt.prompt_tokens,
                                                       num_input_tokens=tokens_files_walkthrough)

            # PR header inference
            get_logger().debug(f"PR diff only description", artifact=files_walkthrough_prompt)
            prediction_headers = await self._get_prediction(model, patches_diff=files_walkthrough_prompt,
                                                            prompt="pr_description_only_description_prompts")
            prediction_headers = prediction_headers.strip().removeprefix('```yaml').strip('`').strip()

            # extend the tables with the files not shown
            files_walkthrough_extended = await self.extend_uncovered_files(files_walkthrough)

            # final processing
            self.prediction = prediction_headers + "\n" + "pr_files:\n" + files_walkthrough_extended
            if not load_yaml(self.prediction, keys_fix_yaml=self.keys_fix):
                get_logger().error(f"Error getting valid YAML in large PR handling for describe {self.pr_id}")
                if load_yaml(prediction_headers, keys_fix_yaml=self.keys_fix):
                    get_logger().debug(f"Using only headers for describe {self.pr_id}")
                    self.prediction = prediction_headers

    async def extend_uncovered_files(self, original_prediction: str) -> str:
        try:
            prediction = original_prediction

            # get the original prediction filenames
            original_prediction_loaded = load_yaml(original_prediction, keys_fix_yaml=self.keys_fix)
            if isinstance(original_prediction_loaded, list):
                original_prediction_dict = {"pr_files": original_prediction_loaded}
            else:
                original_prediction_dict = original_prediction_loaded
            if original_prediction_dict:
                filenames_predicted = [file.get('filename', '').strip() for file in original_prediction_dict.get('pr_files', [])]
            else:
                filenames_predicted = []

            # extend the prediction with additional files not included in the original prediction
            pr_files = self.git_provider.get_diff_files()
            prediction_extra = "pr_files:"
            MAX_EXTRA_FILES_TO_OUTPUT = 100
            counter_extra_files = 0
            for file in pr_files:
                if file.filename in filenames_predicted:
                    continue

                # add up to MAX_EXTRA_FILES_TO_OUTPUT files
                counter_extra_files += 1
                if counter_extra_files > MAX_EXTRA_FILES_TO_OUTPUT:
                    extra_file_yaml = f"""\
- filename: |
    Additional files not shown
  changes_title: |
    ...
  label: |
    additional files
"""
                    prediction_extra = prediction_extra + "\n" + extra_file_yaml.strip()
                    get_logger().debug(f"Too many remaining files, clipping to {MAX_EXTRA_FILES_TO_OUTPUT}")
                    break

                extra_file_yaml = f"""\
- filename: |
    {file.filename}
  changes_title: |
    ...
  label: |
    additional files
"""
                prediction_extra = prediction_extra + "\n" + extra_file_yaml.strip()

            # merge the two dictionaries
            if counter_extra_files > 0:
                get_logger().info(f"Adding {counter_extra_files} unprocessed extra files to table prediction")
                prediction_extra_dict = load_yaml(prediction_extra, keys_fix_yaml=self.keys_fix)
                if original_prediction_dict and isinstance(original_prediction_dict, dict) and \
                        isinstance(prediction_extra_dict, dict) and "pr_files" in prediction_extra_dict:
                    if "pr_files" in original_prediction_dict:
                        original_prediction_dict["pr_files"].extend(prediction_extra_dict["pr_files"])
                    else:
                        original_prediction_dict["pr_files"] = prediction_extra_dict["pr_files"]
                    new_yaml = yaml.dump(original_prediction_dict)
                    if load_yaml(new_yaml, keys_fix_yaml=self.keys_fix):
                        prediction = new_yaml
                if isinstance(original_prediction, list):
                    prediction = yaml.dump(original_prediction_dict["pr_files"])

            return prediction
        except Exception as e:
            get_logger().exception(f"Error extending uncovered files {self.pr_id}", artifact={"error": e})
            return original_prediction


    async def extend_additional_files(self, remaining_files_list) -> str:
        prediction = self.prediction
        try:
            original_prediction_dict = load_yaml(self.prediction, keys_fix_yaml=self.keys_fix)
            prediction_extra = "pr_files:"
            for file in remaining_files_list:
                extra_file_yaml = f"""\
- filename: |
    {file}
  changes_summary: |
    ...
  changes_title: |
    ...
  label: |
    additional files (token-limit)
"""
                prediction_extra = prediction_extra + "\n" + extra_file_yaml.strip()
            prediction_extra_dict = load_yaml(prediction_extra, keys_fix_yaml=self.keys_fix)
            # merge the two dictionaries
            if isinstance(original_prediction_dict, dict) and isinstance(prediction_extra_dict, dict):
                original_prediction_dict["pr_files"].extend(prediction_extra_dict["pr_files"])
                new_yaml = yaml.dump(original_prediction_dict)
                if load_yaml(new_yaml, keys_fix_yaml=self.keys_fix):
                    prediction = new_yaml
            return prediction
        except Exception as e:
            get_logger().error(f"Error extending additional files {self.pr_id}: {e}")
            return self.prediction

    async def _get_prediction(self, model: str, patches_diff: str, prompt="pr_description_prompt") -> str:
        variables = copy.deepcopy(self.vars)
        variables["diff"] = patches_diff  # update diff

        environment = Environment(undefined=StrictUndefined)
        set_custom_labels(variables, self.git_provider)
        self.variables = variables

        system_prompt = environment.from_string(get_settings().get(prompt, {}).get("system", "")).render(self.variables)
        user_prompt = environment.from_string(get_settings().get(prompt, {}).get("user", "")).render(self.variables)

        get_logger().info(f"[Generating] - Making AI call for description generation using {model}...")
        
        try:
            response, finish_reason, token_usage = await self.ai_handler.chat_completion(
                model=model,
                temperature=get_settings().config.temperature,
                system=system_prompt,
                user=user_prompt
            )
            
            # Track AI metrics for multi-model support
            if token_usage:
                self._track_ai_metrics(model, token_usage)
            
            get_logger().info(f"[Generating] - AI call completed successfully", 
                             artifacts={
                                 'model': model,
                                 'finish_reason': finish_reason,
                                 'response_length': len(response) if response else 0,
                                 'prompt_type': prompt
                             })
            
            return response
            
        except Exception as e:
            get_logger().error(f"[Generating] - AI call failed for model {model}: {e}")
            
            # Still track metrics even on failure if we have token usage data
            if 'token_usage' in locals() and token_usage:
                self._track_ai_metrics(model, token_usage)
            
            raise

    def _estimate_description_dev_hours_saved(self, model: str, input_tokens: int = None, 
                                            output_tokens: int = None, files_count: int = 0,
                                            prompt_type: str = "pr_description_prompt") -> float:
        """
        Estimate developer hours saved for PR description operation
        """
        try:
            # Base time for manual PR description writing (varies by complexity)
            if prompt_type == "pr_description_prompt":
                base_description_hours = 0.25  # 15 minutes base for full description
            elif "only_files" in prompt_type:
                base_description_hours = 0.1   # 6 minutes for file descriptions only
            elif "only_description" in prompt_type:
                base_description_hours = 0.15  # 9 minutes for description headers only
            else:
                base_description_hours = 0.25  # Default
            
            # Adjust based on number of files
            if files_count > 15:
                base_description_hours = 0.5   # 30 minutes for large PRs
            elif files_count > 8:
                base_description_hours = 0.33  # 20 minutes for medium PRs
            elif files_count > 3:
                base_description_hours = 0.25  # 15 minutes for small-medium PRs
            
            # Adjust based on token complexity (if available)
            complexity_multiplier = 1.0
            if input_tokens and output_tokens:
                total_tokens = input_tokens + output_tokens
                if total_tokens > 2500:
                    complexity_multiplier = 1.4  # Complex description
                elif total_tokens > 1200:
                    complexity_multiplier = 1.2  # Medium complexity
                elif total_tokens < 400:
                    complexity_multiplier = 0.8  # Simple description
            
            # Adjust based on model capability
            model_multiplier = 1.0
            model_lower = model.lower()
            if any(name in model_lower for name in ['gpt-4', 'claude-3-opus', 'claude-3-5-sonnet']):
                model_multiplier = 1.2  # High-quality models save more time
            elif any(name in model_lower for name in ['gpt-3.5', 'claude-3-sonnet']):
                model_multiplier = 1.0  # Standard models
            else:
                model_multiplier = 0.8  # Lower capability models
            
            # Calculate final estimate
            estimated_hours = base_description_hours * complexity_multiplier * model_multiplier
            
            # Cap at reasonable bounds (allow negative values for time wasted)
            return max(-2.0, min(2.0, estimated_hours))
            
        except Exception as e:
            get_logger().debug(f"Failed to estimate description dev hours: {e}")
            return 0.25  # Default fallback

    async def _estimate_description_dev_hours_saved_ai_full(self, model: str, input_tokens: int = None, 
                                                           output_tokens: int = None, files_count: int = 0,
                                                           prompt_type: str = "pr_description_prompt", 
                                                           diff: str = None, description_content: str = None) -> dict:
        """
        Estimate developer hours saved using AI-powered analysis - returns full AI estimation result
        """
        try:
            if diff and description_content:
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
                
                get_logger().info(f"[DevTime] - Making AI call for description time estimation using model: {model}")
                
                # Get the FULL AI estimation result
                estimation_result = await estimator.estimate_description_time_savings(
                    diff=diff,
                    ai_description_content=description_content,
                    language=self.main_pr_language,
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

    async def _estimate_description_dev_hours_saved_ai(self, model: str, input_tokens: int = None, 
                                                      output_tokens: int = None, files_count: int = 0,
                                                      prompt_type: str = "pr_description_prompt", 
                                                      diff: str = None, description_content: str = None) -> float:
        """
        Estimate developer hours saved using AI-powered analysis of the description
        """
        try:
            if diff and description_content:
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
                
                # Use the description-specific prompt for time estimation
                prompt_type_for_estimation = "pr_description_dev_time_estimation_prompt" if prompt_type == "pr_description_dev_time_estimation_prompt" else "pr_description_prompt"
                
                estimation_result = await estimator.estimate_description_time_savings(
                    diff=diff,
                    ai_description_content=description_content,
                    language=self.main_pr_language,
                    files_changed=files_count,
                    lines_added=lines_added,
                    lines_deleted=lines_deleted,
                    model=model
                )
                
                if estimation_result and 'final_assessment' in estimation_result:
                    estimated_hours = estimation_result['final_assessment'].get('total_developer_hours_saved', 0.25)
                    confidence = estimation_result['final_assessment'].get('confidence_level', 'medium')
                    
                    get_logger().info(f"AI-powered description time estimation: {estimated_hours} hours (confidence: {confidence})", 
                                    artifacts={'estimation_details': estimation_result})
                    return float(estimated_hours)
            
            # Fall back to heuristic estimation
            return self._estimate_description_dev_hours_saved(model, input_tokens, output_tokens, files_count, prompt_type)
            
        except Exception as e:
            get_logger().debug(f"AI time estimation failed: {e}")
            return self._estimate_description_dev_hours_saved(model, input_tokens, output_tokens, files_count, prompt_type)

    async def _prepare_context_and_tickets(self):
        """Step 1: Prepare context and extract ticket information"""
        try:
            get_logger().info("[Context] - Extracting ticket information...")
            # Extract ticket information if exists
            await extract_and_cache_pr_tickets(self.git_provider, self.vars)
            get_logger().info("[Context] - Context preparation completed")
        except Exception as e:
            get_logger().error(f"[Context] - Failed to prepare context: {e}")
            raise

    async def _generate_description(self):
        """Step 2: Generate main PR description using AI"""
        try:
            get_logger().info("[Generating] - Starting description generation...")
            
            # Initialize progress message if enabled
            if get_settings().config.publish_output and not get_settings().config.get('is_auto_command', False):
                self.git_provider.publish_comment("Preparing PR description...", is_temporary=True)
            
            # Generate the main prediction using AI
            await retry_with_fallback_models(self._prepare_prediction, ModelType.WEAK, tool_name='pr_description')
            
            if not self.prediction:
                get_logger().warning(f"[Generating] - Empty prediction for PR: {self.pr_id}")
                self.git_provider.remove_initial_comment()
                raise Exception("Description generation returned empty result")
            
            get_logger().info("[Generating] - Description generation completed successfully")
            
        except Exception as e:
            get_logger().error(f"[Generating] - Failed to generate description: {e}")
            raise

    async def _process_description_data(self):
        """Step 3: Process and prepare the generated description data"""
        try:
            get_logger().info("[Processing] - Processing generated description data...")
            
            # Prepare the data dictionary from AI prediction
            self._prepare_data()
            
            # Prepare file labels if semantic files are enabled
            if get_settings().pr_description.enable_semantic_files_types:
                self.file_label_dict = self._prepare_file_labels()
            
            # Prepare labels and PR structure
            pr_labels, pr_file_changes = [], []
            if get_settings().pr_description.publish_labels:
                pr_labels = self._prepare_labels()
            
            # Process description based on marker mode
            if get_settings().pr_description.use_description_markers:
                pr_title, pr_body, changes_walkthrough, pr_file_changes = self._prepare_pr_answer_with_markers()
            else:
                pr_title, pr_body, changes_walkthrough, pr_file_changes = self._prepare_pr_answer()
            
            result = {
                'title': pr_title,
                'body': pr_body,
                'changes_walkthrough': changes_walkthrough,
                'pr_file_changes': pr_file_changes,
                'labels': pr_labels,
                'data': self.data
            }
            
            get_logger().info("[Processing] - Description data processing completed", 
                             artifacts={'result_keys': list(result.keys())})
            
            return result
            
        except Exception as e:
            get_logger().error(f"[Processing] - Failed to process description data: {e}")
            raise

    async def _estimate_dev_time_saved_with_insights(self, result):
        """Step 4: Estimate dev time savings with detailed insights capture"""
        try:
            get_logger().info("[DevTime] - Starting dev time estimation with insights...")
            
            # Calculate file metrics
            files_count = len(self.git_provider.get_files()) if self.git_provider.get_files() else 0
            
            # Try AI-powered estimation first if we have enough data
            if result and 'body' in result and self.patches_diff:
                get_logger().info("[DevTime] - Using AI-powered time estimation...")
                
                # Calculate input/output tokens from the AI generation
                total_input_tokens = sum(data.get('input_tokens', 0) for data in self.ai_models_metrics.values())
                total_output_tokens = sum(data.get('output_tokens', 0) for data in self.ai_models_metrics.values())
                
                try:
                    # Get the FULL AI estimation result (not just the hours)
                    estimation_result = await self._estimate_description_dev_hours_saved_ai_full(
                        model=get_settings().config.model,
                        input_tokens=total_input_tokens,
                        output_tokens=total_output_tokens,
                        files_count=files_count,
                        prompt_type="pr_description_dev_time_estimation_prompt",
                        diff=self.patches_diff,
                        description_content=result['body']
                    )
                    
                    # Extract final hours estimate
                    estimated_hours = 0.0
                    if estimation_result and 'final_assessment' in estimation_result:
                        estimated_hours = estimation_result['final_assessment'].get('total_developer_hours_saved', 0.0)
                        # Cap the result at reasonable bounds
                        estimated_hours = max(-2.0, min(2.0, float(estimated_hours)))
                    
                    get_logger().info(f"[DevTime] - AI estimation completed: {estimated_hours} hours", 
                                     artifacts={'full_estimation_result': estimation_result})
                    
                    return estimated_hours, estimation_result
                    
                except Exception as e:
                    get_logger().warning(f"[DevTime] - AI estimation failed, falling back to heuristic: {e}")
            
            # Fallback to heuristic estimation
            get_logger().info("[DevTime] - Using heuristic time estimation...")
            total_tokens = sum(data.get('input_tokens', 0) + data.get('output_tokens', 0) 
                              for data in self.ai_models_metrics.values())
            
            dev_hours_saved = self._estimate_description_dev_hours_saved(
                model=get_settings().config.model,
                input_tokens=total_tokens // 2,  # Rough split
                output_tokens=total_tokens // 2,
                files_count=files_count
            )
            
            get_logger().info(f"[DevTime] - Heuristic estimation completed: {dev_hours_saved} hours")
            
            # Return None for insights since this is heuristic, not AI-powered
            return dev_hours_saved, None
            
        except Exception as e:
            get_logger().error(f"[DevTime] - Failed to estimate dev time: {e}")
            return 0.25, None  # Return None for insights on error

    async def _send_insights(self, insights_data: dict):
        """Send insights data to dashboard"""
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

    async def _publish_description_result(self, result, dev_hours_saved):
        """Step 5: Publish the final PR description result"""
        try:
            get_logger().info("[Publishing] - Publishing PR description result...")
            
            if not should_publish_pr_description():
                get_logger().info("[Publishing] - Output publishing disabled, storing as data artifact")
                get_settings().data = {"artifact": result['body']}
                return
            
            # Remove temporary comment
            self.git_provider.remove_initial_comment()
            
            # Set PR title if enabled
            if get_settings().pr_description.generate_ai_title and result.get('title'):
                self.git_provider.publish_description(result['title'], result['body'])
            else:
                # Use original title when AI title generation is disabled
                original_title = self.vars.get("title", "PR Description")
                self.git_provider.publish_description(original_title, result['body'])
            
            # Publish labels if enabled and supported
            if get_settings().pr_description.publish_labels and result.get('labels') and self.git_provider.is_supported("get_labels"):
                self.git_provider.publish_labels(result['labels'])
            
            # Send aggregated AI metrics to dashboard
            self._send_aggregated_ai_metrics(dev_hours_saved)
            
            get_logger().info("[Publishing] - PR description published successfully", 
                             artifacts={
                                 'title_changed': get_settings().pr_description.generate_ai_title and result.get('title'),
                                 'labels_published': get_settings().pr_description.publish_labels and result.get('labels'),
                                 'body_length': len(result['body']) if result.get('body') else 0
                             })
            
        except Exception as e:
            get_logger().error(f"[Publishing] - Failed to publish description: {e}")
            raise

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

    def _send_aggregated_ai_metrics(self, estimated_dev_hours_saved):
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

    def _prepare_data(self):
        # Load the AI prediction data into a dictionary
        self.data = load_yaml(self.prediction.strip(), keys_fix_yaml=self.keys_fix)

        if get_settings().pr_description.add_original_user_description and self.user_description:
            self.data["User Description"] = self.user_description

        # re-order keys
        if 'User Description' in self.data:
            self.data['User Description'] = self.data.pop('User Description')
        if 'title' in self.data:
            self.data['title'] = self.data.pop('title')
        if 'type' in self.data:
            self.data['type'] = self.data.pop('type')
        if 'labels' in self.data:
            self.data['labels'] = self.data.pop('labels')
        if 'description' in self.data:
            self.data['description'] = self.data.pop('description')
        if 'changes_diagram' in self.data:
            changes_diagram = self.data.pop('changes_diagram').strip()
            if changes_diagram.startswith('```'):
                if not changes_diagram.endswith('```'):  # fallback for missing closing
                    changes_diagram += '\n```'
                self.data['changes_diagram'] = '\n'+ changes_diagram
        if 'pr_files' in self.data:
            self.data['pr_files'] = self.data.pop('pr_files')

    def _prepare_labels(self) -> List[str]:
        pr_labels = []

        # If the 'PR Type' key is present in the dictionary, split its value by comma and assign it to 'pr_types'
        if 'labels' in self.data and self.data['labels']:
            if type(self.data['labels']) == list:
                pr_labels = self.data['labels']
            elif type(self.data['labels']) == str:
                pr_labels = self.data['labels'].split(',')
        elif 'type' in self.data and self.data['type'] and get_settings().pr_description.publish_labels:
            if type(self.data['type']) == list:
                pr_labels = self.data['type']
            elif type(self.data['type']) == str:
                pr_labels = self.data['type'].split(',')
        pr_labels = [label.strip() for label in pr_labels]

        # convert lowercase labels to original case
        try:
            if "labels_minimal_to_labels_dict" in self.variables:
                d: dict = self.variables["labels_minimal_to_labels_dict"]
                for i, label_i in enumerate(pr_labels):
                    if label_i in d:
                        pr_labels[i] = d[label_i]
        except Exception as e:
            get_logger().error(f"Error converting labels to original case {self.pr_id}: {e}")
        return pr_labels

    def _prepare_pr_answer_with_markers(self) -> Tuple[str, str, str, List[dict]]:
        get_logger().info(f"Using description marker replacements {self.pr_id}")

        # Remove the 'PR Title' key from the dictionary
        ai_title = self.data.pop('title', self.vars["title"])
        if (not get_settings().pr_description.generate_ai_title):
            # Assign the original PR title to the 'title' variable
            title = self.vars["title"]
        else:
            # Assign the value of the 'PR Title' key to 'title' variable
            title = ai_title
      
        body = self.user_description
        if get_settings().pr_description.include_generated_by_header:
            ai_header = f"### 🤖 Generated by PR Agent at {self.git_provider.last_commit_id.sha}\n\n"
        else:
            ai_header = ""

        ai_type = self.data.get('type')
        if ai_type and not re.search(r'<!--\s*pr_agent:type\s*-->', body):
            if isinstance(ai_type, list):
                pr_type = ', '.join(str(t) for t in ai_type)
            else:
                pr_type = ai_type
            pr_type = f"{ai_header}{pr_type}"
            body = body.replace('pr_agent:type', pr_type)

        ai_summary = self.data.get('description')
        if ai_summary and not re.search(r'<!--\s*pr_agent:summary\s*-->', body):
            summary = f"{ai_header}{ai_summary}"
            body = body.replace('pr_agent:summary', summary)

        ai_walkthrough = self.data.get('pr_files')
        walkthrough_gfm = ""
        pr_file_changes = []
        if ai_walkthrough and not re.search(r'<!--\s*pr_agent:walkthrough\s*-->', body):
            try:
                walkthrough_gfm, pr_file_changes = self.process_pr_files_prediction(walkthrough_gfm,
                                                                                    self.file_label_dict)
                body = body.replace('pr_agent:walkthrough', walkthrough_gfm)
            except Exception as e:
                get_logger().error(f"Failing to process walkthrough {self.pr_id}: {e}")
                body = body.replace('pr_agent:walkthrough', "")

        return title, body, walkthrough_gfm, pr_file_changes

    def _prepare_pr_answer(self) -> Tuple[str, str, str, List[dict]]:
        """
        Prepare the PR description based on the AI prediction data.

        Returns:
        - title: a string containing the PR title.
        - pr_body: a string containing the PR description body in a markdown format.
        """

        # Iterate over the dictionary items and append the key and value to 'markdown_text' in a markdown format
        markdown_text = ""
        # Don't display 'PR Labels'
        if 'labels' in self.data and self.git_provider.is_supported("get_labels"):
            self.data.pop('labels')
        if not get_settings().pr_description.enable_pr_type:
            self.data.pop('type')
        for key, value in self.data.items():
            markdown_text += f"## **{key}**\n\n"
            markdown_text += f"{value}\n\n"

        # Remove the 'PR Title' key from the dictionary
        ai_title = self.data.pop('title', self.vars["title"])
        if (not get_settings().pr_description.generate_ai_title):
            # Assign the original PR title to the 'title' variable
            title = self.vars["title"]
        else:
            # Assign the value of the 'PR Title' key to 'title' variable
            title = ai_title

        # Iterate over the remaining dictionary items and append the key and value to 'pr_body' in a markdown format,
        # except for the items containing the word 'walkthrough'
        pr_body, changes_walkthrough = "", ""
        pr_file_changes = []
        for idx, (key, value) in enumerate(self.data.items()):
            if key == 'pr_files':
                value = self.file_label_dict
            else:
                key_publish = key.rstrip(':').replace("_", " ").capitalize()
                if key_publish == "Type":
                    key_publish = "PR Type"
                # elif key_publish == "Description":
                #     key_publish = "PR Description"
                pr_body += f"### **{key_publish}**\n"
            if 'walkthrough' in key.lower():
                if self.git_provider.is_supported("gfm_markdown"):
                    pr_body += "<details> <summary>files:</summary>\n\n"
                for file in value:
                    filename = file['filename'].replace("'", "`")
                    description = file['changes_in_file']
                    pr_body += f'- `{filename}`: {description}\n'
                if self.git_provider.is_supported("gfm_markdown"):
                    pr_body += "</details>\n"
            elif 'pr_files' in key.lower() and get_settings().pr_description.enable_semantic_files_types:
                changes_walkthrough, pr_file_changes = self.process_pr_files_prediction(changes_walkthrough, value)
                changes_walkthrough = f"{PRDescriptionHeader.CHANGES_WALKTHROUGH.value}\n{changes_walkthrough}"
            elif key.lower().strip() == 'description':
                if isinstance(value, list):
                    value = ', '.join(v.rstrip() for v in value)
                value = value.replace('\n-', '\n\n-').strip() # makes the bullet points more readable by adding double space
                pr_body += f"{value}\n"
            else:
                # if the value is a list, join its items by comma
                if isinstance(value, list):
                    value = ', '.join(v.rstrip() for v in value)
                pr_body += f"{value}\n"
            if idx < len(self.data) - 1:
                pr_body += "\n\n___\n\n"

        return title, pr_body, changes_walkthrough, pr_file_changes,

    def _prepare_file_labels(self):
        file_label_dict = {}
        if (not self.data or not isinstance(self.data, dict) or
                'pr_files' not in self.data or not self.data['pr_files']):
            return file_label_dict
        for file in self.data['pr_files']:
            try:
                required_fields = ['changes_title', 'filename', 'label']
                if not all(field in file for field in required_fields):
                    # can happen for example if a YAML generation was interrupted in the middle (no more tokens)
                    get_logger().warning(f"Missing required fields in file label dict {self.pr_id}, skipping file",
                                         artifact={"file": file})
                    continue
                if not file.get('changes_title'):
                    get_logger().warning(f"Empty changes title or summary in file label dict {self.pr_id}, skipping file",
                                         artifact={"file": file})
                    continue
                filename = file['filename'].replace("'", "`").replace('"', '`')
                changes_summary = file.get('changes_summary', "").strip()
                changes_title = file['changes_title'].strip()
                label = file.get('label').strip().lower()
                if label not in file_label_dict:
                    file_label_dict[label] = []
                file_label_dict[label].append((filename, changes_title, changes_summary))
            except Exception as e:
                get_logger().error(f"Error preparing file label dict {self.pr_id}: {e}")
                pass
        return file_label_dict

    def process_pr_files_prediction(self, pr_body, value):
        pr_comments = []
        # logic for using collapsible file list
        use_collapsible_file_list = get_settings().pr_description.collapsible_file_list
        num_files = 0
        if value:
            for semantic_label in value.keys():
                num_files += len(value[semantic_label])
        if use_collapsible_file_list == "adaptive":
            use_collapsible_file_list = num_files > self.COLLAPSIBLE_FILE_LIST_THRESHOLD

        if not self.git_provider.is_supported("gfm_markdown"):
            return pr_body, pr_comments
        try:
            pr_body += "<table>"
            header = f"Relevant files"
            delta = 75
            # header += "&nbsp; " * delta
            pr_body += f"""<thead><tr><th></th><th align="left">{header}</th></tr></thead>"""
            pr_body += """<tbody>"""
            for semantic_label in value.keys():
                s_label = semantic_label.strip("'").strip('"')
                pr_body += f"""<tr><td><strong>{s_label.capitalize()}</strong></td>"""
                list_tuples = value[semantic_label]

                if use_collapsible_file_list:
                    pr_body += f"""<td><details><summary>{len(list_tuples)} files</summary><table>"""
                else:
                    pr_body += f"""<td><table>"""
                for filename, file_changes_title, file_change_description in list_tuples:
                    filename = filename.replace("'", "`").rstrip()
                    filename_publish = filename.split("/")[-1]
                    if file_changes_title and file_changes_title.strip() != "...":
                        file_changes_title_code = f"<code>{file_changes_title}</code>"
                        file_changes_title_code_br = insert_br_after_x_chars(file_changes_title_code, x=(delta - 5)).strip()
                        if len(file_changes_title_code_br) < (delta - 5):
                            file_changes_title_code_br += "&nbsp; " * ((delta - 5) - len(file_changes_title_code_br))
                        filename_publish = f"<strong>{filename_publish}</strong><dd>{file_changes_title_code_br}</dd>"
                    else:
                        filename_publish = f"<strong>{filename_publish}</strong>"
                    diff_plus_minus = ""
                    delta_nbsp = ""
                    diff_files = self.git_provider.get_diff_files()
                    for f in diff_files:
                        if f.filename.lower().strip('/') == filename.lower().strip('/'):
                            num_plus_lines = f.num_plus_lines
                            num_minus_lines = f.num_minus_lines
                            diff_plus_minus += f"+{num_plus_lines}/-{num_minus_lines}"
                            if len(diff_plus_minus) > 12 or diff_plus_minus == "+0/-0":
                                diff_plus_minus = "[link]"
                            delta_nbsp = "&nbsp; " * max(0, (8 - len(diff_plus_minus)))
                            break

                    # try to add line numbers link to code suggestions
                    link = ""
                    if hasattr(self.git_provider, 'get_line_link'):
                        filename = filename.strip()
                        link = self.git_provider.get_line_link(filename, relevant_line_start=-1)
                    if (not link or not diff_plus_minus) and ('additional files' not in filename.lower()):
                        # get_logger().warning(f"Error getting line link for '{filename}'")
                        link = ""
                        # continue

                    # Add file data to the PR body
                    file_change_description_br = insert_br_after_x_chars(file_change_description, x=(delta - 5))
                    pr_body = self.add_file_data(delta_nbsp, diff_plus_minus, file_change_description_br, filename,
                                                 filename_publish, link, pr_body)

                # Close the collapsible file list
                if use_collapsible_file_list:
                    pr_body += """</table></details></td></tr>"""
                else:
                    pr_body += """</table></td></tr>"""
            pr_body += """</tr></tbody></table>"""

        except Exception as e:
            get_logger().error(f"Error processing PR files to markdown {self.pr_id}: {str(e)}")
            pass
        return pr_body, pr_comments

    def add_file_data(self, delta_nbsp, diff_plus_minus, file_change_description_br, filename, filename_publish, link,
                      pr_body) -> str:

        if not file_change_description_br:
            pr_body += f"""
<tr>
  <td>{filename_publish}</td>
  <td><a href="{link}">{diff_plus_minus}</a>{delta_nbsp}</td>

</tr>
"""
        else:
            pr_body += f"""
<tr>
  <td>
    <details>
      <summary>{filename_publish}</summary>
<hr>

{filename}

{file_change_description_br}


</details>


  </td>
  <td><a href="{link}">{diff_plus_minus}</a>{delta_nbsp}</td>

</tr>
"""
        return pr_body

def count_chars_without_html(string):
    if '<' not in string:
        return len(string)
    no_html_string = re.sub('<[^>]+>', '', string)
    return len(no_html_string)


def insert_br_after_x_chars(text: str, x=70):
    """
    Insert <br> into a string after a word that increases its length above x characters.
    Use proper HTML tags for code and new lines.
    """

    if not text:
        return ""
    if count_chars_without_html(text) < x:
        return text

    # replace odd instances of ` with <code> and even instances of ` with </code>
    text = replace_code_tags(text)

    # convert list items to <li>
    if text.startswith("- ") or text.startswith('* '):
        text = "<li>" + text[2:]
    text = text.replace("\n- ", '<br><li> ').replace("\n - ", '<br><li> ')
    text = text.replace("\n* ", '<br><li> ').replace("\n * ", '<br><li> ')

    # convert new lines to <br>
    text = text.replace("\n", '<br>')

    # split text into lines
    lines = text.split('<br>')
    words = []
    for i, line in enumerate(lines):
        words += line.split(' ')
        if i < len(lines) - 1:
            words[-1] += "<br>"

    new_text = []
    is_inside_code = False
    current_length = 0
    for word in words:
        is_saved_word = False
        if word == "<code>" or word == "</code>" or word == "<li>" or word == "<br>":
            is_saved_word = True

        len_word = count_chars_without_html(word)
        if not is_saved_word and (current_length + len_word > x):
            if is_inside_code:
                new_text.append("</code><br><code>")
            else:
                new_text.append("<br>")
            current_length = 0  # Reset counter
        new_text.append(word + " ")

        if not is_saved_word:
            current_length += len_word + 1  # Add 1 for the space

        if word == "<li>" or word == "<br>":
            current_length = 0

        if "<code>" in word:
            is_inside_code = True
        if "</code>" in word:
            is_inside_code = False
    return ''.join(new_text).strip()


def replace_code_tags(text):
    """
    Replace odd instances of ` with <code> and even instances of ` with </code>
    """
    parts = text.split('`')
    for i in range(1, len(parts), 2):
        parts[i] = '<code>' + parts[i] + '</code>'
    return ''.join(parts)