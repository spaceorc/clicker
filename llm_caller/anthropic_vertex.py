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

from .base import ConversationMessage, ImageContent, JsonSchemaType, LlmCaller, LlmProvider, MessageRole, TextContent

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


# Singleton instance of Anthropic client
_anthropic_client: AsyncAnthropicVertex | None = None


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


def _get_anthropic_client() -> AsyncAnthropicVertex:
    """Get or create Anthropic Vertex AI client singleton."""
    global _anthropic_client

    if _anthropic_client is None:
        vertex_project_name = os.environ.get("VERTEX_PROJECT_NAME")
        vertex_location = os.environ.get("VERTEX_LOCATION")

        if not vertex_project_name:
            raise ValueError("VERTEX_PROJECT_NAME environment variable is not set")
        if not vertex_location:
            raise ValueError("VERTEX_LOCATION environment variable is not set")

        # Create credentials in-memory
        credentials = _create_google_credentials()

        _anthropic_client = AsyncAnthropicVertex(
            region=vertex_location,
            project_id=vertex_project_name,
            credentials=credentials,
        )

    return _anthropic_client


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
        """Convert conversation history to Anthropic message format."""
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
        return result

    def _create_retry_message(self, error_msg: str) -> dict[str, Any]:
        """Create a retry message for Anthropic."""
        return {"role": "user", "content": f"Error: {error_msg}. Please provide a valid JSON response."}

    async def _do_api_call(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        json_schema: JsonSchemaType,
    ) -> str | None:
        """Make the actual API call to Anthropic Vertex AI."""
        client = _get_anthropic_client()

        # Append schema to system prompt if provided
        enhanced_system_prompt = system_prompt
        if json_schema:
            enhanced_system_prompt = system_prompt + _format_schema_prompt(json_schema)

        # Convert to Anthropic MessageParam format
        anthropic_messages = [MessageParam(role=msg["role"], content=msg["content"]) for msg in messages]  # type: ignore[arg-type]

        response = await client.messages.create(
            model=self.__model,
            max_tokens=self.MAX_TOKENS,
            temperature=self.TEMPERATURE,
            system=enhanced_system_prompt,
            messages=anthropic_messages,
        )

        if not response.content or len(response.content) == 0:
            return None

        first_block = response.content[0]
        if not isinstance(first_block, TextBlock):
            logger.warning("First block is not a TextBlock: %s", type(first_block))
            return None

        return first_block.text
