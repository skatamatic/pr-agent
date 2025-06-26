import copy
import textwrap
from functools import partial
from typing import Dict

from jinja2 import Environment, StrictUndefined

from pr_agent.algo.ai_handlers.base_ai_handler import BaseAiHandler
from pr_agent.algo.ai_handlers.litellm_ai_handler import LiteLLMAIHandler
from pr_agent.algo.pr_processing import get_pr_diff, retry_with_fallback_models
from pr_agent.algo.token_handler import TokenHandler
from pr_agent.algo.utils import load_yaml
from pr_agent.config_loader import get_settings
from pr_agent.git_providers import get_git_provider
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


class PRAddDocs:
    def __init__(self, pr_url: str, cli_mode=False, args: list = None,
                 ai_handler: partial[BaseAiHandler,] = LiteLLMAIHandler):

        self.git_provider = get_git_provider()(pr_url)
        self.main_language = get_main_pr_language(
            self.git_provider.get_languages(), self.git_provider.get_files()
        )

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
            "extra_instructions": get_settings().pr_add_docs.extra_instructions,
            "commit_messages_str": self.git_provider.get_commit_messages(),
            'docs_for_language': get_docs_for_language(self.main_language,
                                                       get_settings().pr_add_docs.docs_style),
        }
        self.token_handler = TokenHandler(self.git_provider.pr,
                                          self.vars,
                                          get_settings().pr_add_docs_prompt.system,
                                          get_settings().pr_add_docs_prompt.user)

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
                    operation_type=OperationType.ADDING_DOCUMENTATION,
                    command="add_docs",
                    repo=repository,
                    pr_url=pr_url,
                    installation_id=getattr(self.git_provider, 'installation_id', None),
                    sender=getattr(self.git_provider, 'sender', None)
                ) as operation_id:
                    get_logger().info(f"PR add docs operation started with ID: {operation_id}")
                    return await self._run_with_tracking(operation_id)
            except Exception as e:
                get_logger().warning(f"Dashboard operation tracking failed, continuing without tracking: {e}")
                # Fall through to execute without tracking
        
        # Execute without operation tracking (fallback or dashboard disabled)
        get_logger().info("Executing PR add docs without dashboard tracking")
        return await self._run_without_tracking()

    async def _run_with_tracking(self, operation_id: str):
        """Execute PR add docs with dashboard operation tracking"""
        try:
            update_operation_status("processing")
            
            result = await self._execute_add_docs()
            
            # Count documentation suggestions added
            docs_count = 0
            if hasattr(self, 'prediction') and self.prediction:
                data = self._prepare_pr_code_docs()
                if data and 'Code Documentation' in data:
                    docs_count = len(data['Code Documentation'])
            
            update_operation_status("completed", result_data={
                "docs_added": docs_count,
                "language": self.main_language,
                "cli_mode": self.cli_mode
            })
            
            return result
            
        except Exception as e:
            update_operation_status("failed", error_details=str(e))
            raise

    async def _run_without_tracking(self):
        """Execute PR add docs without dashboard tracking (fallback)"""
        return await self._execute_add_docs()

    async def _execute_add_docs(self):
        """Core PR add docs execution logic"""
        try:
            get_logger().info('Generating code Docs for PR...')
            if get_settings().config.publish_output:
                self.git_provider.publish_comment("Generating Documentation...", is_temporary=True)

            get_logger().info('Preparing PR documentation...')
            await retry_with_fallback_models(self._prepare_prediction)
            data = self._prepare_pr_code_docs()
            if (not data) or (not 'Code Documentation' in data):
                get_logger().info('No code documentation found for PR.')
                return

            if get_settings().config.publish_output:
                get_logger().info('Pushing PR documentation...')
                self.git_provider.remove_initial_comment()
                get_logger().info('Pushing inline code documentation...')
                self.push_inline_docs(data)
        except Exception as e:
            get_logger().error(f"Failed to generate code documentation for PR, error: {e}")

    async def _prepare_prediction(self, model: str):
        get_logger().info('Getting PR diff...')

        self.patches_diff = get_pr_diff(self.git_provider,
                                        self.token_handler,
                                        model,
                                        add_line_numbers_to_hunks=True,
                                        disable_extra_lines=False)

        get_logger().info('Getting AI prediction...')
        self.prediction = await self._get_prediction(model)

    async def _get_prediction(self, model: str):
        variables = copy.deepcopy(self.vars)
        variables["diff"] = self.patches_diff  # update diff
        environment = Environment(undefined=StrictUndefined)
        system_prompt = environment.from_string(get_settings().pr_add_docs_prompt.system).render(variables)
        user_prompt = environment.from_string(get_settings().pr_add_docs_prompt.user).render(variables)
        if get_settings().config.verbosity_level >= 2:
            get_logger().info(f"\nSystem prompt:\n{system_prompt}")
            get_logger().info(f"\nUser prompt:\n{user_prompt}")
        
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
                    
                    # Update AI metrics (no time estimation for adding docs)
                    update_operation_ai_metrics(
                        model_used=model,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        estimated_dev_hours_saved=0.15  # Small fixed amount for adding docs
                    )
                    
                    get_logger().info(f"AI metrics updated - Input: {input_tokens}, Output: {output_tokens}, "
                                    f"Calls: {totals['call_count']}, Failed: {totals['failed_calls']}")
                    
                except Exception as e:
                    get_logger().debug(f"Failed to track AI metrics for add docs: {e}")
            
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

    def _prepare_pr_code_docs(self) -> Dict:
        docs = self.prediction.strip()
        data = load_yaml(docs)
        if isinstance(data, list):
            data = {'Code Documentation': data}
        return data

    def push_inline_docs(self, data):
        docs = []

        if not data['Code Documentation']:
            return self.git_provider.publish_comment('No code documentation found to improve this PR.')

        for d in data['Code Documentation']:
            try:
                if get_settings().config.verbosity_level >= 2:
                    get_logger().info(f"add_docs: {d}")
                relevant_file = d['relevant file'].strip()
                relevant_line = int(d['relevant line'])  # absolute position
                documentation = d['documentation']
                doc_placement = d['doc placement'].strip()
                if documentation:
                    new_code_snippet = self.dedent_code(relevant_file, relevant_line, documentation, doc_placement,
                                                        add_original_line=True)

                    body = f"**Suggestion:** Proposed documentation\n```suggestion\n" + new_code_snippet + "\n```"
                    docs.append({'body': body, 'relevant_file': relevant_file,
                                             'relevant_lines_start': relevant_line,
                                             'relevant_lines_end': relevant_line})
            except Exception:
                if get_settings().config.verbosity_level >= 2:
                    get_logger().info(f"Could not parse code docs: {d}")

        is_successful = self.git_provider.publish_code_suggestions(docs)
        if not is_successful:
            get_logger().info("Failed to publish code docs, trying to publish each docs separately")
            for doc_suggestion in docs:
                self.git_provider.publish_code_suggestions([doc_suggestion])

    def dedent_code(self, relevant_file, relevant_lines_start, new_code_snippet, doc_placement='after',
                    add_original_line=False):
        try:  # dedent code snippet
            self.diff_files = self.git_provider.diff_files if self.git_provider.diff_files \
                else self.git_provider.get_diff_files()
            original_initial_line = None
            for file in self.diff_files:
                if file.filename.strip() == relevant_file:
                    original_initial_line = file.head_file.splitlines()[relevant_lines_start - 1]
                    break
            if original_initial_line:
                if doc_placement == 'after':
                    line = file.head_file.splitlines()[relevant_lines_start]
                else:
                    line = original_initial_line
                suggested_initial_line = new_code_snippet.splitlines()[0]
                original_initial_spaces = len(line) - len(line.lstrip())
                suggested_initial_spaces = len(suggested_initial_line) - len(suggested_initial_line.lstrip())
                delta_spaces = original_initial_spaces - suggested_initial_spaces
                if delta_spaces > 0:
                    new_code_snippet = textwrap.indent(new_code_snippet, delta_spaces * " ").rstrip('\n')
                if add_original_line:
                    if doc_placement == 'after':
                        new_code_snippet = original_initial_line + "\n" + new_code_snippet
                    else:
                        new_code_snippet = new_code_snippet.rstrip() + "\n" + original_initial_line
        except Exception as e:
            if get_settings().config.verbosity_level >= 2:
                get_logger().info(f"Could not dedent code snippet for file {relevant_file}, error: {e}")

        return new_code_snippet


def get_docs_for_language(language, style):
    language = language.lower()
    if language == 'java':
        return "Javadocs"
    elif language in ['python', 'lisp', 'clojure']:
        return f"Docstring ({style})"
    elif language in ['javascript', 'typescript']:
        return "JSdocs"
    elif language == 'c++':
        return "Doxygen"
    else:
        return "Docs"
