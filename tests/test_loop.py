"""Unit tests for the agent loop with fake browser and LLMs."""

import base64

import pytest

from agent.actions import AgentResponse
from agent.loop import run_agent
from browser.controller import PageInfo, ViewportSize
from llm_caller import TextContent, UsageStats


class FakeBrowser:
    """Browser that shows a new screen after every action."""

    viewport = ViewportSize()

    def __init__(self) -> None:
        self._screen = 0

    async def screenshot_base64(self) -> str:
        return base64.b64encode(f"screen {self._screen}".encode()).decode()

    async def current_url(self) -> str:
        return "https://example.com"

    async def list_pages(self) -> list[PageInfo]:
        return [PageInfo(id=1, url="https://example.com", title="Example", active=True)]

    async def click(self, x: int, y: int) -> None:
        self._screen += 1

    async def wait(self, ms: int) -> None:
        pass


class FakeLlm:
    """LLM that replies with scripted responses shared between models and records who answered."""

    def __init__(self, model: str, script: list[dict], calls: list[tuple[str, str]]) -> None:
        self.model = model
        self._script = script
        self._calls = calls

    async def call_llm(self, system_prompt, conversation, json_schema):
        text = " ".join(p.text for p in conversation[-1].content if isinstance(p, TextContent))
        self._calls.append((self.model, text))
        response = AgentResponse.model_validate({
            "observation": "", "reasoning": "", "next_step": "",
            **self._script.pop(0),
        })
        return response, UsageStats()


@pytest.mark.unit
async def test_model_switches_to_smart_and_back_to_fast():
    """The agent can upgrade to the smart model and later downgrade to the fast one."""
    click = {"action": "click", "x": 1, "y": 1}
    script = [
        {"switch_model": "smart", "action": click},
        {"action": click},
        {"switch_model": "fast", "action": click},
        {"action": {"action": "done", "summary": "ok"}},
    ]
    calls: list[tuple[str, str]] = []
    fast = FakeLlm("fast-model", script, calls)
    smart = FakeLlm("smart-model", script, calls)

    result = await run_agent(fast, FakeBrowser(), "scenario", fallback_llm=smart)  # type: ignore[arg-type]

    assert result.success
    assert [model for model, _ in calls] == ["fast-model", "smart-model", "smart-model", "fast-model"]
    assert [text.split("Active model: ")[1].split()[0] for _, text in calls] == ["fast", "smart", "smart", "fast"]


@pytest.mark.unit
@pytest.mark.parametrize(("timeout_seconds", "success"), [(60, False), (0, True)])
async def test_timeout_counts_time_spent_before_resume(timeout_seconds: int, success: bool):
    """The time limit includes time already spent in the session; 0 means unlimited."""
    from collections import Counter

    from session import ResumeState

    resume = ResumeState(
        step=3, elapsed_seconds=120, screenshot_counts=Counter(), screenshot_warnings=Counter(),
        conversation=[], last_url="https://example.com", usage=UsageStats(),
    )
    llm = FakeLlm("fast-model", [{"action": {"action": "done", "summary": "ok"}}], [])

    result = await run_agent(llm, FakeBrowser(), "scenario", resume=resume, timeout_seconds=timeout_seconds)  # type: ignore[arg-type]

    assert result.success is success
    if not success:
        assert result.summary.startswith("Timeout")
