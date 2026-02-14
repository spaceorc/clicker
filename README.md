# Clicker

[![Tests](https://github.com/spaceorc/clicker/actions/workflows/test.yml/badge.svg?branch=master)](https://github.com/spaceorc/clicker/actions/workflows/test.yml)

LLM-driven browser automation agent. Takes a URL and a goal, then autonomously navigates the page — clicking buttons, filling forms, scrolling, dragging elements — until the goal is achieved.

The agent works by repeatedly taking screenshots, sending them to a vision-capable LLM, and executing whatever action the model decides on. It features intelligent model switching, starting with cheap models (Haiku/Gemini) and automatically upgrading to expensive models (Sonnet) when needed.

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

# Using specific models (primary + fallback)
uv run python main.py "https://example.com" "Click the link" \
  --model anthropic_vertex/claude-haiku-4-5@20251001 \
  --fallback-model anthropic_vertex/claude-sonnet-4-5@20250929

# Named session (custom session name instead of timestamp)
make run URL="https://example.com" SCENARIO="Complete task" SESSION="my-experiment"
# → Creates sessions/my-experiment/

# Persistent sessions (save cookies between runs)
make run-pause URL="https://myapp.com" SCENARIO="Login and navigate" USER_DATA_DIR="./my-profile"
# After manual login, cookies are saved to ./my-profile/
# Future runs use the same profile (no re-login needed):
make run URL="https://myapp.com" SCENARIO="Check dashboard" USER_DATA_DIR="./my-profile"

# Resume a session (after crash or Ctrl+C)
make resume-last                          # Resume last session
make resume SESSION="2026-02-13_14-30-00" # Resume specific session by name
make resume SESSION="my-experiment"       # Resume named session
```

### CLI options

| Flag | Description |
|------|-------------|
| `--model provider/model` | Primary LLM to use (default: `anthropic_vertex/claude-haiku-4-5@20251001`) |
| `--fallback-model provider/model` | Fallback LLM for stuck situations or critical tasks (default: `anthropic_vertex/claude-sonnet-4-5@20250929`) |
| `--session SESSION` | Session name or path. If exists, resumes it. If not, creates new session with this name. |
| `--last-session` | Resume the last session (from `sessions/.last_session`) |
| `--no-headless` | Show the browser window |
| `--pause` | Pause after page load for manual login, press Enter to start |
| `--max-steps N` | Limit agent steps (default: 0 = unlimited) |
| `--user-data-dir DIR` | Browser profile directory (preserves cookies/sessions between runs) |
| `-v` | Verbose (DEBUG) console logging |

**Note:** See [docs/PERSISTENT_SESSION.md](docs/PERSISTENT_SESSION.md) for detailed guide on using persistent browser profiles.

### Supported LLM providers

| Provider | Model spec example | Cost (input/output per 1M tokens) |
|----------|-------------------|----------------------------------|
| Anthropic (via Vertex AI) | `anthropic_vertex/claude-haiku-4-5@20251001` | $1 / $5 |
| Anthropic (via Vertex AI) | `anthropic_vertex/claude-sonnet-4-5@20250929` | $3 / $15 |
| Google Gemini (via Vertex AI) | `google_vertex/gemini-2.5-flash-lite` | $0.10 / $0.40 |
| Google Gemini (via Vertex AI) | `google_vertex/gemini-2.5-flash` | $0.30 / $1.20 |
| OpenAI | `openai/gpt-4o` | $2.50 / $10 |

**Recommended setup for cost optimization:**
- Primary: `anthropic_vertex/claude-haiku-4-5@20251001` (cheap, good quality)
- Fallback: `anthropic_vertex/claude-sonnet-4-5@20250929` (expensive, excellent reasoning)

This configuration starts cheap and only uses expensive models when truly needed.

## Session persistence

Each run creates a directory under `sessions/`:

```
sessions/
  2026-02-13_14-43-15/
    log.txt                 # Full debug log
    session.json            # Session state (for resume)
    screenshots/
      step_001.png          # Screenshot with coordinate grid
      step_002.png
      ...
```

Sessions can be resumed after crashes or interruption (Ctrl+C) using `--resume-last` or `--resume <path>`.

## Model switching behavior

### Automatic fallback (stuck detection)
When the same screenshot appears 5+ times, the system:
1. Issues first warning → switches to fallback model
2. Compresses old conversation history using LLM summarization
3. Continues with fallback model trying to get unstuck
4. Switches back to primary model when screenshot changes (progress made)

### Smart mode (critical tasks)
The model can request permanent upgrade to the expensive model by setting `request_smart_model: true`. Use cases:
- Answering test questions or solving complex problems (math, logic, comprehension)
- After multiple failures requiring better reasoning
- Deep understanding tasks (quiz content, complex forms)
- When test progress indicators are visible ("Question 5 of 20", "75% complete")

Once smart mode is activated, the session permanently uses the expensive model and won't auto-switch back.

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

## Smart features

- **Intelligent model switching** — Starts with cheap models (Haiku $1/$5, Gemini $0.10-$0.40 per 1M tokens). Automatically switches to expensive model (Sonnet $3/$15) when:
  - Agent gets stuck (same screenshot 5+ times)
  - Model requests upgrade for critical tasks (test questions, complex reasoning)
  - Automatically switches back to cheap model when unstuck (unless smart mode was explicitly requested)
- **Cost tracking** — Real-time token usage and cost estimates displayed per step and in final summary, with per-model breakdown when multiple models are used
- **Session persistence** — Sessions are saved after each step and can be resumed after crashes or interruption
- **Stuck detection** — If the same screenshot appears 5+ times, the agent gets escalating warnings. After 3 warnings on the same screen, it's force-stopped.
- **Conversation compression** — When context grows beyond 150 messages (or during model switch), older messages are summarized by the LLM to stay within context limits
- **Global timeout** — 30-minute hard limit per run
- **Prompt caching** — Anthropic models use prompt caching to reduce costs (10% read cost, 1.25x write cost)

## Testing

```bash
# Install test dependencies
uv sync --dev

# Run unit tests only (fast, no API calls)
make test

# Run integration tests (slow, makes real LLM API calls, ~$0.20)
make test-integration
```

See [tests/README.md](tests/README.md) for more details on the test suite.
