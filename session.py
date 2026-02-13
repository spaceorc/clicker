"""Session save/resume for crash recovery."""

import json
import logging
import tempfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from llm_caller import ConversationMessage, ImageContent, MessageRole, TextContent, UsageStats

logger = logging.getLogger(__name__)

_SESSIONS_DIR = Path("sessions")
_SCREENSHOT_OMITTED = "[screenshot omitted]"


@dataclass
class SessionState:
    """Full session state persisted to session.json."""

    version: int
    status: Literal["in_progress", "done", "failed", "interrupted"]
    url: str
    last_url: str
    scenario: str
    model: str
    viewport: dict[str, int]
    headless: bool
    pause: bool
    max_steps: int
    step: int
    elapsed_seconds: float
    screenshot_counts: dict[str, int]
    screenshot_warnings: dict[str, int]
    conversation: list[dict[str, Any]]
    usage: dict[str, int] = field(default_factory=dict)
    fallback_model: str | None = None
    use_smart_model: bool = False  # If true, permanently use fallback (smart) model


@dataclass
class ResumeState:
    """Subset of session state needed by the agent loop to resume."""

    step: int
    elapsed_seconds: float
    screenshot_counts: Counter[str]
    screenshot_warnings: Counter[str]
    conversation: list[ConversationMessage]
    last_url: str
    usage: UsageStats
    use_smart_model: bool = False


def serialize_conversation(conversation: list[ConversationMessage]) -> list[dict[str, Any]]:
    """Serialize conversation messages to JSON-safe dicts, stripping images."""
    result: list[dict[str, Any]] = []
    for msg in conversation:
        if isinstance(msg.content, str):
            result.append({"role": msg.role.value, "content": msg.content})
        else:
            # Replace images with placeholder text
            text_parts = [p.text for p in msg.content if isinstance(p, TextContent)]
            content = f"{_SCREENSHOT_OMITTED} " + " ".join(text_parts)
            result.append({"role": msg.role.value, "content": content})
    return result


def deserialize_conversation(data: list[dict[str, Any]]) -> list[ConversationMessage]:
    """Deserialize conversation from JSON dicts (text-only, no images)."""
    result: list[ConversationMessage] = []
    for item in data:
        role = MessageRole(item["role"])
        content = item["content"]
        result.append(ConversationMessage(role=role, content=content))
    return result


def save_session(session_dir: Path, state: SessionState) -> None:
    """Atomically write session state to session.json."""
    data = {
        "version": state.version,
        "status": state.status,
        "url": state.url,
        "last_url": state.last_url,
        "scenario": state.scenario,
        "model": state.model,
        "fallback_model": state.fallback_model,
        "use_smart_model": state.use_smart_model,
        "viewport": state.viewport,
        "headless": state.headless,
        "pause": state.pause,
        "max_steps": state.max_steps,
        "step": state.step,
        "elapsed_seconds": state.elapsed_seconds,
        "screenshot_counts": state.screenshot_counts,
        "screenshot_warnings": state.screenshot_warnings,
        "conversation": state.conversation,
        "usage": state.usage,
    }

    session_file = session_dir / "session.json"
    # Atomic write: write to temp file then rename
    fd, tmp_path = tempfile.mkstemp(dir=session_dir, suffix=".tmp")
    try:
        import os
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        Path(tmp_path).replace(session_file)
    except BaseException:
        Path(tmp_path).unlink(missing_ok=True)
        raise

    logger.debug("Session saved to %s (step %d)", session_file, state.step)


def load_session(session_dir: Path) -> SessionState:
    """Load and validate session state from session.json."""
    session_file = session_dir / "session.json"
    if not session_file.exists():
        raise FileNotFoundError(f"No session.json found in {session_dir}")

    data = json.loads(session_file.read_text(encoding="utf-8"))

    if data.get("version") != 1:
        raise ValueError(f"Unsupported session version: {data.get('version')}")

    return SessionState(
        version=data["version"],
        status=data["status"],
        url=data["url"],
        last_url=data["last_url"],
        scenario=data["scenario"],
        model=data["model"],
        viewport=data["viewport"],
        headless=data["headless"],
        pause=data.get("pause", False),
        max_steps=data["max_steps"],
        step=data["step"],
        elapsed_seconds=data["elapsed_seconds"],
        screenshot_counts=data["screenshot_counts"],
        screenshot_warnings=data["screenshot_warnings"],
        conversation=data["conversation"],
        usage=data.get("usage", {}),
        fallback_model=data.get("fallback_model"),
        use_smart_model=data.get("use_smart_model", False),
    )


def find_latest_session() -> Path:
    """Find the most recent resumable session directory (in_progress or interrupted).

    Returns:
        Path to the session directory

    Raises:
        FileNotFoundError: If no sessions directory or no resumable sessions
    """
    if not _SESSIONS_DIR.exists():
        raise FileNotFoundError("No sessions directory found")

    # Sort session dirs by name (they're datetime-formatted, so alphabetical = chronological)
    session_dirs = sorted(_SESSIONS_DIR.iterdir(), reverse=True)

    for session_dir in session_dirs:
        session_file = session_dir / "session.json"
        if session_file.exists():
            try:
                data = json.loads(session_file.read_text(encoding="utf-8"))
                if data.get("status") in ("in_progress", "interrupted"):
                    return session_dir
            except (json.JSONDecodeError, KeyError):
                continue

    raise FileNotFoundError("No resumable sessions found (looking for in_progress or interrupted)")


def build_resume_state(session: SessionState) -> ResumeState:
    """Build a ResumeState from a loaded SessionState."""
    conversation = deserialize_conversation(session.conversation)
    usage_data = session.usage
    usage = UsageStats(
        input_tokens=usage_data.get("input_tokens", 0),
        output_tokens=usage_data.get("output_tokens", 0),
        cache_read_tokens=usage_data.get("cache_read_tokens", 0),
        cache_creation_tokens=usage_data.get("cache_creation_tokens", 0),
    )
    return ResumeState(
        step=session.step,
        elapsed_seconds=session.elapsed_seconds,
        screenshot_counts=Counter(session.screenshot_counts),
        screenshot_warnings=Counter(session.screenshot_warnings),
        conversation=conversation,
        last_url=session.last_url,
        usage=usage,
        use_smart_model=session.use_smart_model,
    )
