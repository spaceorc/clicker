"""Rich console output for clean, user-friendly step-by-step display."""

from rich.console import Console
from rich.panel import Panel

from llm_caller import UsageStats
from llm_caller.pricing import estimate_cost

console = Console()


def _format_cost(cost: float | None, bright: bool = False) -> str:
    """Format cost as a parenthetical string, or empty if None."""
    if cost is None:
        return ""
    if bright:
        return f" [bold yellow](~${cost:.2f})[/bold yellow]"
    return f" (~${cost:.2f})"


def step_start(step: int) -> None:
    """Print step header."""
    console.print(f"\n[bold white]Step {step}[/bold white]")


def step_action(next_step: str, action_repr: str, reasoning: str, estimated_steps_remaining: int | None = None) -> None:
    """Print agent's reasoning, next_step description and the action."""
    console.print(f"  [bright_cyan]{reasoning}[/bright_cyan]")
    if estimated_steps_remaining is not None:
        console.print(f"  [bright_magenta]~{estimated_steps_remaining} steps remaining[/bright_magenta]")
    console.print(f"  [bold green]{next_step}[/bold green]")
    console.print(f"  [white]{action_repr}[/white]")


def step_warning(message: str) -> None:
    console.print(f"  [bold yellow]⚠ {message}[/bold yellow]")


def model_switch(from_model: str, to_model: str, reason: str) -> None:
    """Print model switch notification."""
    console.print(f"\n[bold bright_yellow]🔄 Switching models: {reason}[/bold bright_yellow]")
    console.print(f"  [dim]{from_model}[/dim] → [bold bright_green]{to_model}[/bold bright_green]")


def step_usage(usage: UsageStats, model: str = "", total_usage: UsageStats | None = None) -> None:
    """Print compact per-step token usage and cumulative total."""
    parts = [f"{usage.input_tokens} in", f"{usage.output_tokens} out"]
    cache_parts = []
    if usage.cache_read_tokens:
        cache_parts.append(f"{usage.cache_read_tokens} read")
    if usage.cache_creation_tokens:
        cache_parts.append(f"{usage.cache_creation_tokens} write")
    if cache_parts:
        parts.append(f"cache: {', '.join(cache_parts)}")
    cost = estimate_cost(model, usage) if model else None
    console.print(f"  [dim]{' / '.join(parts)}{_format_cost(cost)}[/dim]")

    if total_usage:
        total_parts = [f"{total_usage.input_tokens} in", f"{total_usage.output_tokens} out"]
        total_cache_parts = []
        if total_usage.cache_read_tokens:
            total_cache_parts.append(f"{total_usage.cache_read_tokens} read")
        if total_usage.cache_creation_tokens:
            total_cache_parts.append(f"{total_usage.cache_creation_tokens} write")
        if total_cache_parts:
            total_parts.append(f"cache: {', '.join(total_cache_parts)}")
        total_cost = estimate_cost(model, total_usage) if model else None
        console.print(f"  [bright_black]total: {' / '.join(total_parts)}{_format_cost(total_cost, bright=True)}[/bright_black]")


def _format_usage(usage: UsageStats, model: str = "", bright_cost: bool = False) -> str:
    """Format usage stats for display in result panels."""
    parts = [f"{usage.input_tokens} in", f"{usage.output_tokens} out"]
    cache_parts = []
    if usage.cache_read_tokens:
        cache_parts.append(f"{usage.cache_read_tokens} read")
    if usage.cache_creation_tokens:
        cache_parts.append(f"{usage.cache_creation_tokens} write")
    if cache_parts:
        parts.append(f"cache: {', '.join(cache_parts)}")
    cost = estimate_cost(model, usage) if model else None
    return f"{' / '.join(parts)}{_format_cost(cost, bright=bright_cost)}"


def result_success(summary: str, steps: int, usage: UsageStats | None = None, model: str = "", usage_by_model: dict[str, UsageStats] | None = None) -> None:
    usage_line = f"\n[white]tokens: {_format_usage(usage, model, bright_cost=True)}[/white]" if usage else ""

    # Add per-model breakdown if multiple models were used
    if usage_by_model and len(usage_by_model) > 1:
        from llm_caller.pricing import estimate_cost
        breakdown_lines = []
        for mdl, mdl_usage in usage_by_model.items():
            cost = estimate_cost(mdl, mdl_usage)
            cost_str = f" (~${cost:.2f})" if cost is not None else ""
            breakdown_lines.append(f"  {mdl}: {mdl_usage.input_tokens} in / {mdl_usage.output_tokens} out{cost_str}")
        usage_line += f"\n[dim]{chr(10).join(breakdown_lines)}[/dim]"

    console.print(Panel(f"{summary}\n[dim]{steps} steps[/dim]{usage_line}", title="Done", border_style="green"))


def result_fail(summary: str, steps: int, usage: UsageStats | None = None, model: str = "", usage_by_model: dict[str, UsageStats] | None = None) -> None:
    usage_line = f"\n[white]tokens: {_format_usage(usage, model, bright_cost=True)}[/white]" if usage else ""

    # Add per-model breakdown if multiple models were used
    if usage_by_model and len(usage_by_model) > 1:
        from llm_caller.pricing import estimate_cost
        breakdown_lines = []
        for mdl, mdl_usage in usage_by_model.items():
            cost = estimate_cost(mdl, mdl_usage)
            cost_str = f" (~${cost:.2f})" if cost is not None else ""
            breakdown_lines.append(f"  {mdl}: {mdl_usage.input_tokens} in / {mdl_usage.output_tokens} out{cost_str}")
        usage_line += f"\n[dim]{chr(10).join(breakdown_lines)}[/dim]"

    console.print(Panel(f"{summary}\n[dim]{steps} steps[/dim]{usage_line}", title="Failed", border_style="red"))
