"""Pydantic action models for agent responses."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field


class ClickAction(BaseModel):
    """Click at coordinates."""

    action: Literal["click"] = "click"
    x: int = Field(description="X coordinate to click")
    y: int = Field(description="Y coordinate to click")


class DoubleClickAction(BaseModel):
    """Double-click at coordinates."""

    action: Literal["double_click"] = "double_click"
    x: int = Field(description="X coordinate to double-click")
    y: int = Field(description="Y coordinate to double-click")


class TypeAction(BaseModel):
    """Type text into the focused element."""

    action: Literal["type"] = "type"
    text: str = Field(description="Text to type")


class PressKeyAction(BaseModel):
    """Press a keyboard key."""

    action: Literal["press_key"] = "press_key"
    key: str = Field(description="Key to press (e.g. Enter, Tab, Escape, Backspace)")


class ScrollAction(BaseModel):
    """Scroll at a position."""

    action: Literal["scroll"] = "scroll"
    x: int = Field(description="X coordinate to scroll at")
    y: int = Field(description="Y coordinate to scroll at")
    delta_x: int = Field(default=0, description="Horizontal scroll amount (pixels)")
    delta_y: int = Field(description="Vertical scroll amount (pixels, positive=down)")


class WaitAction(BaseModel):
    """Wait for a duration."""

    action: Literal["wait"] = "wait"
    ms: int = Field(description="Duration to wait in milliseconds")


class DragAction(BaseModel):
    """Drag from one position to another."""

    action: Literal["drag"] = "drag"
    from_x: int = Field(description="X coordinate to start dragging from")
    from_y: int = Field(description="Y coordinate to start dragging from")
    to_x: int = Field(description="X coordinate to drop at")
    to_y: int = Field(description="Y coordinate to drop at")


class DoneAction(BaseModel):
    """Scenario completed successfully."""

    action: Literal["done"] = "done"
    summary: str = Field(description="Summary of what was accomplished")


class FailAction(BaseModel):
    """Scenario failed."""

    action: Literal["fail"] = "fail"
    reason: str = Field(description="Reason for failure")


Action = Annotated[
    ClickAction | DoubleClickAction | TypeAction | PressKeyAction | ScrollAction | DragAction | WaitAction | DoneAction | FailAction,
    Field(discriminator="action"),
]


class AgentResponse(BaseModel):
    """LLM response with chain-of-thought and action."""

    observation: str = Field(description="What you see on the current screenshot")
    reasoning: str = Field(description="Why you chose this action")
    next_step: str = Field(description="Short human-readable description of what you are about to do, e.g. 'Clicking the Submit button'")
    action: Action
