"""Integration tests for the browser automation agent.

These tests run the full agent loop with real LLM API calls and browser automation.
They are slow and expensive, so mark them with @pytest.mark.integration.

Run with: pytest -m integration
Skip with: pytest -m "not integration"
"""

import pytest

from agent.loop import run_agent


@pytest.mark.integration
async def test_wikipedia_search(browser, llm, temp_screenshots_dir):
    """Agent can use Wikipedia search to find an article."""
    await browser.navigate("https://en.wikipedia.org")

    result = await run_agent(
        llm=llm,
        browser=browser,
        scenario="Use the search box to find the article about 'Python programming language'",
        max_steps=10,
        screenshots_dir=temp_screenshots_dir,
    )

    assert result.success, f"Agent failed: {result.summary}"
    assert "python" in result.final_url.lower(), \
        f"Expected Python-related URL, got: {result.final_url}"
    assert result.steps_taken <= 10, f"Too many steps: {result.steps_taken}"


@pytest.mark.integration
async def test_simple_form_interaction(browser, llm, temp_screenshots_dir):
    """Agent can interact with a simple HTML form."""
    # Create a simple test page
    html_content = """
    <!DOCTYPE html>
    <html>
    <head><title>Test Form</title></head>
    <body>
        <h1>Simple Test Form</h1>
        <input id="name-input" type="text" placeholder="Enter your name" />
        <button id="submit-btn" onclick="document.getElementById('result').innerText = 'Hello, ' + document.getElementById('name-input').value">Submit</button>
        <div id="result"></div>
    </body>
    </html>
    """

    # Save HTML to temp file and navigate
    html_file = temp_screenshots_dir.parent / "test_form.html"
    html_file.write_text(html_content)
    await browser.navigate(f"file://{html_file}")

    result = await run_agent(
        llm=llm,
        browser=browser,
        scenario="Type 'Alice' in the input field and click the Submit button",
        max_steps=5,
        screenshots_dir=temp_screenshots_dir,
    )

    assert result.success, f"Agent failed: {result.summary}"


@pytest.mark.integration
async def test_wikipedia_article_exists(browser, llm, temp_screenshots_dir):
    """Agent can verify an article exists on Wikipedia."""
    await browser.navigate("https://en.wikipedia.org")

    result = await run_agent(
        llm=llm,
        browser=browser,
        scenario="Search for 'Albert Einstein' and tell me if there is an article about him",
        max_steps=8,
        screenshots_dir=temp_screenshots_dir,
    )

    assert result.success, f"Agent failed: {result.summary}"
    # Check that the agent found Einstein's article
    assert ("einstein" in result.final_url.lower() or "yes" in result.summary.lower() or "found" in result.summary.lower()), \
        f"Expected confirmation of Einstein article, got: {result.summary}"
