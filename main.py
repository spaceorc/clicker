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
    get_sessions_dir,
    load_last_session,
    load_session,
    save_last_session,
    save_session,
    serialize_conversation,
)
from llm_caller.base import UsageStats


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Browser automation agent powered by LLM vision",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose (DEBUG) logging",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # === RUN command ===
    run_parser = subparsers.add_parser("run", help="Start browser automation task")
    run_parser.add_argument("url", help="Starting URL to navigate to")
    run_parser.add_argument("scenario", help="Scenario/goal to accomplish")
    run_parser.add_argument(
        "--model",
        default="anthropic_vertex/claude-haiku-4-5@20251001",
        help="LLM model in provider/model format (default: anthropic_vertex/claude-haiku-4-5@20251001)",
    )
    run_parser.add_argument(
        "--fallback-model",
        default="anthropic_vertex/claude-sonnet-4-5@20250929",
        help="Fallback to this model if primary model gets stuck or fails (default: anthropic_vertex/claude-sonnet-4-5@20250929)",
    )
    run_parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run browser in visible (non-headless) mode",
    )
    run_parser.add_argument(
        "--max-steps",
        type=int,
        default=0,
        help="Maximum number of agent steps (default: 0 = unlimited)",
    )
    run_parser.add_argument(
        "--pause",
        action="store_true",
        help="Pause after opening the page so you can log in manually, then press Enter to start the agent",
    )
    run_parser.add_argument(
        "--session",
        metavar="NAME",
        default=None,
        help="Named session (saved in sessions/<name>). If exists, resumes it. If not, creates new session with this name.",
    )
    run_parser.add_argument(
        "--user-data-dir",
        metavar="DIR",
        default=None,
        help="Directory to store browser profile data (cookies, sessions, etc.). Using this preserves login state between runs.",
    )

    # === RESUME command ===
    resume_parser = subparsers.add_parser("resume", help="Resume a session")
    resume_group = resume_parser.add_mutually_exclusive_group(required=True)
    resume_group.add_argument("session_id", nargs="?", default=None, help="Session ID or path to resume")
    resume_group.add_argument("--last", action="store_true", help="Resume the last session")
    resume_parser.add_argument(
        "--no-headless",
        action="store_true",
        help="Run browser in visible (non-headless) mode",
    )

    # === LIST command ===
    list_parser = subparsers.add_parser("list", help="List all sessions")

    # === SHOW command ===
    show_parser = subparsers.add_parser("show", help="Show session details")
    show_group = show_parser.add_mutually_exclusive_group(required=True)
    show_group.add_argument("session_id", nargs="?", default=None, help="Session ID or path to show")
    show_group.add_argument("--last", action="store_true", help="Show the last session")
    show_parser.add_argument(
        "--full",
        action="store_true",
        help="Show full conversation history",
    )

    args = parser.parse_args()

    # If no command specified, show help
    if args.command is None:
        parser.print_help()
        sys.exit(0)

    return args


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
    user_data_dir: str | None,
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
            use_smart_model=state.use_smart_model,
            user_data_dir=user_data_dir,
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
    browser = BrowserController(viewport=viewport, headless=headless, user_data_dir=args.user_data_dir)

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
            user_data_dir=args.user_data_dir,
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


def _cmd_list() -> None:
    """List all sessions with summary info."""
    from rich.table import Table

    sessions_dir = get_sessions_dir()
    if not sessions_dir.exists():
        console_output.console.print("[yellow]No sessions found[/yellow]")
        return

    # Collect all sessions
    sessions = []
    for session_dir in sorted(sessions_dir.iterdir(), reverse=True):
        session_file = session_dir / "session.json"
        if not session_file.exists():
            continue
        try:
            session = load_session(session_dir)
            sessions.append((session_dir.name, session))
        except Exception:
            continue

    if not sessions:
        console_output.console.print("[yellow]No sessions found[/yellow]")
        return

    # Build table
    table = Table(title="Sessions")
    table.add_column("Session ID", style="cyan", no_wrap=True)
    table.add_column("Status", style="white")
    table.add_column("Steps", justify="right", style="white")
    table.add_column("Scenario", style="bright_white")
    table.add_column("URL", style="dim")

    for session_id, session in sessions:
        # Status with color
        status_colors = {
            "done": "green",
            "failed": "red",
            "in_progress": "yellow",
            "interrupted": "yellow",
        }
        status_color = status_colors.get(session.status, "white")
        status_text = f"[{status_color}]{session.status}[/{status_color}]"

        table.add_row(
            session_id,
            status_text,
            str(session.step),
            session.scenario[:50] + ("..." if len(session.scenario) > 50 else ""),
            session.url[:50] + ("..." if len(session.url) > 50 else ""),
        )

    console_output.console.print(table)


def _cmd_show(session_id: str | None, use_last: bool, full: bool) -> None:
    """Show detailed session info."""
    # Resolve session
    if use_last:
        try:
            session_dir = load_last_session()
        except FileNotFoundError as e:
            console_output.console.print(f"[red]Error: {e}[/red]")
            sys.exit(1)
    else:
        session_dir = Path(session_id)
        if not session_dir.is_absolute():
            session_dir = get_sessions_dir() / session_dir

    # Load session
    try:
        session = load_session(session_dir)
    except FileNotFoundError as e:
        console_output.console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

    # Format status with color
    status_colors = {
        "done": "green",
        "failed": "red",
        "in_progress": "yellow",
        "interrupted": "yellow",
    }
    status_color = status_colors.get(session.status, "white")
    status_text = f"[{status_color}]{session.status}[/{status_color}]"

    # Calculate cost
    usage = session.usage
    from llm_caller.pricing import estimate_cost
    total_cost = estimate_cost(session.model, UsageStats(
        input_tokens=usage.get("input_tokens", 0),
        output_tokens=usage.get("output_tokens", 0),
        cache_read_tokens=usage.get("cache_read_tokens", 0),
        cache_creation_tokens=usage.get("cache_creation_tokens", 0),
    ))
    cost_str = f" (~${total_cost:.3f})" if total_cost is not None else ""

    # Print summary
    console_output.console.print(f"\n[bold]Session:[/bold] {session_dir.name}")
    console_output.console.print(f"[bold]Status:[/bold] {status_text}")
    console_output.console.print(f"[bold]Scenario:[/bold] {session.scenario}")
    console_output.console.print(f"[bold]URL:[/bold] {session.url}")
    if session.last_url != session.url:
        console_output.console.print(f"[bold]Last URL:[/bold] {session.last_url}")

    console_output.console.print(f"\n[bold]Configuration:[/bold]")
    console_output.console.print(f"  Model: {session.model}")
    if session.fallback_model:
        console_output.console.print(f"  Fallback: {session.fallback_model}")
    console_output.console.print(f"  Viewport: {session.viewport['width']}x{session.viewport['height']}")
    console_output.console.print(f"  Headless: {session.headless}")

    console_output.console.print(f"\n[bold]Progress:[/bold]")
    console_output.console.print(f"  Steps: {session.step}")
    console_output.console.print(f"  Duration: {session.elapsed_seconds:.1f}s")

    console_output.console.print(f"\n[bold]Usage:[/bold]")
    console_output.console.print(f"  Input: {usage.get('input_tokens', 0):,} tokens")
    console_output.console.print(f"  Output: {usage.get('output_tokens', 0):,} tokens")
    if usage.get('cache_read_tokens'):
        console_output.console.print(f"  Cache read: {usage.get('cache_read_tokens', 0):,} tokens")
    if usage.get('cache_creation_tokens'):
        console_output.console.print(f"  Cache creation: {usage.get('cache_creation_tokens', 0):,} tokens")
    console_output.console.print(f"  [bold yellow]Total cost:{cost_str}[/bold yellow]")

    # Show conversation
    console_output.console.print(f"\n[bold]Conversation:[/bold] ({len(session.conversation)} messages)")

    if full:
        # Show full conversation
        for i, msg in enumerate(session.conversation, 1):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            role_color = "cyan" if role == "user" else "green"
            console_output.console.print(f"\n[{role_color}]{'='*60}[/{role_color}]")
            console_output.console.print(f"[{role_color}]{role.upper()} (message {i})[/{role_color}]")
            console_output.console.print(f"[{role_color}]{'='*60}[/{role_color}]")
            console_output.console.print(content)
    else:
        # Show preview (first 3 and last 2 messages)
        preview_count = min(5, len(session.conversation))
        for i, msg in enumerate(session.conversation[:preview_count], 1):
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            # Truncate long messages
            if len(content) > 200:
                content = content[:200] + "..."
            role_color = "cyan" if role == "user" else "green"
            console_output.console.print(f"  [{role_color}]{role}:[/{role_color}] {content}")

        if len(session.conversation) > preview_count:
            console_output.console.print(f"  [dim]... ({len(session.conversation) - preview_count} more messages)[/dim]")
            console_output.console.print(f"  [dim]Use --full to see complete conversation[/dim]")


def _load_config() -> Path | None:
    """Load environment variables from standard config locations.

    Searches in order:
    1. ~/.clicker/config.env
    2. ~/.config/clicker/config.env
    3. ./.env (current directory)

    Returns:
        Path to the loaded config file, or None if not found
    """
    config_paths = [
        Path.home() / ".clicker" / "config.env",
        Path.home() / ".config" / "clicker" / "config.env",
        Path.cwd() / ".env",
    ]

    for config_path in config_paths:
        if config_path.exists():
            load_dotenv(config_path)
            return config_path

    return None


def main() -> None:
    _load_config()
    args = _parse_args()

    # Handle different commands
    if args.command == "list":
        _cmd_list()
        return

    if args.command == "show":
        _cmd_show(args.session_id, args.last, args.full)
        return

    # RUN or RESUME command - need to run the agent
    resuming = False
    session: SessionState | None = None
    session_dir: Path | None = None

    if args.command == "resume":
        # Resume command
        if args.last:
            # Resume last session
            try:
                session_dir = load_last_session()
            except FileNotFoundError as e:
                console_output.console.print(f"[red]Error: {e}[/red]")
                sys.exit(1)
        else:
            # Resume specific session
            session_dir = Path(args.session_id)
            if not session_dir.is_absolute():
                session_dir = get_sessions_dir() / session_dir

        try:
            session = load_session(session_dir)
        except FileNotFoundError as e:
            console_output.console.print(f"[red]Error: {e}[/red]")
            sys.exit(1)

        if session.status not in ("in_progress", "interrupted"):
            console_output.console.print(f"[red]Error: Session is already '{session.status}', cannot resume[/red]")
            sys.exit(1)

        resuming = True

    elif args.command == "run":
        # Run command
        if args.session:
            # Named session - check if it exists
            session_dir = Path(args.session)
            if not session_dir.is_absolute():
                session_dir = get_sessions_dir() / session_dir

            session_file = session_dir / "session.json"
            if session_file.exists():
                # Session exists → resume it
                try:
                    session = load_session(session_dir)
                except (FileNotFoundError, ValueError) as e:
                    console_output.console.print(f"[red]Error loading session: {e}[/red]")
                    sys.exit(1)

                if session.status not in ("in_progress", "interrupted"):
                    console_output.console.print(f"[red]Error: Session '{args.session}' is already '{session.status}', cannot resume[/red]")
                    sys.exit(1)

                resuming = True
            # else: create new session with this name
        else:
            # No session name → create timestamped session
            session_dir = get_sessions_dir() / datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    # Prepare args for agent run
    if resuming:
        assert session is not None
        assert session_dir is not None

        # Use session values, allow CLI overrides
        args.url = session.url
        args.scenario = session.scenario
        args.model = session.model
        args.fallback_model = session.fallback_model or "anthropic_vertex/claude-sonnet-4-5@20250929"
        args.max_steps = session.max_steps
        args.pause = session.pause
        args.user_data_dir = session.user_data_dir
        args.resume_state = build_resume_state(session)
        args.run_dir = session_dir
    else:
        # New session
        args.resume_state = None
        args.run_dir = session_dir
        args.run_dir.mkdir(parents=True, exist_ok=True)
        # defaults are already set in argparse

    # Save this as the last session
    save_last_session(args.run_dir)

    log_format = "%(asctime)s %(levelname)-8s %(name)s — %(message)s"
    log_datefmt = "%H:%M:%S"

    # Set up logging to file only (console output via Rich)
    # Use DEBUG level only if -v flag is passed
    log_level = logging.DEBUG if args.verbose else logging.INFO
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    file_mode = "a" if resuming else "w"
    file_handler = logging.FileHandler(args.run_dir / "log.txt", mode=file_mode, encoding="utf-8")
    file_handler.setLevel(log_level)
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
    except Exception as e:
        # Log full stack trace to file
        logging.exception("Fatal error")
        # Print only error message to console
        console_output.console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)

    _save_final_status(args, result)

    if result.success:
        console_output.result_success(result.summary, result.steps_taken, result.usage, result.model, result.usage_by_model)
    else:
        console_output.result_fail(result.summary, result.steps_taken, result.usage, result.model, result.usage_by_model)
        sys.exit(1)


if __name__ == "__main__":
    main()
