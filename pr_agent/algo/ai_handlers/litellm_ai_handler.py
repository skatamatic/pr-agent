import os
from typing import Optional

import litellm
import openai
import requests
from litellm import acompletion
from tenacity import retry, retry_if_exception_type, retry_if_not_exception_type, stop_after_attempt

from pr_agent.algo.model_registry import (
    REASONING_STYLE_ANTHROPIC_ADAPTIVE,
    REASONING_STYLE_ANTHROPIC_BUDGET,
    model_is_user_message_only,
    model_reasoning_style,
    model_supports_claude_extended_thinking,
    model_supports_reasoning_effort,
    model_supports_temperature,
)
from pr_agent.algo.ai_handlers.base_ai_handler import BaseAiHandler
from pr_agent.algo.utils import ReasoningEffort, get_version
from pr_agent.config_loader import get_settings
from pr_agent.log import get_logger
import json

OPENAI_RETRIES = 5


class LiteLLMAIHandler(BaseAiHandler):
    """
    This class handles interactions with the OpenAI API for chat completions.
    It initializes the API key and other settings from a configuration file,
    and provides a method for performing chat completions using the OpenAI ChatCompletion API.
    """

    def __init__(self, use_injected_credentials: bool = False):
        """
        Initializes the OpenAI API key and other settings from a configuration file.
        When use_injected_credentials is True, skip loading API keys from settings so
        temporary credentials (e.g. dashboard benchmark overrides) are preserved.
        """
        self.azure = False
        self.api_base = None
        self.repetition_penalty = None

        if not use_injected_credentials:
            self._apply_settings_credentials()
        else:
            self._sync_runtime_from_litellm_globals()

        self._apply_settings_runtime_config()

    def _apply_settings_credentials(self):
        if get_settings().get("OPENAI.KEY", None):
            openai.api_key = get_settings().openai.key
            litellm.openai_key = get_settings().openai.key
        elif 'OPENAI_API_KEY' not in os.environ:
            litellm.api_key = "dummy_key"
        if get_settings().get("OPENAI.ORG", None):
            litellm.organization = get_settings().openai.org
        if get_settings().get("OPENAI.API_TYPE", None):
            if get_settings().openai.api_type == "azure":
                self.azure = True
                litellm.azure_key = get_settings().openai.key
        if get_settings().get("OPENAI.API_VERSION", None):
            litellm.api_version = get_settings().openai.api_version
        if get_settings().get("OPENAI.API_BASE", None):
            litellm.api_base = get_settings().openai.api_base
            self.api_base = get_settings().openai.api_base
        if get_settings().get("ANTHROPIC.KEY", None):
            litellm.anthropic_key = get_settings().anthropic.key
        if get_settings().get("COHERE.KEY", None):
            litellm.cohere_key = get_settings().cohere.key
        if get_settings().get("GROQ.KEY", None):
            litellm.api_key = get_settings().groq.key
        if get_settings().get("REPLICATE.KEY", None):
            litellm.replicate_key = get_settings().replicate.key
        if get_settings().get("XAI.KEY", None):
            litellm.api_key = get_settings().xai.key
        if get_settings().get("HUGGINGFACE.KEY", None):
            litellm.huggingface_key = get_settings().huggingface.key
        if get_settings().get("HUGGINGFACE.API_BASE", None) and 'huggingface' in get_settings().config.model:
            litellm.api_base = get_settings().huggingface.api_base
            self.api_base = get_settings().huggingface.api_base
        if get_settings().get("OLLAMA.API_BASE", None):
            litellm.api_base = get_settings().ollama.api_base
            self.api_base = get_settings().ollama.api_base
        if get_settings().get("GOOGLE_AI_STUDIO.GEMINI_API_KEY", None):
            os.environ["GEMINI_API_KEY"] = get_settings().google_ai_studio.gemini_api_key
        if get_settings().get("DEEPSEEK.KEY", None):
            os.environ['DEEPSEEK_API_KEY'] = get_settings().get("DEEPSEEK.KEY")
        if get_settings().get("DEEPINFRA.KEY", None):
            os.environ['DEEPINFRA_API_KEY'] = get_settings().get("DEEPINFRA.KEY")
        if get_settings().get("MISTRAL.KEY", None):
            os.environ["MISTRAL_API_KEY"] = get_settings().get("MISTRAL.KEY")
        if get_settings().get("CODESTRAL.KEY", None):
            os.environ["CODESTRAL_API_KEY"] = get_settings().get("CODESTRAL.KEY")
        if get_settings().get("AZURE_AD.CLIENT_ID", None):
            self.azure = True
            access_token = self._get_azure_ad_token()
            litellm.api_key = access_token
            openai.api_key = access_token
            self.api_base = get_settings().azure_ad.api_base
            litellm.api_base = self.api_base
            openai.api_base = self.api_base
        if get_settings().get("OPENROUTER.KEY", None):
            openrouter_api_key = get_settings().get("OPENROUTER.KEY", None)
            os.environ["OPENROUTER_API_KEY"] = openrouter_api_key
            litellm.api_key = openrouter_api_key
            openai.api_key = openrouter_api_key
            openrouter_api_base = get_settings().get("OPENROUTER.API_BASE", "https://openrouter.ai/api/v1")
            os.environ["OPENROUTER_API_BASE"] = openrouter_api_base
            self.api_base = openrouter_api_base
            litellm.api_base = openrouter_api_base

    def _sync_runtime_from_litellm_globals(self):
        """Read azure/base routing from litellm globals set by temporary credentials."""
        self.azure = bool(getattr(litellm, "azure_key", None))
        self.api_base = getattr(litellm, "api_base", None)

    def _apply_settings_runtime_config(self):
        if get_settings().get("aws.AWS_ACCESS_KEY_ID"):
            assert get_settings().aws.AWS_SECRET_ACCESS_KEY and get_settings().aws.AWS_REGION_NAME, "AWS credentials are incomplete"
            os.environ["AWS_ACCESS_KEY_ID"] = get_settings().aws.AWS_ACCESS_KEY_ID
            os.environ["AWS_SECRET_ACCESS_KEY"] = get_settings().aws.AWS_SECRET_ACCESS_KEY
            os.environ["AWS_REGION_NAME"] = get_settings().aws.AWS_REGION_NAME
        if get_settings().get("LITELLM.DROP_PARAMS", None):
            litellm.drop_params = get_settings().litellm.drop_params
        if get_settings().get("LITELLM.SUCCESS_CALLBACK", None):
            litellm.success_callback = get_settings().litellm.success_callback
        if get_settings().get("LITELLM.FAILURE_CALLBACK", None):
            litellm.failure_callback = get_settings().litellm.failure_callback
        if get_settings().get("LITELLM.SERVICE_CALLBACK", None):
            litellm.service_callback = get_settings().litellm.service_callback
        if get_settings().get("HUGGINGFACE.REPETITION_PENALTY", None):
            self.repetition_penalty = float(get_settings().huggingface.repetition_penalty)
        if get_settings().get("VERTEXAI.VERTEX_PROJECT", None):
            litellm.vertex_project = get_settings().vertexai.vertex_project
            litellm.vertex_location = get_settings().get(
                "VERTEXAI.VERTEX_LOCATION", None
            )

    def _get_azure_ad_token(self):
        """
        Generates an access token using Azure AD credentials from settings.
        Returns:
            str: The access token
        """
        from azure.identity import ClientSecretCredential
        try:
            credential = ClientSecretCredential(
                tenant_id=get_settings().azure_ad.tenant_id,
                client_id=get_settings().azure_ad.client_id,
                client_secret=get_settings().azure_ad.client_secret
            )
            # Get token for Azure OpenAI service
            token = credential.get_token("https://cognitiveservices.azure.com/.default")
            return token.token
        except Exception as e:
            get_logger().error(f"Failed to get Azure AD token: {e}")
            raise

    def prepare_logs(self, response, system, user, resp, finish_reason):
        if hasattr(response, "model_dump") and callable(response.model_dump):
            response_log = response.model_dump()
        elif hasattr(response, "dict") and callable(response.dict):
            response_log = response.dict().copy()
        elif isinstance(response, dict):
            response_log = dict(response)
        else:
            response_log = {"response": str(response)}
        response_log['system'] = system
        response_log['user'] = user
        response_log['output'] = resp
        response_log['finish_reason'] = finish_reason
        if hasattr(self, 'main_pr_language'):
            response_log['main_pr_language'] = self.main_pr_language
        else:
            response_log['main_pr_language'] = 'unknown'
        return response_log

    def _configure_claude_extended_thinking(self, model: str, kwargs: dict) -> dict:
        """
        Configure Claude extended thinking parameters if applicable.

        Args:
            model (str): The AI model being used
            kwargs (dict): The keyword arguments for the model call

        Returns:
            dict: Updated kwargs with extended thinking configuration
        """
        extended_thinking_budget_tokens = get_settings().config.get("extended_thinking_budget_tokens", 2048)
        extended_thinking_max_output_tokens = get_settings().config.get("extended_thinking_max_output_tokens", 4096)

        # Validate extended thinking parameters
        if not isinstance(extended_thinking_budget_tokens, int) or extended_thinking_budget_tokens <= 0:
            raise ValueError(f"extended_thinking_budget_tokens must be a positive integer, got {extended_thinking_budget_tokens}")
        if not isinstance(extended_thinking_max_output_tokens, int) or extended_thinking_max_output_tokens <= 0:
            raise ValueError(f"extended_thinking_max_output_tokens must be a positive integer, got {extended_thinking_max_output_tokens}")
        if extended_thinking_max_output_tokens < extended_thinking_budget_tokens:
            raise ValueError(f"extended_thinking_max_output_tokens ({extended_thinking_max_output_tokens}) must be greater than or equal to extended_thinking_budget_tokens ({extended_thinking_budget_tokens})")

        # If reasoning-level mapping already configured adaptive thinking for this model,
        # don't overwrite it with the enabled/budget shape (which adaptive models reject).
        if isinstance(kwargs.get("thinking"), dict) and kwargs["thinking"].get("type") == "adaptive":
            return kwargs

        kwargs["thinking"] = {
            "type": "enabled",
            "budget_tokens": extended_thinking_budget_tokens
        }
        if get_settings().config.get("verbosity_level", 0) >= 2:
            get_logger().debug(f"Adding max output tokens {extended_thinking_max_output_tokens} to model {model}, extended thinking budget tokens: {extended_thinking_budget_tokens}")
        kwargs["max_tokens"] = extended_thinking_max_output_tokens

        # temperature may only be set to 1 when thinking is enabled
        if get_settings().config.get("verbosity_level", 0) >= 2:
            get_logger().debug("Temperature may only be set to 1 when thinking is enabled with claude models.")
        kwargs["temperature"] = 1

        return kwargs

    # Approximate thinking budgets (in tokens) for the older Anthropic "enabled" thinking API.
    _ANTHROPIC_BUDGET_BY_EFFORT = {"low": 2048, "medium": 4096, "high": 8192}

    def _apply_reasoning_level(self, model: str, model_for_check: str, level: str, kwargs: dict) -> dict:
        """Express the desired reasoning level using the model's native mechanism.

        - OpenAI reasoning models: the `reasoning_effort` parameter.
        - Anthropic adaptive-thinking models (e.g. claude-opus-4-8): `thinking.type=adaptive`
          plus `output_config.effort`. These models also deprecate `temperature`.
        - Anthropic budget-thinking models (e.g. claude-3-7-sonnet): `thinking.type=enabled`
          with a token budget; `temperature` must be 1 and `max_tokens` must exceed the budget.

        If a model rejects the chosen shape at request time, `_acompletion_with_param_fallback`
        negotiates the correct one, so this only needs to pick a sensible default.
        """
        style = model_reasoning_style(model_for_check)

        if style == REASONING_STYLE_ANTHROPIC_ADAPTIVE:
            kwargs["thinking"] = {"type": "adaptive"}
            kwargs["output_config"] = {"effort": level}
            # Adaptive-thinking models reject a custom temperature.
            kwargs.pop("temperature", None)
            get_logger().info(f"Using Anthropic adaptive thinking (effort={level}) for model {model}.")
        elif style == REASONING_STYLE_ANTHROPIC_BUDGET:
            budget = self._ANTHROPIC_BUDGET_BY_EFFORT.get(level, 4096)
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget}
            # When thinking is enabled, max_tokens must exceed the budget and temperature must be 1.
            existing_max = kwargs.get("max_tokens") or 0
            kwargs["max_tokens"] = max(existing_max, budget + 4096)
            kwargs["temperature"] = 1
            get_logger().info(
                f"Using Anthropic extended thinking (budget_tokens={budget}, effort={level}) for model {model}."
            )
        else:
            kwargs["reasoning_effort"] = level
            get_logger().info(f"Adding reasoning_effort with value {level} to model {model}.")

        return kwargs

    def add_litellm_callbacks(selfs, kwargs) -> dict:
        captured_extra = []

        def capture_logs(message):
            # Parsing the log message and context
            record = message.record
            log_entry = {}
            if record.get('extra', None).get('command', None) is not None:
                log_entry.update({"command": record['extra']["command"]})
            if record.get('extra', {}).get('pr_url', None) is not None:
                log_entry.update({"pr_url": record['extra']["pr_url"]})

            # Append the log entry to the captured_logs list
            captured_extra.append(log_entry)

        # Adding the custom sink to Loguru
        handler_id = get_logger().add(capture_logs)
        get_logger().debug("Capturing logs for litellm callbacks")
        get_logger().remove(handler_id)

        context = captured_extra[0] if len(captured_extra) > 0 else None

        command = context.get("command", "unknown")
        pr_url = context.get("pr_url", "unknown")
        git_provider = get_settings().config.git_provider

        metadata = dict()
        callbacks = litellm.success_callback + litellm.failure_callback + litellm.service_callback
        if "langfuse" in callbacks:
            metadata.update({
                "trace_name": command,
                "tags": [git_provider, command, f'version:{get_version()}'],
                "trace_metadata": {
                    "command": command,
                    "pr_url": pr_url,
                },
            })
        if "langsmith" in callbacks:
            metadata.update({
                "run_name": command,
                "tags": [git_provider, command, f'version:{get_version()}'],
                "extra": {
                    "metadata": {
                        "command": command,
                        "pr_url": pr_url,
                    }
                },
            })

        # Adding the captured logs to the kwargs
        kwargs["metadata"] = metadata

        return kwargs

    @property
    def deployment_id(self):
        """
        Returns the deployment ID for the OpenAI API.
        """
        return get_settings().get("OPENAI.DEPLOYMENT_ID", None)

    # Optional tuning parameters that are safe to drop and retry without if a provider
    # rejects them. Some models (e.g. newer Anthropic reasoning models) advertise these
    # via LiteLLM metadata but reject them at request time.
    _DROPPABLE_PARAMS = ("temperature", "reasoning_effort", "top_p", "thinking", "seed")

    def _negotiate_thinking_params(self, kwargs: dict, msg: str, negotiated: set) -> Optional[str]:
        """Repair Anthropic `thinking` parameters based on the provider's rejection message.

        Different Claude models accept different thinking shapes (adaptive vs enabled+budget).
        Rather than hardcode which model wants which, we react to the API's guidance and switch
        shapes. Each repair runs at most once (tracked in `negotiated`) to guarantee termination.
        Returns a human-readable description of the repair, or None if nothing applied.
        """
        thinking = kwargs.get("thinking")

        # Model wants adaptive thinking instead of the enabled/budget shape we sent.
        if "to_adaptive" not in negotiated and (
            "thinking.type.adaptive" in msg or ("adaptive" in msg and "enabled" in msg)
        ):
            negotiated.add("to_adaptive")
            effort = (kwargs.get("output_config") or {}).get("effort") or "high"
            kwargs["thinking"] = {"type": "adaptive"}
            kwargs["output_config"] = {"effort": effort}
            kwargs.pop("temperature", None)  # adaptive-thinking models deprecate temperature
            return "switched thinking to adaptive"

        # Model does not support adaptive thinking; fall back to enabled+budget.
        if "to_budget" not in negotiated and "adaptive thinking is not supported" in msg:
            negotiated.add("to_budget")
            budget = self._ANTHROPIC_BUDGET_BY_EFFORT.get(
                (kwargs.get("output_config") or {}).get("effort"), 4096
            )
            kwargs["thinking"] = {"type": "enabled", "budget_tokens": budget}
            kwargs.pop("output_config", None)
            kwargs["max_tokens"] = max(kwargs.get("max_tokens") or 0, budget + 4096)
            kwargs["temperature"] = 1
            return "switched thinking to enabled budget"

        # max_tokens must exceed the thinking budget.
        if "bump_max" not in negotiated and "budget_tokens" in msg and "max_tokens" in msg:
            negotiated.add("bump_max")
            budget = 4096
            if isinstance(thinking, dict) and isinstance(thinking.get("budget_tokens"), int):
                budget = thinking["budget_tokens"]
            kwargs["max_tokens"] = budget + 4096
            return "increased max_tokens above thinking budget"

        return None

    async def _acompletion_with_param_fallback(self, kwargs: dict):
        """Call litellm.acompletion, adapting the request when a provider rejects parameters.

        Two layers of resilience:
        1. Negotiate Anthropic `thinking` shape (adaptive <-> enabled/budget, max_tokens) based
           on the rejection message, so reasoning still happens on the right API.
        2. Otherwise drop the specific optional parameter the provider complained about and
           retry, instead of failing the whole operation.
        """
        attempt_kwargs = dict(kwargs)
        dropped = []
        negotiated: set = set()
        while True:
            try:
                return await acompletion(**attempt_kwargs)
            except (openai.BadRequestError, litellm.BadRequestError) as e:
                msg = str(e).lower()

                repair = self._negotiate_thinking_params(attempt_kwargs, msg, negotiated)
                if repair:
                    get_logger().warning(
                        f"Adjusting request for model {attempt_kwargs.get('model')}: {repair}."
                    )
                    continue

                to_drop = next(
                    (p for p in self._DROPPABLE_PARAMS if p in attempt_kwargs and p in msg),
                    None,
                )
                # reasoning_effort is translated to Anthropic "thinking"; the rejection
                # message references thinking/reasoning rather than the param we sent.
                if to_drop is None and "reasoning_effort" in attempt_kwargs and (
                    "thinking" in msg or "reasoning" in msg
                ):
                    to_drop = "reasoning_effort"
                if to_drop is None:
                    raise
                attempt_kwargs.pop(to_drop, None)
                if to_drop == "thinking":
                    attempt_kwargs.pop("output_config", None)
                dropped.append(to_drop)
                get_logger().warning(
                    f"Provider rejected parameter '{to_drop}' for model "
                    f"{attempt_kwargs.get('model')}; retrying without it (dropped so far: {dropped})."
                )

    @retry(
        retry=retry_if_exception_type(openai.APIError)
        & retry_if_not_exception_type((openai.RateLimitError, openai.BadRequestError)),
        stop=stop_after_attempt(OPENAI_RETRIES),
    )
    async def chat_completion(self, model: str, system: str, user: str, temperature: float = 0.2, img_path: str = None):
        try:
            resp, finish_reason = None, None
            deployment_id = self.deployment_id
            if self.azure and not model.startswith("azure/"):
                model = 'azure/' + model
            model_for_check = model.removeprefix('azure/')
            if 'claude' in model and not system:
                system = "No system prompt provided"
                get_logger().warning(
                    "Empty system prompt for claude model. Adding a newline character to prevent OpenAI API error.")
            messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]

            if img_path:
                try:
                    # check if the image link is alive
                    r = requests.head(img_path, allow_redirects=True)
                    if r.status_code == 404:
                        error_msg = f"The image link is not [alive](img_path).\nPlease repost the original image as a comment, and send the question again with 'quote reply' (see [instructions](https://pr-agent-docs.codium.ai/tools/ask/#ask-on-images-using-the-pr-code-as-context))."
                        get_logger().error(error_msg)
                        return f"{error_msg}", "error"
                except Exception as e:
                    get_logger().error(f"Error fetching image: {img_path}", e)
                    return f"Error fetching image: {img_path}", "error"
                messages[1]["content"] = [{"type": "text", "text": messages[1]["content"]},
                                          {"type": "image_url", "image_url": {"url": img_path}}]

            custom_reasoning_model = bool(get_settings().config.get("custom_reasoning_model", False))

            # Currently, some models do not support a separate system and user prompts
            if model_is_user_message_only(model_for_check) or custom_reasoning_model:
                user = f"{system}\n\n\n{user}"
                system = ""
                get_logger().info(f"Using model {model}, combining system and user prompts")
                messages = [{"role": "user", "content": user}]
                kwargs = {
                    "model": model,
                    "deployment_id": deployment_id,
                    "messages": messages,
                    "timeout": get_settings().config.ai_timeout,
                    "api_base": self.api_base,
                }
            else:
                kwargs = {
                    "model": model,
                    "deployment_id": deployment_id,
                    "messages": messages,
                    "timeout": get_settings().config.ai_timeout,
                    "api_base": self.api_base,
                }

            # Add temperature only if model supports it
            if model_supports_temperature(model_for_check) and not custom_reasoning_model:
                # get_logger().info(f"Adding temperature with value {temperature} to model {model}.")
                kwargs["temperature"] = temperature

            # Add a reasoning level if the model supports it. The level is expressed using
            # the provider-native mechanism (OpenAI `reasoning_effort` vs Anthropic `thinking`).
            if model_supports_reasoning_effort(model_for_check):
                supported_reasoning_efforts = [ReasoningEffort.HIGH.value, ReasoningEffort.MEDIUM.value, ReasoningEffort.LOW.value]
                reasoning_effort = get_settings().config.get("reasoning_effort", ReasoningEffort.MEDIUM.value)
                if reasoning_effort not in supported_reasoning_efforts:
                    reasoning_effort = ReasoningEffort.MEDIUM.value
                kwargs = self._apply_reasoning_level(model, model_for_check, reasoning_effort, kwargs)

            # https://docs.anthropic.com/en/docs/build-with-claude/extended-thinking
            if model_supports_claude_extended_thinking(model_for_check) and get_settings().config.get("enable_claude_extended_thinking", False):
                kwargs = self._configure_claude_extended_thinking(model, kwargs)

            if get_settings().get("LITELLM.ENABLE_CALLBACKS", False):
                kwargs = self.add_litellm_callbacks(kwargs)

            seed = get_settings().config.get("seed", -1)
            if temperature > 0 and seed >= 0:
                raise ValueError(f"Seed ({seed}) is not supported with temperature ({temperature}) > 0")
            elif seed >= 0:
                get_logger().info(f"Using fixed seed of {seed}")
                kwargs["seed"] = seed

            if self.repetition_penalty:
                kwargs["repetition_penalty"] = self.repetition_penalty

            #Added support for extra_headers while using litellm to call underlying model, via a api management gateway, would allow for passing custom headers for security and authorization
            if get_settings().get("LITELLM.EXTRA_HEADERS", None):
                try:
                    litellm_extra_headers = json.loads(get_settings().litellm.extra_headers)
                    if not isinstance(litellm_extra_headers, dict):
                        raise ValueError("LITELLM.EXTRA_HEADERS must be a JSON object")
                except json.JSONDecodeError as e:
                    raise ValueError(f"LITELLM.EXTRA_HEADERS contains invalid JSON: {str(e)}")
                kwargs["extra_headers"] = litellm_extra_headers

            # Enhanced AI interaction logging - always log prompts at INFO level for debugging
            get_logger().info(f"[AI] - AI Model Call: {model}", artifacts={
                "model": model,
                "temperature": kwargs.get("temperature", "not_set"),
                "system_prompt_chars": len(system),
                "user_prompt_chars": len(user),
                "combined_prompt": model_is_user_message_only(model_for_check) or custom_reasoning_model
            })
            
            # Log full prompts for debugging purposes
            get_logger().info(f"[AI] - System Prompt ({len(system)} chars)", artifacts={"system_prompt": system})
            get_logger().info(f"[AI] - User Prompt ({len(user)} chars)", artifacts={"user_prompt": user})

            response = await self._acompletion_with_param_fallback(kwargs)
        except openai.RateLimitError as e:
            get_logger().error(f"[AI] - Rate limit error during LLM inference: {e}")
            raise
        except openai.APIError as e:
            get_logger().warning(f"[AI] - Error during LLM inference: {e}")
            raise
        except Exception as e:
            get_logger().warning(f"[AI] - Unknown error during LLM inference: {e}")
            raise
        choices = response.get("choices") if isinstance(response, dict) else getattr(response, "choices", None)
        if response is None or not choices:
            raise RuntimeError("LLM returned empty response")
        first_choice = choices[0]
        if isinstance(first_choice, dict):
            resp = first_choice['message']['content']
            finish_reason = first_choice["finish_reason"]
        else:
            resp = first_choice.message.content
            finish_reason = first_choice.finish_reason

        token_usage = None
        if hasattr(response, 'usage') and response.usage:
            token_usage = {
                'input_tokens': getattr(response.usage, 'prompt_tokens', 0),
                'output_tokens': getattr(response.usage, 'completion_tokens', 0)
            }
        elif isinstance(response, dict) and 'usage' in response:
            usage = response['usage']
            token_usage = {
                'input_tokens': usage.get('prompt_tokens', 0),
                'output_tokens': usage.get('completion_tokens', 0)
            }

        get_logger().info(f"[AI] - AI Response ({len(resp)} chars)", artifacts={
            "ai_response": resp,
            "finish_reason": finish_reason,
            "response_chars": len(resp)
        })

        if token_usage:
            get_logger().info(f"[AI] - Token Usage", artifacts={
                "model": model,
                "input_tokens": token_usage.get('input_tokens', 0),
                "output_tokens": token_usage.get('output_tokens', 0),
                "total_tokens": token_usage.get('input_tokens', 0) + token_usage.get('output_tokens', 0)
            })
        else:
            get_logger().warning(f"[AI] - No token usage information available from AI model: {model}")

        response_log = self.prepare_logs(response, system, user, resp, finish_reason)
        get_logger().debug("[AI] - Full AI Response Structure", artifact=response_log)

        return resp, finish_reason, token_usage
