"""Unit tests for Anthropic Vertex location selection."""

import pytest

from llm_caller.anthropic_vertex import _get_location


@pytest.mark.unit
@pytest.mark.parametrize("model", ["claude-sonnet-5-5", "claude-haiku-5-5", "claude-haiku-5-5@default"])
def test_claude_5_5_uses_global_location(model: str, monkeypatch: pytest.MonkeyPatch):
    """Claude 5.5 models are served only on the global endpoint."""
    monkeypatch.setenv("VERTEX_LOCATION", "europe-west1")

    assert _get_location(model) == "global"


@pytest.mark.unit
def test_other_models_use_configured_location(monkeypatch: pytest.MonkeyPatch):
    """Other models go to VERTEX_LOCATION."""
    monkeypatch.setenv("VERTEX_LOCATION", "europe-west1")

    assert _get_location("claude-haiku-4-5@20251001") == "europe-west1"
