"""OpenAI LLM caller implementation."""

import logging
import os
from typing import Any

from openai import AsyncOpenAI
from openai.types.chat import (
    ChatCompletionAssistantMessageParam,
    ChatCompletionMessageParam,
    ChatCompletionSystemMessageParam,
    ChatCompletionUserMessageParam,
)
from openai.types.shared_params import ResponseFormatJSONSchema, ResponseFormatText
from openai.types.shared_params.response_format_json_schema import JSONSchema
from pydantic import BaseModel

from .base import ConversationMessage, ImageContent, JsonSchemaType, LlmCaller, LlmProvider, TextContent

logger = logging.getLogger(__name__)


def _make_schema_strict(schema: dict) -> dict:
    """Transform Pydantic schema to OpenAI strict mode requirements.

    OpenAI strict mode requires:
    1. All objects must have "additionalProperties": false
    2. All properties must be in "required" array
    3. Optional fields use type union with null: ["type", "null"]

    Args:
        schema: Pydantic model JSON schema

    Returns:
        Transformed schema compatible with OpenAI strict mode
    """

    def strip_ref_extras(item: dict) -> dict:
        """Strip 'default' and 'description' from $ref items - OpenAI doesn't allow $ref with extra keywords."""
        if "$ref" in item:
            # Only keep $ref, remove default, description, and other extra keywords
            extra_keys = {"default", "description", "title"}
            if any(k in item for k in extra_keys):
                return {k: v for k, v in item.items() if k not in extra_keys}
        return item

    def process_property_schema(prop_schema: dict, is_required: bool) -> dict:
        """Process a single property schema."""
        if "$ref" in prop_schema:
            # Strip extra keywords from $ref - OpenAI doesn't allow them
            clean_schema = strip_ref_extras(prop_schema)
            if not is_required:
                return {"anyOf": [clean_schema, {"type": "null"}]}
            return clean_schema

        # Convert oneOf to anyOf (OpenAI doesn't support oneOf)
        if "oneOf" in prop_schema:
            one_of_items = prop_schema["oneOf"]
            prop_schema = {k: v for k, v in prop_schema.items() if k not in ("oneOf", "discriminator")}
            prop_schema["anyOf"] = one_of_items

        if "anyOf" in prop_schema:
            any_of_items = []
            has_null = False

            for item in prop_schema["anyOf"]:
                if item.get("type") == "null":
                    has_null = True
                else:
                    # Strip extra keywords from $ref items inside anyOf
                    clean_item = strip_ref_extras(item) if "$ref" in item else process_object_schema(item)
                    any_of_items.append(clean_item)

            if not is_required and not has_null:
                any_of_items.append({"type": "null"})
            elif is_required and has_null:
                pass
            elif has_null:
                any_of_items.append({"type": "null"})

            result = {**prop_schema, "anyOf": any_of_items}
            result.pop("oneOf", None)
            result.pop("discriminator", None)
            if is_required and "default" in result:
                result = {k: v for k, v in result.items() if k != "default"}
            return result

        result = process_object_schema(prop_schema)

        if not is_required and "type" in result:
            prop_type = result["type"]
            if isinstance(prop_type, str) and prop_type != "null":
                # Use anyOf format for nullable instead of type arrays
                # This is required because OpenAI doesn't support type arrays for complex types
                # when the schema is referenced via anyOf containing $ref
                type_specific_keys = {"type", "items", "properties", "required", "additionalProperties", "enum"}
                metadata_keys = {k: v for k, v in result.items() if k not in type_specific_keys}
                type_schema = {k: v for k, v in result.items() if k in type_specific_keys}
                result = {**metadata_keys, "anyOf": [type_schema, {"type": "null"}]}
            elif isinstance(prop_type, list) and "null" not in prop_type:
                # Already a type array, convert to anyOf
                type_specific_keys = {"type", "items", "properties", "required", "additionalProperties", "enum"}
                metadata_keys = {k: v for k, v in result.items() if k not in type_specific_keys}
                type_schema = {k: v for k, v in result.items() if k in type_specific_keys}
                type_schema["type"] = prop_type[0] if len(prop_type) == 1 else prop_type
                result = {**metadata_keys, "anyOf": [type_schema, {"type": "null"}]}

        if is_required and "default" in result:
            result = {k: v for k, v in result.items() if k != "default"}

        return result

    def process_object_schema(obj: Any) -> Any:
        """Process an object schema (not a property, but a schema definition)."""
        if not isinstance(obj, dict):
            return obj

        if "$ref" in obj:
            return obj

        result = {}

        for key, value in obj.items():
            # OpenAI doesn't support discriminator — strip it
            if key == "discriminator":
                continue

            if key == "$defs":
                processed_defs = {}
                for def_name, def_schema in value.items():
                    processed_defs[def_name] = process_object_schema(def_schema)
                result[key] = processed_defs

            elif key == "properties" and isinstance(value, dict):
                current_required = set(obj.get("required", []))

                processed_props = {}
                for prop_name, prop_schema in value.items():
                    is_required = prop_name in current_required
                    processed_props[prop_name] = process_property_schema(prop_schema, is_required)

                result[key] = processed_props

            elif key == "items" and isinstance(value, dict):
                result[key] = process_object_schema(value)

            # OpenAI doesn't support oneOf — convert to anyOf
            elif key == "oneOf" and isinstance(value, list):
                result["anyOf"] = [process_object_schema(item) if isinstance(item, dict) else item for item in value]

            elif key == "anyOf" and isinstance(value, list):
                result[key] = [process_object_schema(item) if isinstance(item, dict) else item for item in value]

            elif isinstance(value, dict):
                result[key] = process_object_schema(value)

            elif isinstance(value, list):
                result[key] = [process_object_schema(item) if isinstance(item, dict) else item for item in value]

            else:
                result[key] = value

        # If we have properties, treat as object (even without explicit type)
        if "properties" in result:
            result["additionalProperties"] = False
            # Ensure required only contains keys that exist in properties
            all_props = list(result["properties"].keys())
            result["required"] = sorted(all_props)
            if "type" not in result:
                result["type"] = "object"
            # Strip 'default' from all properties since they're all required now
            # OpenAI strict mode doesn't allow default on required fields
            for prop_name, prop_schema in result["properties"].items():
                if isinstance(prop_schema, dict) and "default" in prop_schema:
                    result["properties"][prop_name] = {k: v for k, v in prop_schema.items() if k != "default"}
        elif result.get("type") == "object":
            # OpenAI strict mode requires additionalProperties: false for ALL objects
            # For free-form dicts (additionalProperties: true), we must convert to empty object schema
            result["additionalProperties"] = False
            if "properties" not in result:
                result["properties"] = {}
            if "required" not in result:
                result["required"] = []

        return result

    return process_object_schema(schema)


# Singleton instance of OpenAI client
_openai_client: AsyncOpenAI | None = None


def _get_openai_client() -> AsyncOpenAI:
    """Get or create OpenAI client singleton."""
    global _openai_client

    if _openai_client is None:
        api_key = os.environ.get("OPENAI_API_KEY")
        base_url = os.environ.get("OPENAI_BASE_URL")
        organization = os.environ.get("OPENAI_ORGANIZATION")

        if not api_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")

        if not base_url:
            raise ValueError("OPENAI_BASE_URL environment variable is not set")

        if not organization:
            raise ValueError("OPENAI_ORGANIZATION environment variable is not set")

        _openai_client = AsyncOpenAI(
            api_key=api_key,
            base_url=base_url,
            organization=organization,
        )

    return _openai_client


class OpenAILlmCaller(LlmCaller):
    """LLM caller using OpenAI API (GPT models)."""

    __slots__ = ("__model",)

    def __init__(self, model: str) -> None:
        self.__model = model

    @property
    def provider(self) -> LlmProvider:
        """Get the LLM provider name."""
        return "openai"

    @property
    def model(self) -> str:
        """Get the model identifier."""
        return self.__model

    def _convert_messages(self, conversation_history: list[ConversationMessage]) -> list[dict[str, Any]]:
        """Convert conversation history to OpenAI message format."""
        result: list[dict[str, Any]] = []
        for msg in conversation_history:
            if isinstance(msg.content, str):
                result.append({"role": msg.role.value, "content": msg.content})
            else:
                parts: list[dict[str, Any]] = []
                for part in msg.content:
                    if isinstance(part, TextContent):
                        parts.append({"type": "text", "text": part.text})
                    elif isinstance(part, ImageContent):
                        parts.append({
                            "type": "image_url",
                            "image_url": {"url": f"data:{part.media_type};base64,{part.data}"},
                        })
                result.append({"role": msg.role.value, "content": parts})
        return result

    def _create_retry_message(self, error_msg: str) -> dict[str, Any]:
        """Create a retry message for OpenAI."""
        return {"role": "user", "content": f"Error: {error_msg}. Please provide a valid JSON response."}

    async def _do_api_call(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        json_schema: JsonSchemaType,
    ) -> str | None:
        """Make the actual API call to OpenAI."""
        client = _get_openai_client()

        # Build OpenAI-specific message format
        openai_messages: list[ChatCompletionMessageParam] = [
            ChatCompletionSystemMessageParam(role="system", content=system_prompt),
        ]
        openai_messages.extend(
            [
                ChatCompletionUserMessageParam(role="user", content=msg["content"])
                if msg["role"] == "user"
                else ChatCompletionAssistantMessageParam(role="assistant", content=msg["content"])
                for msg in messages
            ]
        )

        # Build response format based on schema type
        strict_schema: dict | None = None
        if json_schema:
            if isinstance(json_schema, type) and issubclass(json_schema, BaseModel):  # pyright: ignore[reportUnnecessaryIsInstance]
                base_schema = json_schema.model_json_schema()
            else:
                base_schema = json_schema  # type: ignore[assignment]
            strict_schema = _make_schema_strict(base_schema)

            response_format = ResponseFormatJSONSchema(
                type="json_schema",
                json_schema=JSONSchema(
                    name="ResponseSchema",
                    description="Schema for response",
                    schema=strict_schema,
                    strict=True,
                ),
            )
        else:
            response_format = ResponseFormatText(type="text")

        try:
            response = await client.chat.completions.create(
                model=self.__model,
                max_tokens=self.MAX_TOKENS,
                temperature=self.TEMPERATURE,
                messages=openai_messages,
                response_format=response_format,
            )
        except Exception as e:
            if strict_schema is not None and "schema" in str(e).lower():
                import json

                logger.error(f"Schema that caused error:\n{json.dumps(strict_schema, indent=2)}")
            raise

        if not response.choices or len(response.choices) == 0:
            return None

        choice = response.choices[0]
        return choice.message.content
