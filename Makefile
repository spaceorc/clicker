.PHONY: install run run-visible run-pause resume resume-last list show cost test test-integration help

URL ?=
SCENARIO ?=
MODEL ?= anthropic_vertex/claude-haiku-5-5
SESSION ?=
DEBUG ?= 0
VERBOSE ?= 0
USER_DATA_DIR ?=
TIMEOUT ?=
LIMIT ?= 20
MATCH ?=

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

ifneq ($(TIMEOUT),)
    TIMEOUT_FLAG = --timeout $(TIMEOUT)
else
    TIMEOUT_FLAG =
endif

ifneq ($(MATCH),)
    MATCH_FLAG = --match "$(MATCH)"
else
    MATCH_FLAG =
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
	uv run python main.py $(VERBOSE_FLAG) run "$(URL)" "$(SCENARIO)" --model "$(MODEL)" $(SESSION_FLAG) $(USER_DATA_FLAG) $(TIMEOUT_FLAG)

run-visible:
	uv run python main.py $(VERBOSE_FLAG) run "$(URL)" "$(SCENARIO)" --model "$(MODEL)" --no-headless $(SESSION_FLAG) $(USER_DATA_FLAG) $(TIMEOUT_FLAG)

run-pause:
	uv run python main.py $(VERBOSE_FLAG) run "$(URL)" "$(SCENARIO)" --model "$(MODEL)" --no-headless --pause $(SESSION_FLAG) $(USER_DATA_FLAG) $(TIMEOUT_FLAG)

resume:
	uv run python main.py $(VERBOSE_FLAG) resume "$(SESSION)" --no-headless $(TIMEOUT_FLAG)

resume-last:
	uv run python main.py $(VERBOSE_FLAG) resume --last --no-headless $(TIMEOUT_FLAG)

list:
	uv run python main.py list

show:
	uv run python main.py show "$(SESSION)"

cost:
	uv run python main.py cost --limit $(LIMIT) $(MATCH_FLAG)

test:
	uv run pytest -m "not integration" -v -n auto

test-integration:
	uv run pytest -m integration -v -n auto

help:
	uv run python main.py --help
