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
	uv run python main.py "$(URL)" "$(SCENARIO)" --model "$(MODEL)" --no-headless -v

run-pause:
	uv run python main.py "$(URL)" "$(SCENARIO)" --model "$(MODEL)" --no-headless --pause -v

resume:
	uv run python main.py --resume "$(SESSION)" --no-headless -v

resume-last:
	uv run python main.py --resume-last --no-headless -v

help:
	uv run python main.py --help
