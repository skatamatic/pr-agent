import asyncio
import copy
import re
import traceback
from functools import partial
from typing import List, Tuple

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
        update_operation_ai_metrics, extract_repository_from_url
    )
    DASHBOARD_AVAILABLE = True
except ImportError:
    DASHBOARD_AVAILABLE = False


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
        self.ai_handler = ai_handler()
        self.ai_handler.main_pr_language = self.main_pr_language

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
        if DASHBOARD_AVAILABLE:
            try:
                repository = extract_repository_from_url(pr_url)
            except Exception as e:
                get_logger().debug(f"Failed to extract repository from URL: {e}")

        # Create operation context for dashboard tracking (error resilient)
        if DASHBOARD_AVAILABLE:
            try:
                with operation_context(
                    operation_type=OperationType.GENERATING_DESCRIPTION,
                    command="describe",
                    repo=repository,
                    pr_url=pr_url,
                    installation_id=getattr(self.git_provider, 'installation_id', None),
                    sender=getattr(self.git_provider, 'sender', None)
                ) as operation_id:
                    get_logger().info(f"PR description operation started with ID: {operation_id}")
                    return await self._run_with_tracking(operation_id)
            except Exception as e:
                get_logger().warning(f"Dashboard operation tracking failed, continuing without tracking: {e}")
                # Fall through to execute without tracking
        
        # Execute without operation tracking (fallback or dashboard disabled)
        get_logger().info("Executing PR description without dashboard tracking")
        return await self._run_without_tracking()

    async def _run_with_tracking(self, operation_id: str):
        """Run PR description with dashboard operation tracking"""
        try:
            # Update operation status to processing
            update_operation_status("processing")
            
            # Execute the main description logic
            result = await self._execute_description_logic()
            
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
        return await self._execute_description_logic()

    async def _execute_description_logic(self):
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

            await retry_with_fallback_models(self._prepare_prediction, ModelType.WEAK)

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

            if get_settings().config.publish_output:

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
                get_logger().info('PR description, but not published since publish_output is False.')
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
                    
                    # Estimate developer time saved for description operation using AI analysis
                    try:
                        estimated_hours = await self._estimate_description_dev_hours_saved_ai(
                            model=model,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            files_count=len(self.git_provider.get_files()) if self.git_provider.get_files() else 0,
                            prompt_type=prompt,
                            diff=self.patches_diff,
                            description_content=response
                        )
                    except Exception as e:
                        get_logger().debug(f"AI time estimation failed, using fallback: {e}")
                        estimated_hours = self._estimate_description_dev_hours_saved(
                            model=model,
                            input_tokens=input_tokens,
                            output_tokens=output_tokens,
                            files_count=len(self.git_provider.get_files()) if self.git_provider.get_files() else 0,
                            prompt_type=prompt
                        )
                    
                    # Update AI metrics
                    update_operation_ai_metrics(
                        model_used=model,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        estimated_dev_hours_saved=estimated_hours
                    )
                    
                    get_logger().info(f"AI metrics updated - Input: {input_tokens}, Output: {output_tokens}, "
                                    f"Calls: {totals['call_count']}, Failed: {totals['failed_calls']}, Prompt: {prompt}")
                    
                except Exception as e:
                    get_logger().debug(f"Failed to track AI metrics for description: {e}")
            
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
            
            # Cap at reasonable bounds
            return max(0.08, min(2.0, estimated_hours))
            
        except Exception as e:
            get_logger().debug(f"Failed to estimate description dev hours: {e}")
            return 0.25  # Default fallback

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