"""Unit tests for LLM pricing calculations."""

import pytest

from llm_caller.base import UsageStats
from llm_caller.pricing import estimate_cost


@pytest.mark.unit
def test_estimate_cost_haiku_basic():
    """Test cost calculation for Haiku without caching."""
    usage = UsageStats(
        input_tokens=1000,
        output_tokens=500,
        cache_read_tokens=0,
        cache_creation_tokens=0,
    )

    cost = estimate_cost("claude-haiku-4-5", usage)

    # Haiku: $1 per 1M input, $5 per 1M output
    # 1000 input = $0.001, 500 output = $0.0025
    expected = 0.001 + 0.0025
    assert cost == pytest.approx(expected, abs=0.0001)


@pytest.mark.unit
def test_estimate_cost_sonnet_with_cache():
    """Test cost calculation for Sonnet with prompt caching."""
    usage = UsageStats(
        input_tokens=1000,
        output_tokens=500,
        cache_read_tokens=5000,
        cache_creation_tokens=2000,
    )

    cost = estimate_cost("claude-sonnet-4-5", usage)

    # Sonnet: $3 per 1M input, $15 per 1M output
    # Cache read: $0.30 per 1M (10% of input cost)
    # Cache creation: $3.75 per 1M (1.25x of input cost)
    # 1000 input = $0.003, 500 output = $0.0075
    # 5000 cache_read = $0.0015, 2000 cache_creation = $0.0075
    expected = 0.003 + 0.0075 + 0.0015 + 0.0075
    assert cost == pytest.approx(expected, abs=0.0001)


@pytest.mark.unit
def test_estimate_cost_gemini():
    """Test cost calculation for Gemini Flash Lite."""
    usage = UsageStats(
        input_tokens=10000,
        output_tokens=2000,
        cache_read_tokens=0,
        cache_creation_tokens=0,
    )

    cost = estimate_cost("gemini-2.5-flash-lite", usage)

    # Gemini Flash Lite: $0.10 per 1M input, $0.40 per 1M output
    # 10000 input = $0.001, 2000 output = $0.0008
    expected = 0.001 + 0.0008
    assert cost == pytest.approx(expected, abs=0.0001)


@pytest.mark.unit
def test_estimate_cost_unknown_model():
    """Test that unknown models return None."""
    usage = UsageStats(input_tokens=1000, output_tokens=500)

    cost = estimate_cost("unknown-model-xyz", usage)

    assert cost is None


@pytest.mark.unit
def test_estimate_cost_zero_tokens():
    """Test cost calculation with zero tokens."""
    usage = UsageStats(input_tokens=0, output_tokens=0)

    cost = estimate_cost("claude-haiku-4-5", usage)

    assert cost == 0.0
