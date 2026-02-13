.PHONY: install run run-visible run-pause resume resume-last test test-integration help

URL ?=
SCENARIO ?=
MODEL ?= anthropic_vertex/claude-haiku-4-5@20251001
SESSION ?=
DEBUG ?= 0
VERBOSE ?= 0

ifneq ($(filter 1,$(DEBUG) $(VERBOSE)),)
    VERBOSE_FLAG = -v
else
    VERBOSE_FLAG =
endif

install:
	uv sync
	uv run playwright install chromium

run:
	uv run python main.py "$(URL)" "$(SCENARIO)" --model "$(MODEL)" $(VERBOSE_FLAG)

run-visible:
	uv run python main.py "$(URL)" "$(SCENARIO)" --model "$(MODEL)" --no-headless $(VERBOSE_FLAG)

run-pause:
	uv run python main.py "$(URL)" "$(SCENARIO)" --model "$(MODEL)" --no-headless --pause $(VERBOSE_FLAG)

resume:
	uv run python main.py --resume "$(SESSION)" --no-headless $(VERBOSE_FLAG)

resume-last:
	uv run python main.py --resume-last --no-headless $(VERBOSE_FLAG)

test:
	uv run pytest -m "not integration" -v

test-integration:
	uv run pytest -m integration -v

help:
	uv run python main.py --help
