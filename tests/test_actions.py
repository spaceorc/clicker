"""Unit tests for Pydantic action models."""

import pytest
from pydantic import ValidationError

from agent.actions import (
    AgentResponse,
    ClickAction,
    DoubleClickAction,
    TypeAction,
    PressKeyAction,
    ScrollAction,
    DragAction,
    WaitAction,
    DoneAction,
    FailAction,
)


@pytest.mark.unit
def test_click_action_valid():
    """Test creating a valid click action."""
    action = ClickAction(x=100, y=200)

    assert action.action == "click"
    assert action.x == 100
    assert action.y == 200


@pytest.mark.unit
def test_double_click_action_valid():
    """Test creating a valid double-click action."""
    action = DoubleClickAction(x=150, y=250)

    assert action.action == "double_click"
    assert action.x == 150
    assert action.y == 250


@pytest.mark.unit
def test_type_action_valid():
    """Test creating a valid type action."""
    action = TypeAction(text="Hello, World!")

    assert action.action == "type"
    assert action.text == "Hello, World!"


@pytest.mark.unit
def test_press_key_action_valid():
    """Test creating a valid press key action."""
    action = PressKeyAction(key="Enter")

    assert action.action == "press_key"
    assert action.key == "Enter"


@pytest.mark.unit
def test_scroll_action_valid():
    """Test creating a valid scroll action."""
    action = ScrollAction(x=640, y=360, delta_y=300)

    assert action.action == "scroll"
    assert action.x == 640
    assert action.y == 360
    assert action.delta_x == 0  # default
    assert action.delta_y == 300


@pytest.mark.unit
def test_drag_action_valid():
    """Test creating a valid drag action."""
    action = DragAction(from_x=100, from_y=100, to_x=200, to_y=200)

    assert action.action == "drag"
    assert action.from_x == 100
    assert action.from_y == 100
    assert action.to_x == 200
    assert action.to_y == 200


@pytest.mark.unit
def test_wait_action_valid():
    """Test creating a valid wait action."""
    action = WaitAction(ms=1000)

    assert action.action == "wait"
    assert action.ms == 1000


@pytest.mark.unit
def test_done_action_valid():
    """Test creating a valid done action."""
    action = DoneAction(summary="Task completed successfully")

    assert action.action == "done"
    assert action.summary == "Task completed successfully"


@pytest.mark.unit
def test_fail_action_valid():
    """Test creating a valid fail action."""
    action = FailAction(reason="Cannot find the button")

    assert action.action == "fail"
    assert action.reason == "Cannot find the button"


@pytest.mark.unit
def test_agent_response_with_click():
    """Test AgentResponse with click action."""
    response = AgentResponse(
        observation="I see a login button",
        reasoning="Need to click the login button",
        next_step="Clicking login button",
        estimated_steps_remaining=3,
        request_smart_model=False,
        action=ClickAction(x=500, y=300),
    )

    assert response.observation == "I see a login button"
    assert response.reasoning == "Need to click the login button"
    assert response.next_step == "Clicking login button"
    assert response.estimated_steps_remaining == 3
    assert response.request_smart_model is False
    assert isinstance(response.action, ClickAction)
    assert response.action.x == 500


@pytest.mark.unit
def test_agent_response_with_done():
    """Test AgentResponse with done action."""
    response = AgentResponse(
        observation="Login successful",
        reasoning="Task completed",
        next_step="Finishing task",
        action=DoneAction(summary="Successfully logged in"),
    )

    assert isinstance(response.action, DoneAction)
    assert response.action.summary == "Successfully logged in"


@pytest.mark.unit
def test_agent_response_request_smart_model():
    """Test AgentResponse requesting smart model upgrade."""
    response = AgentResponse(
        observation="This is a complex math problem",
        reasoning="Need better reasoning for this",
        next_step="Solving the problem",
        request_smart_model=True,
        action=WaitAction(ms=1000),
    )

    assert response.request_smart_model is True


@pytest.mark.unit
def test_agent_response_optional_fields():
    """Test AgentResponse with optional fields omitted."""
    response = AgentResponse(
        observation="Page loaded",
        reasoning="Ready to proceed",
        next_step="Clicking button",
        action=ClickAction(x=100, y=100),
    )

    assert response.estimated_steps_remaining is None  # optional, not provided
    assert response.request_smart_model is False  # default value


@pytest.mark.unit
def test_agent_response_json_serialization():
    """Test that AgentResponse can be serialized to JSON."""
    response = AgentResponse(
        observation="Test",
        reasoning="Test reason",
        next_step="Test step",
        estimated_steps_remaining=5,
        action=ClickAction(x=100, y=200),
    )

    json_str = response.model_dump_json()

    # Verify JSON contains expected fields
    import json
    data = json.loads(json_str)
    assert data["observation"] == "Test"
    assert data["action"]["action"] == "click"
    assert data["action"]["x"] == 100


@pytest.mark.unit
def test_agent_response_json_deserialization():
    """Test that AgentResponse can be deserialized from JSON."""
    json_data = {
        "observation": "Test observation",
        "reasoning": "Test reasoning",
        "next_step": "Test next step",
        "estimated_steps_remaining": 3,
        "request_smart_model": False,
        "action": {
            "action": "type",
            "text": "Hello",
        },
    }

    response = AgentResponse.model_validate(json_data)

    assert response.observation == "Test observation"
    assert isinstance(response.action, TypeAction)
    assert response.action.text == "Hello"


@pytest.mark.unit
def test_action_discriminator():
    """Test that action discriminator works correctly."""
    # Test with different action types
    actions_data = [
        {"action": "click", "x": 100, "y": 200},
        {"action": "type", "text": "test"},
        {"action": "done", "summary": "finished"},
    ]

    for action_data in actions_data:
        response_data = {
            "observation": "test",
            "reasoning": "test",
            "next_step": "test",
            "action": action_data,
        }
        response = AgentResponse.model_validate(response_data)
        assert response.action.action == action_data["action"]


@pytest.mark.unit
def test_invalid_action_type():
    """Test that invalid action type is rejected."""
    with pytest.raises(ValidationError):
        AgentResponse(
            observation="test",
            reasoning="test",
            next_step="test",
            action={"action": "invalid_action", "foo": "bar"},  # type: ignore
        )


@pytest.mark.unit
def test_missing_required_fields():
    """Test that missing required fields raise ValidationError."""
    with pytest.raises(ValidationError):
        ClickAction(x=100)  # missing y  # type: ignore

    with pytest.raises(ValidationError):
        TypeAction()  # missing text  # type: ignore

    with pytest.raises(ValidationError):
        DoneAction()  # missing summary  # type: ignore


@pytest.mark.unit
def test_scroll_action_default_delta_x():
    """Test that ScrollAction has default delta_x of 0."""
    action = ScrollAction(x=100, y=100, delta_y=200)

    assert action.delta_x == 0  # default value


@pytest.mark.unit
def test_agent_response_from_llm_json():
    """Test parsing real LLM-like JSON response."""
    # Simulate JSON response from LLM
    llm_json = """
    {
        "observation": "I can see a submit button at coordinates (550, 320)",
        "reasoning": "The form is filled, now I need to submit it",
        "next_step": "Clicking the submit button",
        "estimated_steps_remaining": 2,
        "request_smart_model": false,
        "action": {
            "action": "click",
            "x": 550,
            "y": 320
        }
    }
    """

    import json
    data = json.loads(llm_json)
    response = AgentResponse.model_validate(data)

    assert isinstance(response.action, ClickAction)
    assert response.action.x == 550
    assert response.action.y == 320
    assert response.estimated_steps_remaining == 2
