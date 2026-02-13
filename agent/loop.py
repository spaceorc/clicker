"""Core agent loop: screenshot -> LLM -> action -> execute."""

import base64
import hashlib
import json
import logging
import time
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import console as console_output
from browser.controller import BrowserController
from llm_caller import ConversationMessage, ImageContent, LlmCaller, MessageRole, TextContent, UsageStats
from session import ResumeState

from .actions import (
    AgentResponse,
    ClickAction,
    DoneAction,
    DoubleClickAction,
    DragAction,
    FailAction,
    PressKeyAction,
    ScrollAction,
    TypeAction,
    WaitAction,
)
from .prompts import build_system_prompt

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class AgentResult:
    """Result of an agent run."""

    success: bool
    summary: str
    steps_taken: int
    usage: UsageStats


_POST_ACTION_DELAY_MS = 2000
_COMPRESS_THRESHOLD = 50  # compress when conversation reaches this many messages
_COMPRESS_KEEP_RECENT = 10  # keep this many recent messages after compression
_STUCK_SCREENSHOT_LIMIT = 5  # same screenshot seen this many times = stuck
_TIMEOUT_SECONDS = 30 * 60  # 30 minutes total


async def _execute_action(browser: BrowserController, action: AgentResponse) -> None:
    """Execute an action on the browser, then wait for the page to settle."""
    act = action.action
    match act:
        case ClickAction():
            await browser.click(act.x, act.y)
        case DoubleClickAction():
            await browser.double_click(act.x, act.y)
        case TypeAction():
            await browser.type_text(act.text)
        case PressKeyAction():
            await browser.press_key(act.key)
        case ScrollAction():
            await browser.scroll(act.x, act.y, act.delta_x, act.delta_y)
        case DragAction():
            await browser.drag(act.from_x, act.from_y, act.to_x, act.to_y)
        case WaitAction():
            await browser.wait(act.ms)
            return  # already waited, skip post-action delay
        case DoneAction() | FailAction():
            return  # terminal actions, no delay needed

    await browser.wait(_POST_ACTION_DELAY_MS)


def _compress_conversation(conversation: list[ConversationMessage]) -> list[ConversationMessage]:
    """Compress old conversation messages into a summary, keeping recent ones."""
    if len(conversation) <= _COMPRESS_THRESHOLD:
        return conversation

    to_compress = conversation[:-_COMPRESS_KEEP_RECENT]
    to_keep = conversation[-_COMPRESS_KEEP_RECENT:]

    # Build summary from old assistant messages
    summary_lines: list[str] = ["Summary of previous steps:"]
    step_num = 0
    for msg in to_compress:
        if msg.role == MessageRole.ASSISTANT and isinstance(msg.content, str):
            step_num += 1
            try:
                data = json.loads(msg.content)
                obs = data.get("observation", "")[:150]
                action = data.get("action", {})
                summary_lines.append(f"  Step {step_num}: [{action.get('action', '?')}] {obs}")
            except (json.JSONDecodeError, AttributeError):
                summary_lines.append(f"  Step {step_num}: {msg.content[:150]}")

    summary_text = "\n".join(summary_lines)
    logger.info("Compressed %d messages into summary (%d chars)", len(to_compress), len(summary_text))

    summary_msg = ConversationMessage(role=MessageRole.USER, content=summary_text)

    # Ensure conversation starts with user message and alternates properly
    result = [summary_msg]
    # Need a dummy assistant response after summary to maintain alternation
    result.append(ConversationMessage(
        role=MessageRole.ASSISTANT,
        content='{"observation": "Understood the summary of previous steps.", "reasoning": "Continuing from where we left off.", "action": {"action": "wait", "ms": 0}}',
    ))
    result.extend(to_keep)
    return result


async def run_agent(
    llm: LlmCaller,
    browser: BrowserController,
    scenario: str,
    max_steps: int = 0,
    screenshots_dir: Path | None = None,
    on_step_done: Callable[[ResumeState], None] | None = None,
    resume: ResumeState | None = None,
) -> AgentResult:
    """Run the agent loop.

    Assumes the browser is already navigated to the starting page.

    Args:
        llm: LLM caller instance
        browser: Browser controller instance
        scenario: Goal/scenario to accomplish
        max_steps: Maximum number of steps (0 = unlimited)
        screenshots_dir: If set, save each step's screenshot as PNG here
        on_step_done: Callback invoked after each step with current state snapshot
        resume: If provided, resume from this state instead of starting fresh

    Returns:
        AgentResult with success status, summary, steps taken, and usage
    """
    system_prompt = build_system_prompt(scenario, browser.viewport.width, browser.viewport.height)

    if resume:
        conversation = resume.conversation
        screenshot_counts = resume.screenshot_counts
        screenshot_warnings = resume.screenshot_warnings
        start_time = time.monotonic() - resume.elapsed_seconds
        step = resume.step
        total_usage = resume.usage

        # Inject resume note into conversation
        conversation.append(ConversationMessage(
            role=MessageRole.USER,
            content=(
                "Session resumed. The browser has been restarted and navigated to the last known URL. "
                "A fresh screenshot will follow. Continue from where you left off."
            ),
        ))
        conversation.append(ConversationMessage(
            role=MessageRole.ASSISTANT,
            content='{"observation": "Session resumed successfully.", "reasoning": "Continuing from the resumed state.", "next_step": "Taking a fresh look at the current page", "action": {"action": "wait", "ms": 0}}',
        ))
    else:
        conversation = []
        screenshot_counts = Counter()
        screenshot_warnings = Counter()
        start_time = time.monotonic()
        step = 0
        total_usage = UsageStats()

    if screenshots_dir is not None:
        screenshots_dir.mkdir(parents=True, exist_ok=True)
        logger.info("Saving screenshots to %s", screenshots_dir)

    while True:
        step += 1

        if max_steps > 0 and step > max_steps:
            return AgentResult(success=False, summary=f"Max steps ({max_steps}) exceeded", steps_taken=step - 1, usage=total_usage)

        elapsed = time.monotonic() - start_time
        if elapsed > _TIMEOUT_SECONDS:
            logger.warning("Timeout after %.0f seconds", elapsed)
            return AgentResult(success=False, summary=f"Timeout after {int(elapsed)}s", steps_taken=step - 1, usage=total_usage)

        # Take screenshot
        screenshot_b64 = await browser.screenshot_base64()
        current_url = await browser.current_url()

        if screenshots_dir is not None:
            (screenshots_dir / f"step_{step:03d}.png").write_bytes(base64.b64decode(screenshot_b64))

        # Track screenshot repeats
        screenshot_hash = hashlib.md5(screenshot_b64.encode()).hexdigest()
        screenshot_counts[screenshot_hash] += 1
        repeat_count = screenshot_counts[screenshot_hash]

        console_output.step_start(step)

        stuck_hint = ""
        if repeat_count >= _STUCK_SCREENSHOT_LIMIT:
            screenshot_warnings[screenshot_hash] += 1
            warnings_given = screenshot_warnings[screenshot_hash]
            logger.warning("Same screenshot seen %d times, warned %d/3", repeat_count, warnings_given)
            console_output.step_warning(f"Same screen seen {repeat_count} times — warning {warnings_given}/3")
            if warnings_given > 3:
                logger.error("Agent ignored 3 stuck warnings for this screen — force stopping")
                return AgentResult(success=False, summary="Force stopped: stuck on the same screen", steps_taken=step, usage=total_usage)
            stuck_hint = (
                f"\n\nWARNING ({warnings_given}/3): This exact screen has appeared {repeat_count} times already. "
                "You are stuck. Try a COMPLETELY different approach, or use the fail action if you cannot proceed. "
                "You will be force-stopped after 3 warnings."
            )

        # Build user message with screenshot
        step_label = f"Step {step}" if max_steps == 0 else f"Step {step}/{max_steps}"
        user_message = ConversationMessage(
            role=MessageRole.USER,
            content=[
                ImageContent(data=screenshot_b64, media_type="image/png"),
                TextContent(text=f"Current URL: {current_url}\n{step_label}. What should I do next?{stuck_hint}"),
            ],
        )
        conversation.append(user_message)

        # Call LLM
        logger.info("%s — calling LLM...", step_label)
        response, step_usage = await llm.call_llm(system_prompt, conversation, AgentResponse)
        total_usage += step_usage
        console_output.step_usage(step_usage)

        if not isinstance(response, AgentResponse):
            logger.error("Unexpected response type: %s", type(response))
            return AgentResult(success=False, summary=f"Unexpected LLM response: {response}", steps_taken=step, usage=total_usage)

        logger.info("  observation: %s", response.observation[:100])
        logger.info("  reasoning: %s", response.reasoning[:100])
        logger.info("  next_step: %s", response.next_step)
        logger.info("  action: %s", response.action)

        console_output.step_action(response.next_step, str(response.action))

        # Store assistant response as plain text to save tokens
        conversation.append(ConversationMessage(
            role=MessageRole.ASSISTANT,
            content=response.model_dump_json(),
        ))

        # Replace previous user messages that had images with text-only versions to save tokens
        if len(conversation) >= 4:
            old_msg = conversation[-3]
            if old_msg.role == MessageRole.USER and isinstance(old_msg.content, list):
                text_parts = [p.text for p in old_msg.content if isinstance(p, TextContent)]
                conversation[-3] = ConversationMessage(
                    role=MessageRole.USER,
                    content="[screenshot omitted] " + " ".join(text_parts),
                )

        # Compress old conversation if it's getting too long
        conversation = _compress_conversation(conversation)

        # Check for terminal actions
        if isinstance(response.action, DoneAction):
            logger.info("Scenario completed: %s", response.action.summary)
            if on_step_done:
                on_step_done(ResumeState(
                    step=step, elapsed_seconds=time.monotonic() - start_time,
                    screenshot_counts=screenshot_counts, screenshot_warnings=screenshot_warnings,
                    conversation=conversation, last_url=current_url, usage=total_usage,
                ))
            return AgentResult(success=True, summary=response.action.summary, steps_taken=step, usage=total_usage)

        if isinstance(response.action, FailAction):
            logger.warning("Scenario failed: %s", response.action.reason)
            if on_step_done:
                on_step_done(ResumeState(
                    step=step, elapsed_seconds=time.monotonic() - start_time,
                    screenshot_counts=screenshot_counts, screenshot_warnings=screenshot_warnings,
                    conversation=conversation, last_url=current_url, usage=total_usage,
                ))
            return AgentResult(success=False, summary=response.action.reason, steps_taken=step, usage=total_usage)

        # Execute the action
        await _execute_action(browser, response)

        # Notify callback after action execution
        if on_step_done:
            on_step_done(ResumeState(
                step=step, elapsed_seconds=time.monotonic() - start_time,
                screenshot_counts=screenshot_counts, screenshot_warnings=screenshot_warnings,
                conversation=conversation, last_url=await browser.current_url(), usage=total_usage,
            ))
