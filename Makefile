.PHONY: install run run-visible run-pause resume resume-last list show test test-integration help

URL ?=
SCENARIO ?=
MODEL ?= anthropic_vertex/claude-haiku-4-5@20251001
SESSION ?=
DEBUG ?= 0
VERBOSE ?= 0
USER_DATA_DIR ?=

ifneq ($(filter 1,$(DEBUG) $(VERBOSE)),)
    VERBOSE_FLAG = -v
else
    VERBOSE_FLAG =
endif

ifneq ($(USER_DATA_DIR),)
    USER_DATA_FLAG = --user-data-dir "$(USER_DATA_DIR)"
else
    USER_DATA_FLAG =
endif

ifneq ($(SESSION),)
    SESSION_FLAG = --session "$(SESSION)"
else
    SESSION_FLAG =
endif

install:
	uv sync
	uv run playwright install chromium

run:
	uv run python main.py $(VERBOSE_FLAG) run "$(URL)" "$(SCENARIO)" --model "$(MODEL)" $(SESSION_FLAG) $(USER_DATA_FLAG)

run-visible:
	uv run python main.py $(VERBOSE_FLAG) run "$(URL)" "$(SCENARIO)" --model "$(MODEL)" --no-headless $(SESSION_FLAG) $(USER_DATA_FLAG)

run-pause:
	uv run python main.py $(VERBOSE_FLAG) run "$(URL)" "$(SCENARIO)" --model "$(MODEL)" --no-headless --pause $(SESSION_FLAG) $(USER_DATA_FLAG)

resume:
	uv run python main.py $(VERBOSE_FLAG) resume "$(SESSION)" --no-headless

resume-last:
	uv run python main.py $(VERBOSE_FLAG) resume --last --no-headless

list:
	uv run python main.py list

show:
	uv run python main.py show "$(SESSION)"

test:
	uv run pytest -m "not integration" -v -n auto

test-integration:
	uv run pytest -m integration -v -n auto

help:
	uv run python main.py --help
