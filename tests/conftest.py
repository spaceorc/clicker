"""Pytest fixtures for integration tests."""

import pytest
from pathlib import Path

from browser.controller import BrowserController, ViewportSize
from llm_caller.factory import get_llm_caller


@pytest.fixture
async def browser():
    """Provide a Playwright browser instance for tests."""
    viewport = ViewportSize(width=1280, height=720)
    browser = BrowserController(viewport=viewport, headless=True)
    await browser.start()
    yield browser
    await browser.stop()


@pytest.fixture
def llm():
    """Provide default LLM caller (Haiku for cost optimization)."""
    return get_llm_caller("anthropic_vertex", "claude-haiku-4-5@20251001")


@pytest.fixture
def temp_screenshots_dir(tmp_path):
    """Provide temporary directory for test screenshots."""
    screenshots_dir = tmp_path / "screenshots"
    screenshots_dir.mkdir()
    return screenshots_dir
