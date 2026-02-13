.PHONY: install run run-visible run-pause resume resume-last help

URL ?=
SCENARIO ?=
MODEL ?= anthropic_vertex/claude-haiku-4-5@20251001
SESSION ?=

install:
	uv sync
	uv run playwright install chromium

run:
	uv run python main.py "$(URL)" "$(SCENARIO)" --model "$(MODEL)"

run-visible:
	uv run python main.py "$(URL)" "$(SCENARIO)" --model "$(MODEL)" --no-headless

run-pause:
	uv run python main.py "$(URL)" "$(SCENARIO)" --model "$(MODEL)" --no-headless --pause

resume:
	uv run python main.py --resume "$(SESSION)" --no-headless

resume-last:
	uv run python main.py --resume-last --no-headless

help:
	uv run python main.py --help
