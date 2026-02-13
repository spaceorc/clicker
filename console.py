"""Rich console output for clean, user-friendly step-by-step display."""

from rich.console import Console
from rich.panel import Panel

from llm_caller import UsageStats

console = Console()


def step_start(step: int) -> None:
    """Print step header."""
    console.print(f"\n[bold white]Step {step}[/bold white]")


def step_action(next_step: str, action_repr: str, reasoning: str) -> None:
    """Print agent's reasoning, next_step description and the action."""
    console.print(f"  [dim]{reasoning}[/dim]")
    console.print(f"  [bold green]{next_step}[/bold green]")
    console.print(f"  [white]{action_repr}[/white]")


def step_warning(message: str) -> None:
    console.print(f"  [bold yellow]⚠ {message}[/bold yellow]")


def step_usage(usage: UsageStats) -> None:
    """Print compact per-step token usage."""
    parts = [f"{usage.input_tokens} in", f"{usage.output_tokens} out"]
    cache_parts = []
    if usage.cache_read_tokens:
        cache_parts.append(f"{usage.cache_read_tokens} read")
    if usage.cache_creation_tokens:
        cache_parts.append(f"{usage.cache_creation_tokens} write")
    if cache_parts:
        parts.append(f"cache: {', '.join(cache_parts)}")
    console.print(f"  [dim]{' / '.join(parts)}[/dim]")


def _format_usage(usage: UsageStats) -> str:
    """Format usage stats for display in result panels."""
    parts = [f"{usage.input_tokens} in", f"{usage.output_tokens} out"]
    cache_parts = []
    if usage.cache_read_tokens:
        cache_parts.append(f"{usage.cache_read_tokens} read")
    if usage.cache_creation_tokens:
        cache_parts.append(f"{usage.cache_creation_tokens} write")
    if cache_parts:
        parts.append(f"cache: {', '.join(cache_parts)}")
    return ' / '.join(parts)


def result_success(summary: str, steps: int, usage: UsageStats | None = None) -> None:
    usage_line = f"\n[dim]tokens: {_format_usage(usage)}[/dim]" if usage else ""
    console.print(Panel(f"{summary}\n[dim]{steps} steps[/dim]{usage_line}", title="Done", border_style="green"))


def result_fail(summary: str, steps: int, usage: UsageStats | None = None) -> None:
    usage_line = f"\n[dim]tokens: {_format_usage(usage)}[/dim]" if usage else ""
    console.print(Panel(f"{summary}\n[dim]{steps} steps[/dim]{usage_line}", title="Failed", border_style="red"))
