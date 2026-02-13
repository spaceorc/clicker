.PHONY: install run run-visible run-pause help

URL ?=
SCENARIO ?=
MODEL ?= openai/gpt-4o

install:
	uv sync
	uv run playwright install chromium

run:
	uv run python main.py "$(URL)" "$(SCENARIO)" --model "$(MODEL)"

run-visible:
	uv run python main.py "$(URL)" "$(SCENARIO)" --model "$(MODEL)" --no-headless -v

run-pause:
	uv run python main.py "$(URL)" "$(SCENARIO)" --model "$(MODEL)" --no-headless --pause -v

help:
	uv run python main.py --help
