# Tests

## Running tests

```bash
# Install test dependencies
uv sync --dev

# Run unit tests only (fast, no API calls)
make test

# Run integration tests (slow, makes real LLM API calls)
make test-integration

# Run all tests
uv run pytest -v

# Run specific test
uv run pytest tests/test_integration.py::test_navigate_to_wikipedia -v
```

## Test types

### Unit tests
- Fast (< 1 second)
- No external dependencies
- No API calls
- Run in CI on every commit

**TODO**: Add unit tests for:
- `llm_caller/pricing.py` - cost calculations
- `session.py` - serialization/deserialization
- `agent/actions.py` - Pydantic model validation
- Schema conversion (Gemini/OpenAI)

### Integration tests
- Slow (30-60 seconds each)
- Make real LLM API calls (~$0.01-0.05 per test)
- Require valid credentials
- Run manually or in nightly CI builds

**Current integration tests:**
- `test_navigate_to_wikipedia` - Google → Wikipedia navigation
- `test_wikipedia_direct_read` - Read Wikipedia content
- `test_simple_form_interaction` - Fill and submit HTML form
- `test_agent_handles_failure_gracefully` - Fail on impossible tasks

## Cost estimates

Integration test suite: ~$0.20 per run (4 tests × $0.05)

To minimize costs:
- Use Haiku as default test model (configured in conftest.py)
- Set low `max_steps` limits
- Use simple, predictable scenarios
