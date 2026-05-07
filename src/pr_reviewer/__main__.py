import os
import sys

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.text import Text

load_dotenv()

console = Console()


def main() -> None:
    args = sys.argv[1:]
    dry_run = "--dry-run" in args
    args = [a for a in args if a != "--dry-run"]

    if not args:
        console.print("[red]Usage:[/red] python -m pr_reviewer <github_pr_url> [--dry-run]")
        console.print("[dim]Example: python -m pr_reviewer https://github.com/owner/repo/pull/123[/dim]")
        console.print("[dim]         python -m pr_reviewer https://github.com/owner/repo/pull/123 --dry-run[/dim]")
        sys.exit(1)

    pr_url = args[0]

    if not pr_url.startswith("https://github.com/"):
        console.print(f"[red]Error:[/red] Not a valid GitHub PR URL: {pr_url}")
        sys.exit(1)

    if not os.environ.get("GITHUB_TOKEN"):
        console.print("[red]Error:[/red] GITHUB_TOKEN environment variable is not set.")
        console.print("[dim]Copy .env.example to .env and fill in your token.[/dim]")
        sys.exit(1)

    provider = os.environ.get("LLM_PROVIDER", "openai").lower()

    if provider == "openai":
        if not os.environ.get("OPENAI_API_KEY"):
            console.print("[red]Error:[/red] OPENAI_API_KEY is not set (required when LLM_PROVIDER=openai).")
            sys.exit(1)
        model = os.environ.get("OPENAI_MODEL", "gpt-4o")
    elif provider == "anthropic":
        if not os.environ.get("ANTHROPIC_API_KEY"):
            console.print("[red]Error:[/red] ANTHROPIC_API_KEY is not set (required when LLM_PROVIDER=anthropic).")
            sys.exit(1)
        model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-6")
    else:
        model = os.environ.get("OLLAMA_MODEL", "qwen2.5-coder:7b")

    db_path = os.environ.get("DB_PATH", "pr_reviewer.db")

    header = Text()
    header.append("PR Reviewer", style="bold cyan")
    header.append(f"\nProvider : {provider} / {model}", style="dim")
    header.append(f"\nDB       : {db_path}", style="dim")
    header.append(f"\nPR       : {pr_url}", style="dim")
    if dry_run:
        header.append("\nMode     : DRY RUN (review will not be posted)", style="bold yellow")
    console.print(Panel(header, expand=False))

    from pr_reviewer.agent import run_review  # noqa: PLC0415

    console.print("\n[bold green]Agent starting...[/bold green]\n")

    try:
        result = run_review(pr_url, db_path=db_path, dry_run=dry_run, console=console)
    except Exception as e:  # noqa: BLE001
        console.print(f"\n[red]Error during review:[/red] {e}")
        sys.exit(1)

    if dry_run:
        console.print(Panel(result, title="[bold yellow]Dry Run — review NOT posted[/bold yellow]", expand=False))
    else:
        console.print(Panel(result, title="[bold green]Review posted to GitHub[/bold green]", expand=False))


if __name__ == "__main__":
    main()
