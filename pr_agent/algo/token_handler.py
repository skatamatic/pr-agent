from threading import Lock
from math import ceil
import re
import copy
import math
import tiktoken
from typing import Optional, Dict

from jinja2 import Environment, StrictUndefined
from tiktoken import encoding_for_model, get_encoding

from pr_agent.config_loader import get_settings
from pr_agent.log import get_logger

from pr_agent.algo import MAX_TOKENS


class TokenUsageTracker:
    """
    Tracks cumulative token usage across multiple AI calls for accurate cost calculation.
    Handles retries, failures, and multiple prompts within a single operation.
    """
    
    def __init__(self):
        self.total_input_tokens = 0
        self.total_output_tokens = 0
        self.call_count = 0
        self.failed_calls = 0
        
    def add_usage(self, token_usage: Optional[Dict[str, int]], call_failed: bool = False):
        """
        Add token usage from an AI call.
        
        Args:
            token_usage: Dict with 'input_tokens' and 'output_tokens' keys, or None
            call_failed: Whether this AI call failed (still counts for cost)
        """
        if token_usage:
            self.total_input_tokens += token_usage.get('input_tokens', 0)
            self.total_output_tokens += token_usage.get('output_tokens', 0)
            
        self.call_count += 1
        if call_failed:
            self.failed_calls += 1
            
        get_logger().debug(f"Token usage updated: input={self.total_input_tokens}, "
                          f"output={self.total_output_tokens}, calls={self.call_count}, "
                          f"failed={self.failed_calls}")
    
    def get_totals(self) -> Dict[str, int]:
        """Get total accumulated token usage."""
        return {
            'input_tokens': self.total_input_tokens,
            'output_tokens': self.total_output_tokens,
            'total_tokens': self.total_input_tokens + self.total_output_tokens,
            'call_count': self.call_count,
            'failed_calls': self.failed_calls
        }
    
    def has_usage(self) -> bool:
        """Check if any token usage has been recorded."""
        return self.total_input_tokens > 0 or self.total_output_tokens > 0


class ModelTypeValidator:
    @staticmethod
    def is_openai_model(model_name: str) -> bool:
        openai_patterns = [
            r'^gpt-',
            r'^o\d+',
            r'^o\d+-',
            r'^text-',
            r'^davinci',
            r'^curie',
            r'^babbage',
            r'^ada',
        ]
        return any(re.match(pattern, model_name.lower()) for pattern in openai_patterns)
    
    @staticmethod
    def is_anthropic_model(model_name: str) -> bool:
        anthropic_patterns = [
            r'^claude-',
            r'claude',
        ]
        return any(re.search(pattern, model_name.lower()) for pattern in anthropic_patterns)


class TokenEncoder:
    _encoder_instance = None
    _model = None
    _lock = Lock()  # Create a lock object

    @classmethod
    def get_token_encoder(cls):
        model = get_settings().config.model
        if cls._encoder_instance is None or model != cls._model:  # Check without acquiring the lock for performance
            with cls._lock:  # Lock acquisition to ensure thread safety
                if cls._encoder_instance is None or model != cls._model:
                    cls._model = model
                    try:
                        cls._encoder_instance = encoding_for_model(cls._model) if "gpt" in cls._model else get_encoding(
                            "o200k_base")
                    except:
                        cls._encoder_instance = get_encoding("o200k_base")
        return cls._encoder_instance


class TokenHandler:
    """
    A class for handling tokens in the context of a pull request.

    Attributes:
    - encoder: An object of the encoding_for_model class from the tiktoken module. Used to encode strings and count the
      number of tokens in them.
    - limit: The maximum number of tokens allowed for the given model, as defined in the MAX_TOKENS dictionary in the
      pr_agent.algo module.
    - prompt_tokens: The number of tokens in the system and user strings, as calculated by the _get_system_user_tokens
      method.
    """

    # Constants
    CLAUDE_MODEL = "claude-3-7-sonnet-20250219"
    CLAUDE_MAX_CONTENT_SIZE = 9_000_000 # Maximum allowed content size (9MB) for Claude API

    def __init__(self, pr=None, vars: dict = {}, system="", user=""):
        """
        Initializes the TokenHandler object.

        Args:
        - pr: The pull request object.
        - vars: A dictionary of variables.
        - system: The system string.
        - user: The user string.
        """
        self.encoder = TokenEncoder.get_token_encoder()
        
        if pr is not None:
            self.prompt_tokens = self._get_system_user_tokens(pr, self.encoder, vars, system, user)

    def _get_system_user_tokens(self, pr, encoder, vars: dict, system, user):
        """
        Calculates the number of tokens in the system and user strings.

        Args:
        - pr: The pull request object.
        - encoder: An object of the encoding_for_model class from the tiktoken module.
        - vars: A dictionary of variables.
        - system: The system string.
        - user: The user string.

        Returns:
        The sum of the number of tokens in the system and user strings.
        """
        try:
            environment = Environment(undefined=StrictUndefined)
            system_prompt = environment.from_string(system).render(vars)
            user_prompt = environment.from_string(user).render(vars)
            system_prompt_tokens = len(encoder.encode(system_prompt))
            user_prompt_tokens = len(encoder.encode(user_prompt))
            return system_prompt_tokens + user_prompt_tokens
        except Exception as e:
            get_logger().error(f"Error in _get_system_user_tokens: {e}")
            return 0

    def _calc_claude_tokens(self, patch: str) -> int:
        try:
            import anthropic
            from pr_agent.algo import MAX_TOKENS
            
            client = anthropic.Anthropic(api_key=get_settings(use_context=False).get('anthropic.key'))
            max_tokens = MAX_TOKENS[get_settings().config.model]

            if len(patch.encode('utf-8')) > self.CLAUDE_MAX_CONTENT_SIZE:
                get_logger().warning(
                    "Content too large for Anthropic token counting API, falling back to local tokenizer"
                )
                return max_tokens

            response = client.messages.count_tokens(
                model=self.CLAUDE_MODEL,
                system="system",
                messages=[{
                    "role": "user",
                    "content": patch
                }],
            )
            return response.input_tokens

        except Exception as e:
            get_logger().error(f"Error in Anthropic token counting: {e}")
            return max_tokens

    def _apply_estimation_factor(self, model_name: str, default_estimate: int) -> int:
        factor = 1 + get_settings().get('config.model_token_count_estimate_factor', 0)
        get_logger().warning(f"{model_name}'s token count cannot be accurately estimated. Using factor of {factor}")
        
        return ceil(factor * default_estimate)

    def _get_token_count_by_model_type(self, patch: str, default_estimate: int) -> int:
        """
        Get token count based on model type.

        Args:
            patch: The text to count tokens for.
            default_estimate: The default token count estimate.

        Returns:
            int: The calculated token count.
        """
        model_name = get_settings().config.model.lower()
        
        if ModelTypeValidator.is_openai_model(model_name) and get_settings(use_context=False).get('openai.key'):
            return default_estimate

        if ModelTypeValidator.is_anthropic_model(model_name) and get_settings(use_context=False).get('anthropic.key'):
            return self._calc_claude_tokens(patch)
        
        return self._apply_estimation_factor(model_name, default_estimate)
    
    def count_tokens(self, patch: str, force_accurate: bool = False) -> int:
        """
        Counts the number of tokens in a given patch string.

        Args:
        - patch: The patch string.
        - force_accurate: If True, uses a more precise calculation method.

        Returns:
        The number of tokens in the patch string.
        """
        encoder_estimate = len(self.encoder.encode(patch, disallowed_special=()))

        # If an estimate is enough (for example, in cases where the maximal allowed tokens is way below the known limits), return it.
        if not force_accurate:
            return encoder_estimate

        return self._get_token_count_by_model_type(patch, encoder_estimate)

    def get_token_count_from_string(self, prompt: str) -> int:
        """
        Get the token count for a string using the tiktoken encoder.
        
        Args:
            prompt: The text to count tokens for.
            
        Returns:
            int: The token count.
        """
        return len(self.encoder.encode(prompt, disallowed_special=()))

    def get_token_count_from_string_legacy(self, prompt: str) -> int:
        """
        Legacy method for token counting using simple split.
        This is kept for backwards compatibility but should be avoided.
        
        Args:
            prompt: The text to count tokens for.
            
        Returns:
            int: The estimated token count.
        """
        get_logger().warning("Using legacy split() token counting - this is inaccurate")
        return len(prompt.split())

    def clip_tokens(self, text: str, max_tokens: int, add_three_dots=True) -> str:
        """
        Clip a text string to a maximum number of tokens.

        Args:
        - text: The text string to clip.
        - max_tokens: The maximum number of tokens allowed.
        - add_three_dots: Whether to add "..." at the end of the clipped text.

        Returns:
        The clipped text string.
        """
        if not text:
            return ""

        tokens = self.encoder.encode(text, disallowed_special=())
        if len(tokens) <= max_tokens:
            return text

        clipped_tokens = tokens[:max_tokens]
        clipped_text = self.encoder.decode(clipped_tokens)

        if add_three_dots and clipped_text != text:
            clipped_text += "..."

        return clipped_text

    def get_max_tokens(self, model: str) -> int:
        """
        Get the maximum number of tokens for a given model.

        Args:
        - model: The model name.

        Returns:
        The maximum number of tokens for the model.
        """
        try:
            max_tokens_model = MAX_TOKENS.get(model, 4096)
            max_tokens_model = min(max_tokens_model, get_settings().config.max_model_tokens)
            custom_model_max_tokens = get_settings().config.custom_model_max_tokens
            if custom_model_max_tokens != -1:
                max_tokens_model = custom_model_max_tokens
            return max_tokens_model
        except Exception as e:
            get_logger().warning(f"Failed to get max tokens for model {model}: {e}")
            return 4096
