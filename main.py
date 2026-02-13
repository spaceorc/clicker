"""CLI entry point for the browser automation agent."""

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

from agent.loop import AgentResult, run_agent
from browser.controller import BrowserController, ViewportSize
from llm_caller.factory import parse_model_spec, get_llm_caller


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Browser automation agent powered by LLM vision")
    parser.add_argument("url", help="Starting URL to navigate to")
    parser.add_argument("scenario", help="Scenario/goal to accomplish")
    parser.add_argument(
        "--model",
        default="openai/gpt-4o",
        help="LLM model in provider/model format (default: openai/gpt-4o)",
    )
    parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run browser in visible (non-headless) mode",
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=0,
        help="Maximum number of agent steps (default: 0 = unlimited)",
    )
    parser.add_argument(
        "--pause",
        action="store_true",
        help="Pause after opening the page so you can log in manually, then press Enter to start the agent",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging",
    )
    return parser.parse_args()


async def _run(args: argparse.Namespace) -> AgentResult:
    provider, model = parse_model_spec(args.model)
    llm = get_llm_caller(provider, model)

    headless = not args.no_headless
    browser = BrowserController(viewport=ViewportSize(), headless=headless)

    try:
        await browser.start()
        await browser.navigate(args.url)
        await browser.wait(1000)

        if args.pause:
            print("Browser is open. Log in manually, then press Enter to start the agent...")
            await asyncio.get_event_loop().run_in_executor(None, input)

        result = await run_agent(
            llm=llm,
            browser=browser,
            scenario=args.scenario,
            max_steps=args.max_steps,
            screenshots_dir=args.run_dir / "screenshots",
        )
        return result
    finally:
        await browser.stop()


def main() -> None:
    load_dotenv()

    args = _parse_args()

    log_level = logging.DEBUG if args.verbose else logging.INFO
    log_format = "%(asctime)s %(levelname)-8s %(name)s — %(message)s"
    log_datefmt = "%H:%M:%S"

    # Set up logging to both console and file
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    console_handler = logging.StreamHandler()
    console_handler.setLevel(log_level)
    console_handler.setFormatter(logging.Formatter(log_format, datefmt=log_datefmt))
    root_logger.addHandler(console_handler)

    run_dir = Path("logs") / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    run_dir.mkdir(parents=True, exist_ok=True)

    file_handler = logging.FileHandler(run_dir / "log.txt", mode="w", encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(log_format, datefmt=log_datefmt))
    root_logger.addHandler(file_handler)

    args.run_dir = run_dir
    result = asyncio.run(_run(args))

    if result.success:
        print(f"\nSUCCESS ({result.steps_taken} steps): {result.summary}")
    else:
        print(f"\nFAILED ({result.steps_taken} steps): {result.summary}")
        sys.exit(1)


if __name__ == "__main__":
    main()
