"""Google Vertex AI LLM caller implementation using Gemini models."""

import base64
import copy
import json
import logging
import os
from typing import Any, Literal

from google import genai
from google.genai.types import Blob, Content, GenerateContentConfig, Part
from google.oauth2 import service_account
from pydantic import BaseModel

from .base import ConversationMessage, ImageContent, JsonSchemaType, LlmCaller, LlmProvider, MessageRole, TextContent

logger = logging.getLogger(__name__)

# Role mapping - Gemini uses "model" for assistant role
_ROLE_TO_GEMINI: dict[MessageRole, Literal["user", "model"]] = {
    MessageRole.USER: "user",
    MessageRole.ASSISTANT: "model",
}


def _convert_schema_to_gemini(schema: dict[str, Any]) -> dict[str, Any]:
    """Convert JSON schema to Gemini-compatible format.

    Gemini's response_schema has specific requirements:
    - Type arrays (e.g., ["string", "null"]) must be converted to anyOf format
    - additionalProperties is not supported and must be removed
    - $defs and $ref must be flattened (inline all referenced schemas)

    Args:
        schema: JSON schema dict (from Pydantic model_json_schema or raw dict)

    Returns:
        Gemini-compatible schema dict
    """
    schema = copy.deepcopy(schema)

    # First, flatten all $ref references if $defs exists
    defs = schema.pop("$defs", {})
    if defs:
        schema = _flatten_refs(schema, defs)

    return _process_schema_node(schema)


def _flatten_refs(node: Any, defs: dict[str, Any]) -> Any:
    """Recursively flatten $ref references by inlining them.

    Args:
        node: Schema node to process
        defs: Dictionary of definitions to inline

    Returns:
        Schema with all $ref replaced by their definitions
    """
    if not isinstance(node, dict):
        return node

    # If this is a $ref, replace with the actual definition
    if "$ref" in node:
        ref_path = node["$ref"]
        # Handle "#/$defs/Name" format
        if ref_path.startswith("#/$defs/"):
            def_name = ref_path.split("/")[-1]
            if def_name in defs:
                # Get the referenced definition and flatten any nested refs
                return _flatten_refs(copy.deepcopy(defs[def_name]), defs)
        # If we can't resolve the ref, return as-is (will likely fail later)
        return node

    result = {}
    for key, value in node.items():
        if isinstance(value, dict):
            result[key] = _flatten_refs(value, defs)
        elif isinstance(value, list):
            result[key] = [_flatten_refs(item, defs) if isinstance(item, dict) else item for item in value]
        else:
            result[key] = value

    return result


def _process_schema_node(node: Any) -> Any:
    """Recursively process a schema node for Gemini compatibility.

    - Convert type arrays to anyOf format
    - Remove additionalProperties (not supported by Gemini)

    Args:
        node: Schema node to process

    Returns:
        Processed schema node
    """
    if not isinstance(node, dict):
        return node

    result = {}

    for key, value in node.items():
        # Convert type arrays to anyOf
        if key == "type" and isinstance(value, list):
            result["anyOf"] = [{"type": t} for t in value]
            continue

        # Remove additionalProperties (not supported)
        if key == "additionalProperties":
            continue

        # Recursively process nested structures
        if isinstance(value, dict):
            result[key] = _process_schema_node(value)
        elif isinstance(value, list):
            result[key] = [_process_schema_node(item) if isinstance(item, dict) else item for item in value]
        else:
            result[key] = value

    return result


# Singleton instance of Gemini client
_gemini_client: genai.Client | None = None


def _create_google_credentials() -> service_account.Credentials:
    """Create Google credentials from VERTEX_CREDENTIALS environment variable.

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


def _get_gemini_client() -> genai.Client:
    """Get or create Gemini Vertex AI client singleton."""
    global _gemini_client

    if _gemini_client is None:
        vertex_project_name = os.environ.get("VERTEX_PROJECT_NAME")
        vertex_location = os.environ.get("VERTEX_LOCATION")

        if not vertex_project_name:
            raise ValueError("VERTEX_PROJECT_NAME environment variable is not set")
        if not vertex_location:
            raise ValueError("VERTEX_LOCATION environment variable is not set")

        # Create credentials in-memory (no temp file needed)
        credentials = _create_google_credentials()

        _gemini_client = genai.Client(
            vertexai=True,
            project=vertex_project_name,
            location=vertex_location,
            credentials=credentials,
        )

    return _gemini_client


class GoogleVertexLlmCaller(LlmCaller):
    """LLM caller using Google Vertex AI (Gemini models)."""

    __slots__ = ("__model",)

    def __init__(self, model: str) -> None:
        self.__model = model

    @property
    def provider(self) -> LlmProvider:
        """Get the LLM provider name."""
        return "google_vertex"

    @property
    def model(self) -> str:
        """Get the model identifier."""
        return self.__model

    def _convert_messages(self, conversation_history: list[ConversationMessage]) -> list[dict[str, Any]]:
        """Convert conversation history to Gemini message format."""
        result: list[dict[str, Any]] = []
        for msg in conversation_history:
            if isinstance(msg.content, str):
                result.append({"role": _ROLE_TO_GEMINI[msg.role], "content": msg.content})
            else:
                parts: list[dict[str, Any]] = []
                for part in msg.content:
                    if isinstance(part, TextContent):
                        parts.append({"type": "text", "text": part.text})
                    elif isinstance(part, ImageContent):
                        parts.append({
                            "type": "image",
                            "media_type": part.media_type,
                            "data": part.data,
                        })
                result.append({"role": _ROLE_TO_GEMINI[msg.role], "content": parts})
        return result

    def _create_retry_message(self, error_msg: str) -> dict[str, Any]:
        """Create a retry message for Gemini."""
        return {"role": "user", "content": f"Error: {error_msg}. Please provide a valid JSON response."}

    async def _do_api_call(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        json_schema: JsonSchemaType,
    ) -> str | None:
        """Make the actual API call to Google Vertex AI (Gemini)."""
        client = _get_gemini_client()

        # Convert messages to Gemini Content format
        contents: list[Content] = []
        for msg in messages:
            content_val = msg["content"]
            if isinstance(content_val, str):
                parts = [Part(text=content_val)]
            else:
                parts = []
                for part in content_val:
                    if part["type"] == "text":
                        parts.append(Part(text=part["text"]))
                    elif part["type"] == "image":
                        decoded_bytes = base64.b64decode(part["data"])
                        parts.append(Part(inline_data=Blob(mime_type=part["media_type"], data=decoded_bytes)))
            contents.append(Content(role=msg["role"], parts=parts))

        # Build config with optional response_schema for structured output
        config_kwargs: dict[str, Any] = {
            "temperature": self.TEMPERATURE,
            "max_output_tokens": self.MAX_TOKENS,
            "system_instruction": system_prompt,
        }

        if json_schema:
            # Convert schema to Gemini format
            if isinstance(json_schema, type) and issubclass(json_schema, BaseModel):  # pyright: ignore[reportUnnecessaryIsInstance]
                base_schema = json_schema.model_json_schema()
            else:
                base_schema = json_schema

            gemini_schema = _convert_schema_to_gemini(base_schema)
            config_kwargs["response_schema"] = gemini_schema
            config_kwargs["response_mime_type"] = "application/json"

        config = GenerateContentConfig(**config_kwargs)

        response = await client.aio.models.generate_content(
            model=self.__model,
            contents=contents,  # pyright: ignore[reportArgumentType]
            config=config,
        )

        # Extract text from response
        if not response.candidates:
            return None

        content = response.candidates[0].content
        if not content or not content.parts:
            return None

        # Concatenate all text parts
        text_parts = [part.text for part in content.parts if part.text]
        if not text_parts:
            return None

        return "".join(text_parts)
