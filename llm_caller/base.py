"""Base abstraction for LLM callers."""

import json
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Any, Literal

import jsonschema
from pydantic import BaseModel, ValidationError

LlmProvider = Literal["anthropic_vertex", "openai", "google_vertex"]

# Type alias for JSON schema - either a Pydantic model class or a raw dict schema
JsonSchemaType = type[BaseModel] | dict[str, Any] | None

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class UsageStats:
    """Token usage statistics from an LLM call."""

    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0

    def __iadd__(self, other: "UsageStats") -> "UsageStats":
        self.input_tokens += other.input_tokens
        self.output_tokens += other.output_tokens
        self.cache_read_tokens += other.cache_read_tokens
        self.cache_creation_tokens += other.cache_creation_tokens
        return self


@dataclass(frozen=True, slots=True)
class LlmResult:
    """Result from a single LLM API call."""

    text: str | None
    usage: UsageStats


class MessageRole(str, Enum):
    """Role in conversation message."""

    USER = "user"
    ASSISTANT = "assistant"


@dataclass(frozen=True, slots=True)
class TextContent:
    """Text content part in a multimodal message."""

    text: str


@dataclass(frozen=True, slots=True)
class ImageContent:
    """Image content part in a multimodal message."""

    data: str  # base64-encoded
    media_type: str  # e.g. "image/png"


ContentPart = TextContent | ImageContent
MessageContent = str | list[ContentPart]


@dataclass(frozen=True, slots=True)
class ConversationMessage:
    """Single message in conversation history."""

    role: MessageRole
    content: MessageContent


class LlmCaller(ABC):
    """Base abstract class for LLM callers."""

    __slots__ = ()

    TEMPERATURE = 1.0
    MAX_TOKENS = 4096
    MAX_RETRIES = 3

    @property
    @abstractmethod
    def provider(self) -> LlmProvider:
        """Get the LLM provider name."""
        ...

    @property
    @abstractmethod
    def model(self) -> str:
        """Get the model identifier."""
        ...

    @abstractmethod
    async def _do_api_call(
        self,
        system_prompt: str,
        messages: list[dict[str, Any]],
        json_schema: JsonSchemaType,
    ) -> LlmResult:
        """Make the actual API call to the LLM provider.

        Args:
            system_prompt: System prompt for the LLM
            messages: List of message dicts in provider-specific format
            json_schema: Optional schema for structured output

        Returns:
            LlmResult with text content and usage stats
        """
        ...

    @abstractmethod
    def _create_retry_message(self, error_msg: str) -> dict[str, Any]:
        """Create a retry message in provider-specific format.

        Args:
            error_msg: Error message to include

        Returns:
            Message dict in provider-specific format
        """
        ...

    @abstractmethod
    def _convert_messages(self, conversation_history: list[ConversationMessage]) -> list[dict[str, Any]]:
        """Convert conversation history to provider-specific message format.

        Args:
            conversation_history: List of ConversationMessage objects

        Returns:
            List of message dicts in provider-specific format
        """
        ...

    @staticmethod
    def _strip_markdown_code_block(text: str) -> str:
        """Strip markdown code blocks from text.

        Args:
            text: Text that may contain markdown code blocks

        Returns:
            Text with code block markers removed
        """
        text = text.strip()
        # Handle complete code blocks
        if text.startswith("```") and text.endswith("```"):
            lines = text.split("\n")
            # Remove first line (```json or ```) and last line (```)
            return "\n".join(lines[1:-1])
        # Handle partial code blocks (truncated responses)
        if text.startswith("```"):
            lines = text.split("\n")
            # Remove first line (```json or ```)
            return "\n".join(lines[1:])
        return text

    @staticmethod
    def _validate_json_response(
        data: Any,
        json_schema: JsonSchemaType,
        is_pydantic_schema: bool,
        is_dict_schema: bool,
    ) -> BaseModel | dict[str, Any]:
        """Validate JSON data against schema.

        Args:
            data: Parsed JSON data
            json_schema: Schema to validate against
            is_pydantic_schema: True if schema is a Pydantic model class
            is_dict_schema: True if schema is a raw dict schema

        Returns:
            Validated data (Pydantic model instance or dict)

        Raises:
            ValidationError: If Pydantic validation fails
            jsonschema.ValidationError: If jsonschema validation fails
        """
        if is_pydantic_schema:
            return json_schema.model_validate(data)  # type: ignore[union-attr]
        if is_dict_schema:
            jsonschema.validate(data, json_schema)  # type: ignore[arg-type]
            return data
        raise ValueError("No schema provided for validation")

    async def call_llm(
        self,
        system_prompt: str,
        conversation_history: list[ConversationMessage],
        json_schema: JsonSchemaType = None,
    ) -> tuple[BaseModel | dict[str, Any] | str, UsageStats]:
        """Call LLM and get response.

        Args:
            system_prompt: System prompt describing the persona/instructions
            conversation_history: List of ConversationMessage objects
            json_schema: Optional schema for response format - either a Pydantic model class
                        or a raw JSON schema dict

        Returns:
            Tuple of:
            - Instance of json_schema model if Pydantic model class provided
            - dict[str, Any] if raw JSON schema dict provided
            - str if no schema provided
            And UsageStats with token counts
        """
        # Determine schema type
        is_pydantic_schema = isinstance(json_schema, type) and issubclass(json_schema, BaseModel)  # pyright: ignore[reportUnnecessaryIsInstance]
        is_dict_schema = isinstance(json_schema, dict)

        # Convert messages to provider format
        messages = self._convert_messages(conversation_history)

        total_usage = UsageStats()

        try:
            for attempt in range(self.MAX_RETRIES):
                result = await self._do_api_call(system_prompt, messages, json_schema)
                total_usage += result.usage
                text_content = result.text

                if text_content is None:
                    error_msg = f"Empty response received from {self.provider}"
                    logger.warning(error_msg)
                    messages.append(self._create_retry_message(error_msg))
                    continue

                if not json_schema:
                    return text_content, total_usage

                # Parse and validate JSON response
                try:
                    text_content = self._strip_markdown_code_block(text_content)
                    data = json.loads(text_content)
                    return self._validate_json_response(data, json_schema, is_pydantic_schema, is_dict_schema), total_usage

                except json.JSONDecodeError as e:
                    error_msg = f"Invalid JSON format: {e}. Content: {text_content[:200]}"
                    logger.warning(f"Attempt {attempt + 1}/{self.MAX_RETRIES}: {error_msg}")
                    messages.append(
                        self._create_retry_message(f"{error_msg}. Please provide valid JSON matching the schema.")
                    )
                    continue

                except ValidationError as e:
                    error_msg = f"JSON does not match schema: {e}. Content: {text_content[:200]}"
                    logger.warning(f"Attempt {attempt + 1}/{self.MAX_RETRIES}: {error_msg}")
                    messages.append(
                        self._create_retry_message(
                            f"{error_msg}. Please ensure all required fields are present and match the schema."
                        )
                    )
                    continue

                except jsonschema.ValidationError as e:
                    error_msg = f"JSON does not match schema: {e.message}. Content: {text_content[:200]}"
                    logger.warning(f"Attempt {attempt + 1}/{self.MAX_RETRIES}: {error_msg}")
                    messages.append(
                        self._create_retry_message(
                            f"{error_msg}. Please ensure all required fields are present and match the schema."
                        )
                    )
                    continue

            # All retries exhausted
            return self._handle_exhausted_retries(json_schema, is_pydantic_schema, is_dict_schema), total_usage

        except Exception as e:
            logger.error(f"Error generating response: {e}")
            return self._handle_error(e, json_schema, is_pydantic_schema, is_dict_schema), total_usage

    def _handle_exhausted_retries(
        self,
        json_schema: JsonSchemaType,
        is_pydantic_schema: bool,
        is_dict_schema: bool,
    ) -> BaseModel | str:
        """Handle case when all retries are exhausted.

        Args:
            json_schema: The schema that was requested
            is_pydantic_schema: True if schema is a Pydantic model class
            is_dict_schema: True if schema is a raw dict schema

        Returns:
            Default response or raises ValueError

        Raises:
            ValueError: If no valid response could be obtained
        """
        logger.error(f"Failed to get valid response after {self.MAX_RETRIES} attempts")

        if is_pydantic_schema:
            try:
                return json_schema.model_validate(  # type: ignore[union-attr]
                    {"text": "Cannot provide answer in appropriate format.", "continue_conversation": False}
                )
            except Exception:
                raise ValueError(f"Failed to get valid response from {self.provider} after {self.MAX_RETRIES} attempts")
        elif is_dict_schema:
            raise ValueError(f"Failed to get valid response from {self.provider} after {self.MAX_RETRIES} attempts")
        else:
            return ""

    def _handle_error(
        self,
        error: Exception,
        json_schema: JsonSchemaType,
        is_pydantic_schema: bool,
        is_dict_schema: bool,
    ) -> BaseModel | str:
        """Handle unexpected errors during LLM call.

        Args:
            error: The exception that occurred
            json_schema: The schema that was requested
            is_pydantic_schema: True if schema is a Pydantic model class
            is_dict_schema: True if schema is a raw dict schema

        Returns:
            Error response or re-raises exception
        """
        if is_pydantic_schema or is_dict_schema:
            # Can't create generic error response for Pydantic/dict schemas
            raise
        else:
            return f"Error: {error}"
