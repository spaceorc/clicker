"""Hardcoded LLM pricing table and cost estimation.

Last updated: 2026-02-13
Run /update-pricing in Claude Code to refresh
"""

from dataclasses import dataclass

from llm_caller.base import UsageStats


@dataclass(frozen=True, slots=True)
class ModelPricing:
    input: float          # $ per 1M tokens
    output: float         # $ per 1M tokens
    cache_read: float     # $ per 1M tokens
    cache_creation: float  # $ per 1M tokens


# Keys are sorted by length descending so longest-match-first works correctly
# (e.g. "gpt-4o-mini" is checked before "gpt-4o").
PRICING: dict[str, ModelPricing] = {
    # Gemini (Vertex AI) - 22 chars
    "gemini-3-flash-preview": ModelPricing(0.50, 3.00, 0.05, 0),
    # Gemini (Vertex AI) - 21 chars
    "gemini-2.0-flash-lite":  ModelPricing(0.075, 0.30, 0, 0),
    "gemini-2.5-flash-lite":  ModelPricing(0.10, 0.40, 0.01, 0),
    "gemini-3-pro-preview":   ModelPricing(2.00, 12.00, 0.20, 0),
    # Claude (Anthropic Vertex) - 17 chars
    "claude-sonnet-4-5":      ModelPricing(3.0, 15.0, 0.30, 3.75),
    # Mixed - 16 chars
    "claude-haiku-4-5":       ModelPricing(1.0, 5.0, 0.10, 1.25),
    "gemini-2.0-flash":       ModelPricing(0.15, 0.60, 0, 0),
    "gemini-2.5-flash":       ModelPricing(0.30, 2.50, 0.030, 0),
    # Claude (Anthropic Vertex) - 15 chars
    "claude-opus-4-5":        ModelPricing(5.0, 25.0, 0.50, 6.25),
    "claude-opus-4-6":        ModelPricing(5.0, 25.0, 0.50, 6.25),
    "claude-sonnet-4":        ModelPricing(3.0, 15.0, 0.30, 3.75),
    # Gemini (Vertex AI) - 14 chars
    "gemini-2.5-pro":         ModelPricing(1.25, 10.00, 0.125, 0),
    # OpenAI - 11 chars
    "gpt-4o-mini":            ModelPricing(0.15, 0.60, 0, 0),
    # OpenAI - 6 chars
    "gpt-4o":                 ModelPricing(2.50, 10.0, 0, 0),
}


def estimate_cost(model: str, usage: UsageStats) -> float | None:
    """Estimate dollar cost for a given model and usage.

    Uses longest-match-first substring matching against PRICING keys.
    Returns None if no pricing entry matches the model name.
    """
    # Sort keys by length descending for longest-match-first
    for key in sorted(PRICING, key=len, reverse=True):
        if key in model:
            p = PRICING[key]
            return (
                usage.input_tokens * p.input
                + usage.output_tokens * p.output
                + usage.cache_read_tokens * p.cache_read
                + usage.cache_creation_tokens * p.cache_creation
            ) / 1_000_000
    return None
