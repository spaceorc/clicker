"""Anthropic Vertex AI LLM caller implementation."""

import base64
import json
import logging
import os
from typing import Any, Literal

from anthropic import AsyncAnthropicVertex
from anthropic.types import MessageParam, TextBlock
from google.oauth2 import service_account
from pydantic import BaseModel

from .base import ConversationMessage, ImageContent, JsonSchemaType, LlmCaller, LlmProvider, LlmResult, MessageRole, TextContent, UsageStats

logger = logging.getLogger(__name__)

# Role mapping
_ROLE_TO_ANTHROPIC: dict[MessageRole, Literal["user", "assistant"]] = {
    MessageRole.USER: "user",
    MessageRole.ASSISTANT: "assistant",
}


def _format_schema_prompt(json_schema: type[BaseModel] | dict[str, Any]) -> str:
    """Format JSON schema as prompt section.

    Args:
        json_schema: Pydantic model class or raw JSON schema dict

    Returns:
        Formatted schema prompt section
    """
    if isinstance(json_schema, type) and issubclass(json_schema, BaseModel):  # pyright: ignore[reportUnnecessaryIsInstance]
        schema = json_schema.model_json_schema()
    else:
        schema = json_schema
    return f"""
## Response Format

You must respond with valid JSON matching this schema:

```json
{json.dumps(schema, indent=2)}
```

Do not include markdown code blocks - respond with raw JSON only.
"""


# Anthropic clients by Vertex location
_anthropic_clients: dict[str, AsyncAnthropicVertex] = {}

# Models Vertex serves only on the global endpoint (with our project a regional location answers 404)
_GLOBAL_ONLY_MODELS = ("claude-sonnet-5-5", "claude-haiku-5-5")


def _create_google_credentials() -> service_account.Credentials:
    """Create Google credentials from environment variable.

    Returns:
        Google service account credentials object with proper scopes
    """
    vertex_credentials = os.environ.get("VERTEX_CREDENTIALS")
    if not vertex_credentials:
        raise ValueError("VERTEX_CREDENTIALS environment variable is not set")

    # Decode base64-encoded credentials
    google_credentials_json = base64.b64decode(vertex_credentials.encode()).decode()
    credentials_info = json.loads(google_credentials_json)

    # Create credentials in-memory with Vertex AI scopes
    credentials = service_account.Credentials.from_service_account_info(credentials_info)

    # Add required scopes for Vertex AI
    return credentials.with_scopes(
        [
            "https://www.googleapis.com/auth/cloud-platform",
            "https://www.googleapis.com/auth/cloud-platform.read-only",
        ]
    )


def _get_location(model: str) -> str:
    """Get the Vertex location to call the model in."""
    if model.split("@", 1)[0] in _GLOBAL_ONLY_MODELS:
        return "global"

    vertex_location = os.environ.get("VERTEX_LOCATION")
    if not vertex_location:
        raise ValueError("VERTEX_LOCATION environment variable is not set")
    return vertex_location


def _get_anthropic_client(model: str) -> AsyncAnthropicVertex:
    """Get or create Anthropic Vertex AI client for the model's location."""
    location = _get_location(model)

    if location not in _anthropic_clients:
        vertex_project_name = os.environ.get("VERTEX_PROJECT_NAME")
        if not vertex_project_name:
            raise ValueError("VERTEX_PROJECT_NAME environment variable is not set")

        # Create credentials in-memory
        credentials = _create_google_credentials()

        _anthropic_clients[location] = AsyncAnthropicVertex(
            region=location,
            project_id=vertex_project_name,
            credentials=credentials,
        )

    return _anthropic_clients[location]


class AnthropicVertexLlmCaller(LlmCaller):
    """LLM caller using Anthropic Vertex AI (Claude)."""

    __slots__ = ("__model",)

    def __init__(self, model: str) -> None:
        self.__model = model

    @property
    def provider(self) -> LlmProvider:
        """Get the LLM provider name."""
        return "anthropic_vertex"

    @property
    def model(self) -> str:
        """Get the model identifier."""
        return self.__model

    def _convert_messages(self, conversation_history: list[ConversationMessage]) -> list[dict[str, Any]]:
        """Convert conversation history to Anthropic message format.

        Adds cache_control breakpoint to the last content block of the second-to-last
        message to enable prompt caching of the conversation prefix.
        """
        result: list[dict[str, Any]] = []
        for msg in conversation_history:
            if isinstance(msg.content, str):
                result.append({"role": _ROLE_TO_ANTHROPIC[msg.role], "content": msg.content})
            else:
                parts: list[dict[str, Any]] = []
                for part in msg.content:
                    if isinstance(part, TextContent):
                        parts.append({"type": "text", "text": part.text})
                    elif isinstance(part, ImageContent):
                        parts.append({
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": part.media_type,
                                "data": part.data,
                            },
                        })
                result.append({"role": _ROLE_TO_ANTHROPIC[msg.role], "content": parts})

        # Add cache_control to last content block of second-to-last message
        if len(result) >= 2:
            second_to_last = result[-2]
            content = second_to_last["content"]
            if isinstance(content, list) and content:
                content[-1]["cache_control"] = {"type": "ephemeral"}
            elif isinstance(content, str):
                # Convert string content to block list so we can add cache_control
                second_to_last["content"] = [
                    {"type": "text", "text": content, "cache_control": {"type": "ephemeral"}}
                ]

        return result

    def _create_retry_message(self, error_msg: str) -> dict[str, Any]:
        """Create a retry message for Anthropic."""
        return {"role": "user", "content": f"Error: {error_msg}. Please provide a valid JSON response."}

    async def _do_api_call(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        json_schema: JsonSchemaType,
    ) -> LlmResult:
        """Make the actual API call to Anthropic Vertex AI."""
        client = _get_anthropic_client(self.__model)

        # Append schema to system prompt if provided
        enhanced_system_prompt = system_prompt
        if json_schema:
            enhanced_system_prompt = system_prompt + _format_schema_prompt(json_schema)

        # Pass system as content block list with cache_control on last block
        system_blocks: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": enhanced_system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        # Convert to Anthropic MessageParam format
        anthropic_messages = [MessageParam(role=msg["role"], content=msg["content"]) for msg in messages]  # type: ignore[arg-type]

        response = await client.messages.create(
            model=self.__model,
            max_tokens=self.MAX_TOKENS,
            temperature=self.TEMPERATURE,
            system=system_blocks,  # type: ignore[arg-type]
            messages=anthropic_messages,
        )

        # Extract usage stats
        usage = UsageStats(
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            cache_read_tokens=getattr(response.usage, "cache_read_input_tokens", 0) or 0,
            cache_creation_tokens=getattr(response.usage, "cache_creation_input_tokens", 0) or 0,
        )

        # Newer models may put thinking blocks before the answer
        text = "".join(block.text for block in response.content if isinstance(block, TextBlock))
        if not text:
            logger.warning("No text blocks in response (stop_reason=%s): %s", response.stop_reason, [block.type for block in response.content])
            return LlmResult(text=None, usage=usage)

        return LlmResult(text=text, usage=usage)
