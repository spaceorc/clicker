"""Rich console output for clean, user-friendly step-by-step display."""

from rich.console import Console
from rich.panel import Panel

from llm_caller import UsageStats
from llm_caller.pricing import estimate_cost, estimate_total_cost

console = Console()


def _format_cost(cost: float | None, bright: bool = False) -> str:
    """Format cost as a parenthetical string, or empty if None."""
    if cost is None:
        return ""
    if bright:
        return f" [bold yellow](~${cost:.2f})[/bold yellow]"
    return f" (~${cost:.2f})"


def step_start(step: int, model: str = "") -> None:
    """Print step header with model name."""
    model_str = f" [dim]({model})[/dim]" if model else ""
    console.print(f"\n[bold white]Step {step}{model_str}[/bold white]")


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


def _format_tokens(usage: UsageStats) -> str:
    parts = [f"{usage.input_tokens} in", f"{usage.output_tokens} out"]
    cache_parts = []
    if usage.cache_read_tokens:
        cache_parts.append(f"{usage.cache_read_tokens} read")
    if usage.cache_creation_tokens:
        cache_parts.append(f"{usage.cache_creation_tokens} write")
    if cache_parts:
        parts.append(f"cache: {', '.join(cache_parts)}")
    return " / ".join(parts)


def step_usage(usage: UsageStats, model: str, total_usage: UsageStats, usage_by_model: dict[str, UsageStats]) -> None:
    """Print compact per-step token usage and cumulative total (each model priced at its own rate)."""
    console.print(f"  [dim]{_format_tokens(usage)}{_format_cost(estimate_cost(model, usage))}[/dim]")
    total_cost = estimate_total_cost(usage_by_model)
    console.print(f"  [bright_black]total: {_format_tokens(total_usage)}{_format_cost(total_cost, bright=True)}[/bright_black]")


def _format_result_usage(usage: UsageStats, usage_by_model: dict[str, UsageStats]) -> str:
    """Format total usage with cost summed over models, plus a per-model breakdown if several were used."""
    line = f"\n[white]tokens: {_format_tokens(usage)}{_format_cost(estimate_total_cost(usage_by_model), bright=True)}[/white]"
    if len(usage_by_model) > 1:
        breakdown_lines = [
            f"  {mdl}: {_format_tokens(mdl_usage)}{_format_cost(estimate_cost(mdl, mdl_usage))}"
            for mdl, mdl_usage in usage_by_model.items()
        ]
        line += f"\n[dim]{chr(10).join(breakdown_lines)}[/dim]"
    return line


def result_success(summary: str, steps: int, usage: UsageStats, usage_by_model: dict[str, UsageStats]) -> None:
    usage_line = _format_result_usage(usage, usage_by_model)
    console.print(Panel(f"{summary}\n[dim]{steps} steps[/dim]{usage_line}", title="Done", border_style="green"))


def result_fail(summary: str, steps: int, usage: UsageStats, usage_by_model: dict[str, UsageStats]) -> None:
    usage_line = _format_result_usage(usage, usage_by_model)
    console.print(Panel(f"{summary}\n[dim]{steps} steps[/dim]{usage_line}", title="Failed", border_style="red"))
