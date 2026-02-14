"""Unit tests for session save/resume functionality."""

import json
import pytest
from collections import Counter
from pathlib import Path

from llm_caller import ConversationMessage, ImageContent, MessageRole, TextContent, UsageStats
from session import (
    SessionState,
    ResumeState,
    serialize_conversation,
    deserialize_conversation,
    save_session,
    load_session,
    save_last_session,
    load_last_session,
    build_resume_state,
)


@pytest.mark.unit
def test_serialize_conversation_text_only():
    """Test serializing conversation with text-only messages."""
    conversation = [
        ConversationMessage(role=MessageRole.USER, content="Hello"),
        ConversationMessage(role=MessageRole.ASSISTANT, content="Hi there"),
    ]

    serialized = serialize_conversation(conversation)

    assert len(serialized) == 2
    assert serialized[0] == {"role": "user", "content": "Hello"}
    assert serialized[1] == {"role": "assistant", "content": "Hi there"}


@pytest.mark.unit
def test_serialize_conversation_strips_images():
    """Test that images are replaced with placeholder text during serialization."""
    conversation = [
        ConversationMessage(
            role=MessageRole.USER,
            content=[
                ImageContent(data="base64image", media_type="image/png"),
                TextContent(text="What do you see?"),
            ],
        ),
        ConversationMessage(role=MessageRole.ASSISTANT, content="I see an image"),
    ]

    serialized = serialize_conversation(conversation)

    assert len(serialized) == 2
    assert serialized[0]["role"] == "user"
    assert "[screenshot omitted]" in serialized[0]["content"]
    assert "What do you see?" in serialized[0]["content"]
    assert "base64image" not in serialized[0]["content"]


@pytest.mark.unit
def test_deserialize_conversation():
    """Test deserializing conversation from JSON."""
    data = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there"},
    ]

    conversation = deserialize_conversation(data)

    assert len(conversation) == 2
    assert conversation[0].role == MessageRole.USER
    assert conversation[0].content == "Hello"
    assert conversation[1].role == MessageRole.ASSISTANT
    assert conversation[1].content == "Hi there"


@pytest.mark.unit
def test_serialize_deserialize_roundtrip():
    """Test that text-only conversation survives roundtrip."""
    original = [
        ConversationMessage(role=MessageRole.USER, content="Test message"),
        ConversationMessage(role=MessageRole.ASSISTANT, content="Response"),
    ]

    serialized = serialize_conversation(original)
    deserialized = deserialize_conversation(serialized)

    assert len(deserialized) == len(original)
    assert deserialized[0].content == original[0].content
    assert deserialized[1].content == original[1].content


@pytest.mark.unit
def test_save_and_load_session(tmp_path):
    """Test saving and loading session state."""
    session_dir = tmp_path / "test_session"
    session_dir.mkdir()

    # Create session state
    state = SessionState(
        version=1,
        status="in_progress",
        url="https://example.com",
        last_url="https://example.com/page1",
        scenario="Test scenario",
        model="claude-haiku-4-5@20251001",
        fallback_model="claude-sonnet-4-5@20250929",
        use_smart_model=False,
        viewport={"width": 1280, "height": 720},
        headless=True,
        pause=False,
        max_steps=10,
        step=3,
        elapsed_seconds=45.5,
        screenshot_counts={"abc123": 2, "def456": 1},
        screenshot_warnings={"abc123": 1},
        conversation=[
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ],
        usage={"input_tokens": 1000, "output_tokens": 500, "cache_read_tokens": 0, "cache_creation_tokens": 0},
    )

    # Save session
    save_session(session_dir, state)

    # Verify file exists
    session_file = session_dir / "session.json"
    assert session_file.exists()

    # Load session
    loaded = load_session(session_dir)

    # Verify loaded state matches original
    assert loaded.version == state.version
    assert loaded.status == state.status
    assert loaded.url == state.url
    assert loaded.last_url == state.last_url
    assert loaded.scenario == state.scenario
    assert loaded.model == state.model
    assert loaded.fallback_model == state.fallback_model
    assert loaded.use_smart_model == state.use_smart_model
    assert loaded.step == state.step
    assert loaded.elapsed_seconds == state.elapsed_seconds
    assert loaded.screenshot_counts == state.screenshot_counts
    assert loaded.conversation == state.conversation
    assert loaded.usage == state.usage


@pytest.mark.unit
def test_save_session_atomic_write(tmp_path):
    """Test that session save is atomic (temp file then rename)."""
    session_dir = tmp_path / "test_session"
    session_dir.mkdir()

    state = SessionState(
        version=1,
        status="in_progress",
        url="https://example.com",
        last_url="https://example.com",
        scenario="Test",
        model="test-model",
        viewport={"width": 1280, "height": 720},
        headless=True,
        pause=False,
        max_steps=5,
        step=1,
        elapsed_seconds=10.0,
        screenshot_counts={},
        screenshot_warnings={},
        conversation=[],
        usage={},
    )

    save_session(session_dir, state)

    # Check that no .tmp files remain
    tmp_files = list(session_dir.glob("*.tmp"))
    assert len(tmp_files) == 0

    # Check that session.json exists and is valid JSON
    session_file = session_dir / "session.json"
    assert session_file.exists()
    data = json.loads(session_file.read_text())
    assert data["version"] == 1


@pytest.mark.unit
def test_build_resume_state():
    """Test building ResumeState from SessionState."""
    session = SessionState(
        version=1,
        status="in_progress",
        url="https://example.com",
        last_url="https://example.com/page2",
        scenario="Test scenario",
        model="claude-haiku-4-5",
        viewport={"width": 1280, "height": 720},
        headless=True,
        pause=False,
        max_steps=10,
        step=5,
        elapsed_seconds=120.5,
        screenshot_counts={"hash1": 3, "hash2": 1},
        screenshot_warnings={"hash1": 2},
        conversation=[
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ],
        usage={
            "input_tokens": 5000,
            "output_tokens": 1000,
            "cache_read_tokens": 2000,
            "cache_creation_tokens": 500,
        },
        use_smart_model=True,
    )

    resume = build_resume_state(session)

    assert resume.step == 5
    assert resume.elapsed_seconds == 120.5
    assert resume.screenshot_counts == Counter({"hash1": 3, "hash2": 1})
    assert resume.screenshot_warnings == Counter({"hash1": 2})
    assert len(resume.conversation) == 2
    assert resume.conversation[0].role == MessageRole.USER
    assert resume.conversation[0].content == "Hello"
    assert resume.last_url == "https://example.com/page2"
    assert resume.usage.input_tokens == 5000
    assert resume.usage.output_tokens == 1000
    assert resume.usage.cache_read_tokens == 2000
    assert resume.usage.cache_creation_tokens == 500
    assert resume.use_smart_model is True


@pytest.mark.unit
def test_load_session_missing_file(tmp_path):
    """Test that loading missing session raises FileNotFoundError."""
    session_dir = tmp_path / "nonexistent"

    with pytest.raises(FileNotFoundError, match="No session.json found"):
        load_session(session_dir)


@pytest.mark.unit
def test_load_session_invalid_version(tmp_path):
    """Test that loading session with wrong version raises ValueError."""
    session_dir = tmp_path / "test_session"
    session_dir.mkdir()

    # Create session file with wrong version
    session_file = session_dir / "session.json"
    session_file.write_text(json.dumps({"version": 999}))

    with pytest.raises(ValueError, match="Unsupported session version"):
        load_session(session_dir)


@pytest.mark.unit
def test_session_with_defaults(tmp_path):
    """Test loading session with optional fields missing."""
    session_dir = tmp_path / "test_session"
    session_dir.mkdir()

    # Minimal session JSON (missing optional fields)
    minimal_session = {
        "version": 1,
        "status": "in_progress",
        "url": "https://example.com",
        "last_url": "https://example.com",
        "scenario": "Test",
        "model": "test-model",
        "viewport": {"width": 1280, "height": 720},
        "headless": True,
        "max_steps": 5,
        "step": 1,
        "elapsed_seconds": 10.0,
        "screenshot_counts": {},
        "screenshot_warnings": {},
        "conversation": [],
    }

    session_file = session_dir / "session.json"
    session_file.write_text(json.dumps(minimal_session))

    loaded = load_session(session_dir)

    # Check defaults are applied
    assert loaded.pause is False  # default
    assert loaded.usage == {}  # default empty dict
    assert loaded.fallback_model is None  # default
    assert loaded.use_smart_model is False  # default


@pytest.mark.unit
def test_save_and_load_last_session(tmp_path, monkeypatch):
    """Test saving and loading last session path."""
    import session

    # Patch the sessions directory to use tmp_path
    sessions_dir = tmp_path / "sessions"
    monkeypatch.setattr(session, "_SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr(session, "_LAST_SESSION_FILE", sessions_dir / ".last_session")

    # Create a test session directory
    session_dir = sessions_dir / "2026-02-13_14-30-00"
    session_dir.mkdir(parents=True)

    # Create minimal session.json
    session_file = session_dir / "session.json"
    session_file.write_text(json.dumps({"version": 1, "status": "in_progress"}))

    # Save as last session (relative path under sessions/)
    save_last_session(session_dir)

    # Load last session
    loaded_path = load_last_session()

    assert loaded_path == session_dir


@pytest.mark.unit
def test_save_last_session_absolute_path(tmp_path, monkeypatch):
    """Test saving last session with absolute path."""
    import session

    # Patch the sessions directory to use tmp_path
    sessions_dir = tmp_path / "sessions"
    monkeypatch.setattr(session, "_SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr(session, "_LAST_SESSION_FILE", sessions_dir / ".last_session")

    # Create session outside sessions/
    session_dir = tmp_path / "custom" / "my-session"
    session_dir.mkdir(parents=True)

    # Create minimal session.json
    session_file = session_dir / "session.json"
    session_file.write_text(json.dumps({"version": 1, "status": "in_progress"}))

    # Save as last session (absolute path)
    save_last_session(session_dir)

    # Load last session
    loaded_path = load_last_session()

    assert loaded_path == session_dir.resolve()


@pytest.mark.unit
def test_load_last_session_missing_file(tmp_path, monkeypatch):
    """Test that loading last session without .last_session file raises error."""
    import session

    # Patch the sessions directory to use tmp_path
    sessions_dir = tmp_path / "sessions"
    monkeypatch.setattr(session, "_SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr(session, "_LAST_SESSION_FILE", sessions_dir / ".last_session")

    with pytest.raises(FileNotFoundError, match="No .last_session file found"):
        load_last_session()


@pytest.mark.unit
def test_load_last_session_invalid_path(tmp_path, monkeypatch):
    """Test that loading last session with invalid path raises error."""
    import session

    # Patch the sessions directory to use tmp_path
    sessions_dir = tmp_path / "sessions"
    sessions_dir.mkdir(parents=True)
    monkeypatch.setattr(session, "_SESSIONS_DIR", sessions_dir)
    monkeypatch.setattr(session, "_LAST_SESSION_FILE", sessions_dir / ".last_session")

    # Create .last_session pointing to nonexistent directory
    last_session_file = sessions_dir / ".last_session"
    last_session_file.write_text("nonexistent-session")

    with pytest.raises(FileNotFoundError, match="Last session not found"):
        load_last_session()
