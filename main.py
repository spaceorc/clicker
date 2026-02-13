"""CLI entry point for the browser automation agent."""

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

import console as console_output
from agent.loop import AgentResult, run_agent
from browser.controller import BrowserController, ViewportSize
from llm_caller.factory import parse_model_spec, get_llm_caller
from session import (
    ResumeState,
    SessionState,
    build_resume_state,
    find_latest_session,
    load_session,
    save_session,
    serialize_conversation,
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Browser automation agent powered by LLM vision")
    parser.add_argument("url", nargs="?", default=None, help="Starting URL to navigate to")
    parser.add_argument("scenario", nargs="?", default=None, help="Scenario/goal to accomplish")
    parser.add_argument(
        "--model",
        default=None,
        help="LLM model in provider/model format (default: google_vertex/gemini-2.5-flash)",
    )
    parser.add_argument(
        "--fallback-model",
        default=None,
        help="Fallback to this model if primary model gets stuck or fails (default: anthropic_vertex/claude-sonnet-4-5@20250929)",
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
    parser.add_argument(
        "--resume",
        metavar="SESSION_DIR",
        default=None,
        help="Resume from a specific session directory",
    )
    parser.add_argument(
        "--resume-last",
        action="store_true",
        help="Resume the most recent in-progress session",
    )
    return parser.parse_args()


def _make_step_callback(
    session_dir: Path,
    url: str,
    scenario: str,
    model: str,
    fallback_model: str | None,
    viewport: ViewportSize,
    headless: bool,
    pause: bool,
    max_steps: int,
):
    """Create on_step_done callback that saves session state."""
    def on_step_done(state: ResumeState) -> None:
        session_state = SessionState(
            version=1,
            status="in_progress",
            url=url,
            last_url=state.last_url,
            scenario=scenario,
            model=model,
            fallback_model=fallback_model,
            viewport={"width": viewport.width, "height": viewport.height},
            headless=headless,
            pause=pause,
            max_steps=max_steps,
            step=state.step,
            elapsed_seconds=state.elapsed_seconds,
            screenshot_counts=dict(state.screenshot_counts),
            screenshot_warnings=dict(state.screenshot_warnings),
            conversation=serialize_conversation(state.conversation),
            usage={
                "input_tokens": state.usage.input_tokens,
                "output_tokens": state.usage.output_tokens,
                "cache_read_tokens": state.usage.cache_read_tokens,
                "cache_creation_tokens": state.usage.cache_creation_tokens,
            },
        )
        save_session(session_dir, session_state)
    return on_step_done


async def _run(args: argparse.Namespace) -> AgentResult:
    model_spec = args.model
    provider, model = parse_model_spec(model_spec)
    llm = get_llm_caller(provider, model)

    # Create fallback LLM if specified
    fallback_llm = None
    if args.fallback_model:
        fallback_provider, fallback_model_name = parse_model_spec(args.fallback_model)
        fallback_llm = get_llm_caller(fallback_provider, fallback_model_name)

    headless = not args.no_headless
    viewport = ViewportSize()
    browser = BrowserController(viewport=viewport, headless=headless)

    resume_state: ResumeState | None = None

    try:
        await browser.start()

        if args.resume_state:
            # Resuming — navigate to last URL
            resume_state = args.resume_state
            console_output.console.print(f"[bold cyan]Resuming from step {resume_state.step}[/bold cyan]")
            console_output.console.print(f"[bold]Navigating to:[/bold] {resume_state.last_url}")
            await browser.navigate(resume_state.last_url)
            await browser.wait(1000)
        else:
            # Fresh run — navigate to starting URL
            await browser.navigate(args.url)
            await browser.wait(1000)

        if args.pause:
            print("Browser is open. Log in manually, then press Enter to start the agent...")
            try:
                await asyncio.get_event_loop().run_in_executor(None, input)
            except KeyboardInterrupt:
                console_output.console.print("\n[yellow]Cancelled by user (Ctrl+C)[/yellow]")
                raise SystemExit(130)

        on_step_done = _make_step_callback(
            session_dir=args.run_dir,
            url=args.url,
            scenario=args.scenario,
            model=model_spec,
            fallback_model=args.fallback_model,
            viewport=viewport,
            headless=headless,
            pause=args.pause,
            max_steps=args.max_steps,
        )

        result = await run_agent(
            llm=llm,
            browser=browser,
            scenario=args.scenario,
            max_steps=args.max_steps,
            screenshots_dir=args.run_dir / "screenshots",
            on_step_done=on_step_done,
            resume=resume_state,
            fallback_llm=fallback_llm,
        )
        return result
    finally:
        try:
            await browser.stop()
        except Exception:
            # Ignore errors during browser cleanup (e.g., after Ctrl+C)
            pass


def _save_final_status(args: argparse.Namespace, result: AgentResult) -> None:
    """Save final session status (done/failed)."""
    session_file = args.run_dir / "session.json"
    if session_file.exists():
        import json
        data = json.loads(session_file.read_text(encoding="utf-8"))
        data["status"] = "done" if result.success else "failed"
        data["step"] = result.steps_taken
        data["usage"] = {
            "input_tokens": result.usage.input_tokens,
            "output_tokens": result.usage.output_tokens,
            "cache_read_tokens": result.usage.cache_read_tokens,
            "cache_creation_tokens": result.usage.cache_creation_tokens,
        }
        import tempfile, os
        fd, tmp_path = tempfile.mkstemp(dir=args.run_dir, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        Path(tmp_path).replace(session_file)


def main() -> None:
    load_dotenv()

    args = _parse_args()

    # Handle resume
    resuming = False
    session: SessionState | None = None
    session_dir: Path | None = None

    if args.resume_last:
        try:
            session_dir = find_latest_session()
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        session = load_session(session_dir)
        resuming = True
    elif args.resume:
        session_dir = Path(args.resume)
        try:
            session = load_session(session_dir)
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            sys.exit(1)
        resuming = True

    if resuming:
        assert session is not None
        assert session_dir is not None

        if session.status not in ("in_progress", "interrupted"):
            print(f"Error: Session is already '{session.status}', cannot resume", file=sys.stderr)
            sys.exit(1)

        # Use session values, allow CLI overrides
        args.url = session.url
        args.scenario = session.scenario
        args.model = args.model or session.model
        args.fallback_model = args.fallback_model or session.fallback_model or "anthropic_vertex/claude-sonnet-4-5@20250929"
        args.max_steps = args.max_steps or session.max_steps
        args.pause = args.pause or session.pause
        args.resume_state = build_resume_state(session)
        args.run_dir = session_dir
    else:
        # Validate required args for fresh run
        if not args.url or not args.scenario:
            print("Error: url and scenario are required for new runs", file=sys.stderr)
            sys.exit(1)
        args.model = args.model or "google_vertex/gemini-2.5-flash"
        args.fallback_model = args.fallback_model or "anthropic_vertex/claude-sonnet-4-5@20250929"
        args.resume_state = None
        args.run_dir = Path("sessions") / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        args.run_dir.mkdir(parents=True, exist_ok=True)

    log_format = "%(asctime)s %(levelname)-8s %(name)s — %(message)s"
    log_datefmt = "%H:%M:%S"

    # Set up logging to file only (console output via Rich)
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG)

    file_mode = "a" if resuming else "w"
    file_handler = logging.FileHandler(args.run_dir / "log.txt", mode=file_mode, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(logging.Formatter(log_format, datefmt=log_datefmt))
    root_logger.addHandler(file_handler)

    if resuming:
        logging.info("=== Session resumed ===")
        console_output.console.print(f"[bold]Resuming session:[/bold] {args.run_dir}")

    console_output.console.print(f"[bold]Scenario:[/bold] {args.scenario}")
    console_output.console.print(f"[bold]URL:[/bold] {args.url}")
    console_output.console.print(f"[bold]Model:[/bold] {args.model}")
    if hasattr(args, 'fallback_model') and args.fallback_model:
        console_output.console.print(f"[bold]Fallback:[/bold] {args.fallback_model}")
    console_output.console.print(f"[bold]Session:[/bold] {args.run_dir}")

    try:
        result = asyncio.run(_run(args))
    except KeyboardInterrupt:
        console_output.console.print("\n[yellow]Interrupted by user (Ctrl+C)[/yellow]")
        # Load last saved session state to get usage stats
        session_file = args.run_dir / "session.json"
        if session_file.exists():
            import json
            data = json.loads(session_file.read_text(encoding="utf-8"))
            data["status"] = "interrupted"
            import tempfile, os
            fd, tmp_path = tempfile.mkstemp(dir=args.run_dir, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            Path(tmp_path).replace(session_file)
            # Show final stats
            from llm_caller.base import UsageStats
            usage = UsageStats(
                input_tokens=data["usage"]["input_tokens"],
                output_tokens=data["usage"]["output_tokens"],
                cache_read_tokens=data["usage"]["cache_read_tokens"],
                cache_creation_tokens=data["usage"]["cache_creation_tokens"],
            )
            console_output.result_fail(
                "Interrupted by user",
                data["step"],
                usage,
                data["model"],
            )
        sys.exit(130)  # Standard exit code for Ctrl+C

    _save_final_status(args, result)

    if result.success:
        console_output.result_success(result.summary, result.steps_taken, result.usage, result.model, result.usage_by_model)
    else:
        console_output.result_fail(result.summary, result.steps_taken, result.usage, result.model, result.usage_by_model)
        sys.exit(1)


if __name__ == "__main__":
    main()
