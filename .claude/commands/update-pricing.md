# Update Pricing

Update the LLM pricing table in `llm_caller/pricing.py` with current pricing from the web.

## Instructions

You are updating the hardcoded pricing table for LLM models used by this project.

### Steps to follow

1. **Read current pricing table**: Read `llm_caller/pricing.py` to see the existing `PRICING` dict and all currently tracked models.

2. **Determine which models to update**:
   - If the user provided arguments (e.g., `/update-pricing ALL versions of Gemini`), search for pricing for those specific models PLUS all existing models in the table.
   - If no arguments were provided, just refresh pricing for all existing models in the table.

3. **Web search for current pricing**: Use WebSearch to find the most up-to-date pricing (as of 2026-02-13) for:
   - All models currently in the PRICING dict
   - Any additional models the user requested in their arguments
   - Search for official pricing pages from Anthropic, OpenAI, Google, etc.

4. **Update the pricing table**:
   - Update `PRICING` dict entries with the latest pricing you found
   - Add new entries for any models the user requested (e.g., if they said "ALL versions of Gemini", add all Gemini model variants you found pricing for)
   - Remove entries for deprecated/discontinued models if appropriate
   - Update the "Last updated" date to today's date (2026-02-13)
   - **IMPORTANT**: Keep keys sorted by length descending (longest first) to ensure correct substring matching. For example, `"gpt-4o-mini"` must come before `"gpt-4o"`.

5. **Verify the changes**: After updating, briefly summarize what was changed (which models were updated, which were added, which were removed).

## Important notes

- Pricing is in dollars per 1 million tokens
- `cache_read` and `cache_creation` should be set to 0 for models that don't support prompt caching (e.g., OpenAI models as of early 2026)
- The model matching uses substring matching, so keys should be specific enough to avoid false matches but general enough to match model version suffixes (e.g., `"claude-sonnet-4-5"` will match `"claude-sonnet-4-5@20250929"`)
- Always prioritize official pricing pages from the model providers
