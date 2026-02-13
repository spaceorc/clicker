"""Factory for creating and caching LLM callers based on provider and model."""

import os

from .anthropic_vertex import AnthropicVertexLlmCaller
from .base import LlmCaller, LlmProvider
from .google_vertex import GoogleVertexLlmCaller
from .openai import OpenAILlmCaller

DEFAULT_LLM_MODEL = "openai/gpt-4o-mini"

# Cache for LLM callers by (provider, model) key
_llm_caller_cache: dict[tuple[str, str], LlmCaller] = {}


def parse_model_spec(model_spec: str) -> tuple[LlmProvider, str]:
    """Parse model specification in format 'provider/model'.

    Args:
        model_spec: Model specification like 'openai/gpt-4o-mini' or 'anthropic_vertex/claude-haiku-4-5@20251001'

    Returns:
        Tuple of (provider, model)

    Raises:
        ValueError: If format is invalid or provider is unsupported
    """
    if "/" not in model_spec:
        raise ValueError(
            f"Invalid model spec format: '{model_spec}'. Expected format: 'provider/model' "
            f"(e.g., 'openai/gpt-4o-mini' or 'anthropic_vertex/claude-haiku-4-5@20251001')"
        )

    provider, model = model_spec.split("/", 1)

    if provider not in ("anthropic_vertex", "openai", "google_vertex"):
        raise ValueError(
            f"Unsupported provider: '{provider}'. Supported providers: 'anthropic_vertex', 'openai', 'google_vertex'"
        )

    return provider, model  # type: ignore


def get_llm_caller(provider: LlmProvider, model: str) -> LlmCaller:
    """Get or create an LLM caller for the specified provider and model.

    Callers are cached by (provider, model) key to avoid recreating clients.

    Args:
        provider: LLM provider name ('anthropic_vertex', 'openai', or 'google_vertex')
        model: Model identifier

    Returns:
        LlmCaller instance configured for the provider and model

    Raises:
        ValueError: If provider is unsupported
    """
    cache_key = (provider, model)

    if cache_key not in _llm_caller_cache:
        if provider == "anthropic_vertex":
            caller = AnthropicVertexLlmCaller(model)
        elif provider == "openai":
            caller = OpenAILlmCaller(model)
        elif provider == "google_vertex":
            caller = GoogleVertexLlmCaller(model)
        else:
            raise ValueError(f"Unsupported provider: {provider}")

        _llm_caller_cache[cache_key] = caller

    return _llm_caller_cache[cache_key]


def get_llm_caller_from_env(
    env_var_name: str,
    fallback_env_var: str = "DEFAULT_LLM_MODEL",
    default_model_spec: str = DEFAULT_LLM_MODEL,
) -> LlmCaller:
    """Get LLM caller from environment variable with fallback chain.

    Args:
        env_var_name: Primary environment variable name to check
        fallback_env_var: Fallback environment variable name (default: DEFAULT_LLM_MODEL)
        default_model_spec: Default model spec if no env vars are set (default: openai/gpt-4o-mini)

    Returns:
        LlmCaller instance

    Examples:
        # Try SYNTHETIC_CUSTOMER_LLM_MODEL, then DEFAULT_LLM_MODEL, then default
        get_llm_caller_from_env("SYNTHETIC_CUSTOMER_LLM_MODEL")

        # Try EVALUATOR_LLM_MODEL, then DEFAULT_LLM_MODEL, then default
        get_llm_caller_from_env("EVALUATOR_LLM_MODEL")
    """
    model_spec = os.environ.get(env_var_name) or os.environ.get(fallback_env_var) or default_model_spec

    provider, model = parse_model_spec(model_spec)
    return get_llm_caller(provider, model)
