# Clicker

LLM-driven browser automation agent. Takes a URL and a goal, then autonomously navigates the page — clicking buttons, filling forms, scrolling, dragging elements — until the goal is achieved.

The agent works by repeatedly taking screenshots, sending them to a vision-capable LLM, and executing whatever action the model decides on.

## How it works

```
┌──────────────┐     screenshot      ┌───────────┐
│  Playwright  │ ──────────────────► │  Vision   │
│   Browser    │                     │   LLM     │
│              │ ◄────────────────── │           │
└──────────────┘  click/type/scroll  └───────────┘
       │                                   │
       └───── repeat until done ───────────┘
```

1. Opens the target URL in a Playwright-controlled Chromium browser
2. Takes a screenshot with a coordinate grid overlay (for precise click targeting)
3. Sends the screenshot + conversation history to the LLM
4. LLM responds with an observation, reasoning, and an action (click, type, scroll, drag, etc.)
5. Action is executed in the browser
6. Repeat until the LLM reports success or failure

## Setup

```bash
# Install dependencies
make install

# Configure credentials
cp .env.example .env
# Edit .env with your API keys
```

## Usage

```bash
# Basic (headless)
uv run python main.py "https://example.com" "Click the 'More information' link"

# Visible browser + verbose logging
make run-visible URL="https://example.com" SCENARIO="Click the 'More information' link"

# With manual login pause (for sites requiring authentication)
make run-pause URL="https://myapp.com" SCENARIO="Navigate to settings and change language to English"

# Using a specific model
uv run python main.py "https://example.com" "Click the link" --model anthropic_vertex/claude-sonnet-4-5-20250514
```

### CLI options

| Flag | Description |
|------|-------------|
| `--model provider/model` | LLM to use (default: `openai/gpt-4o`) |
| `--no-headless` | Show the browser window |
| `--pause` | Pause after page load for manual login, press Enter to start |
| `--max-steps N` | Limit agent steps (default: 0 = unlimited) |
| `-v` | Verbose (DEBUG) console logging |

### Supported LLM providers

| Provider | Model spec example |
|----------|-------------------|
| OpenAI | `openai/gpt-4o` |
| Anthropic (via Vertex AI) | `anthropic_vertex/claude-sonnet-4-5-20250514` |
| Google Gemini (via Vertex AI) | `google_vertex/gemini-2.0-flash` |

## Logs & screenshots

Each run creates a directory under `logs/`:

```
logs/
  2026-02-13_14-43-15/
    log.txt                 # Full debug log
    screenshots/
      step_001.png          # Screenshot with coordinate grid
      step_002.png
      ...
```

## Available actions

The LLM can choose from these actions at each step:

- **click** / **double_click** — click at (x, y) coordinates
- **type** — type text into the focused element
- **press_key** — press a keyboard key (Enter, Tab, Escape, etc.)
- **scroll** — scroll at a position with delta
- **drag** — drag and drop between two coordinates
- **wait** — wait for a specified duration
- **done** — report success
- **fail** — report failure

## Safety features

- **Stuck detection** — if the same screenshot appears 5+ times, the agent gets escalating warnings. After 3 warnings on the same screen, it's force-stopped.
- **Conversation compression** — when context grows beyond 50 messages, older messages are compressed into a summary to stay within LLM context limits.
- **Global timeout** — 30-minute hard limit per run.
