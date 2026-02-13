# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
make install          # Install deps + Playwright chromium
make run-visible URL="..." SCENARIO="..."   # Run with visible browser
make run-pause URL="..." SCENARIO="..."     # Run with pause for manual login
make resume SESSION="sessions/2026-..."     # Resume specific session
make resume-last                            # Resume most recent in-progress session
uv run python main.py <url> <scenario> [--model provider/model] [--no-headless] [--pause] [--max-steps N] [-v]
uv run python main.py --resume <session_dir> [--no-headless] [-v]
uv run python main.py --resume-last [--no-headless] [-v]
```

## Architecture

Screenshot-driven agent loop: Playwright browser takes screenshots, sends them to a vision LLM, LLM returns a structured action (click/type/scroll/drag/etc.), action is executed, repeat.

### Key packages

- **`llm_caller/`** — Abstraction over multiple LLM providers (OpenAI, Anthropic Vertex, Google Vertex). Supports multimodal messages (text + base64 images). Each provider converts `ConversationMessage` to its native API format. Uses Pydantic models for structured output via JSON schema.
- **`browser/`** — Playwright wrapper. Handles lifecycle, navigation, mouse/keyboard actions, screenshots with coordinate grid overlay (Pillow).
- **`agent/`** — Core agent logic. `actions.py` defines a Pydantic discriminated union of 9 action types. `prompts.py` builds the system prompt. `loop.py` runs the screenshot→LLM→action loop with conversation compression, stuck detection, and timeout.
- **`main.py`** — CLI entry point. Parses args, sets up logging (console + file), creates LLM caller and browser, runs agent loop.

### LLM provider pattern

All providers extend `LlmCaller` (in `base.py`) with three abstract methods: `_convert_messages`, `_do_api_call`, `_create_retry_message`. The factory (`factory.py`) parses `provider/model` strings and caches caller instances. OpenAI requires special schema handling (`oneOf` → `anyOf`, strip `discriminator`) for strict mode.
