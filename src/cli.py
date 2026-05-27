import sys
import json
import os
import subprocess
from pathlib import Path
from datetime import datetime, timezone

import typer
import rich
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import load_config, HARNESS_DIR
from registry import init_db, register_project, get_all_projects, get_project, update_project_status
from utils.project_scaffold import scaffold_project, get_project_path, generate_project_id

app = typer.Typer(name="harness", help="Spec-driven local harness system")
console = Console()


def ensure_db():
    if not (HARNESS_DIR / "registry.db").exists():
        init_db()


@app.command()
def init(name: str, spec: str | None = typer.Option(None, "--spec", "-s", help="Path to spec file")):
    """Initialize a new project."""
    ensure_db()

    spec_content = None
    if spec:
        spec_path = Path(spec).expanduser()
        if not spec_path.exists():
            console.print(f"[red]Spec file not found: {spec_path}[/red]")
            raise typer.Exit(1)
        spec_content = spec_path.read_text()

    try:
        project_path = scaffold_project(name, spec_content)
    except FileExistsError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    project_id = generate_project_id(name)
    register_project(project_id, name, str(project_path))

    subprocess.run(["git", "init", str(project_path)], check=True, capture_output=True)
    subprocess.run(["git", "-C", str(project_path), "add", "."], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(project_path), "commit", "-m", "Initial scaffold"],
        check=True, capture_output=True,
    )

    console.print(Panel(
        f"[bold green]Project '{name}' initialized[/]\n"
        f"Path: {project_path}\n"
        f"ID: {project_id}",
        title="Success",
    ))


@app.command()
def status():
    """Show project status."""
    ensure_db()
    projects = get_all_projects()

    if not projects:
        console.print("[dim]No projects registered.[/dim]")
        return

    table = Table(title="Projects")
    table.add_column("Name", style="cyan")
    table.add_column("Status", style="green")
    table.add_column("Phase", style="yellow")
    table.add_column("Sessions", justify="right")
    table.add_column("Last Checkpoint", justify="right")

    for p in projects:
        table.add_row(
            p["name"],
            p["status"],
            p["current_phase"] or "-",
            str(p["session_count"]),
            p["last_checkpoint"] or "-",
        )

    console.print(table)


@app.command()
def spec(name: str, action: str = typer.Option("show", "--action", "-a")):
    """Show or edit project spec."""
    project_path = get_project_path(name)
    spec_path = project_path / ".harness" / "spec.md"

    if not spec_path.exists():
        console.print(f"[red]Project '{name}' not found.[/red]")
        raise typer.Exit(1)

    if action == "show":
        console.print(Panel(spec_path.read_text(), title=f"Spec: {name}"))
    elif action == "edit":
        editor = os.environ.get("EDITOR", "nano")
        subprocess.run([editor, str(spec_path)])


@app.command()
def dashboard(port: int = typer.Option(8765, "--port", "-p")):
    """Start the dashboard server."""
    ensure_db()
    console.print(f"[bold]Dashboard starting on http://localhost:{port}[/bold]")
    import uvicorn
    from dashboard.api.app import create_app
    uvicorn.run(create_app(), host="127.0.0.1", port=port, log_level="info")


@app.command()
def plan(name: str):
    """Run planner agent to generate plan.md."""
    ensure_db()
    project = get_project_by_name(name)
    if not project:
        console.print(f"[red]Project '{name}' not found.[/red]")
        raise typer.Exit(1)

    console.print(f"[bold]Running planner for '{name}'...[/bold]")
    from agents.executor import Executor
    executor = Executor(name, project["id"])
    plan_text = executor.run_planner()

    console.print(Panel(plan_text[:1000] + ("..." if len(plan_text) > 1000 else ""), title="Generated Plan"))

    from registry import add_session
    add_session(project["id"], executor.session_tag, executor.session_tag)

    console.print("[bold green]Plan generated and saved to plan.md[/bold green]")


@app.command()
def run(name: str, phase: str | None = None):
    """Execute a phase with agent loop."""
    ensure_db()
    project = get_project_by_name(name)
    if not project:
        console.print(f"[red]Project '{name}' not found.[/red]")
        raise typer.Exit(1)

    from agents.executor import Executor
    executor = Executor(name, project["id"])

    if phase:
        console.print(f"[bold]Running phase '{phase}' for '{name}'...[/bold]")
        results = executor.run_phase(phase)
        console.print(f"[bold]Results:[/bold] {results}")
    else:
        console.print(f"[bold]Running all phases for '{name}'...[/bold]")
        memory = executor.memory
        phases = list(memory.get_phase_progress().keys())
        for p in phases:
            console.print(f"[bold]Phase: {p}[/bold]")
            results = executor.run_phase(p)
            console.print(f"  {results}")

    console.print("[bold green]Execution complete.[/bold green]")


def get_project_by_name(name: str) -> dict | None:
    projects = get_all_projects()
    for p in projects:
        if p["name"] == name:
            return p
    return None


@app.command()
def checkpoint(name: str):
    """Compact session context and commit to git."""
    ensure_db()
    project = get_project_by_name(name)
    if not project:
        console.print(f"[red]Project '{name}' not found.[/red]")
        raise typer.Exit(1)

    from memory.compactor import Compactor
    compactor = Compactor(name, project["id"])
    result = compactor.checkpoint()

    console.print(Panel(
        f"Session: {result['session_id']}\n"
        f"Tag: {result['tag']}\n"
        f"Summary: {result['summary'].get('session_summary', 'N/A')}",
        title="Checkpoint Complete",
    ))


@app.command()
def resume(name: str, from_tag: str | None = typer.Option(None, "--from")):
    """Resume project from checkpoint."""
    ensure_db()
    project = get_project_by_name(name)
    if not project:
        console.print(f"[red]Project '{name}' not found.[/red]")
        raise typer.Exit(1)

    from memory.compactor import Compactor
    compactor = Compactor(name, project["id"])
    result = compactor.resume(from_tag)

    console.print(f"[bold]Resumed '{name}'[/bold]")
    console.print(f"  Sessions loaded: {len(result['recent_sessions'])}")
    console.print(f"  Tasks: {len(result['memory_state'].get('tasks', []))}")
    pending = [t for t in result['memory_state'].get('tasks', []) if t['status'] in ('pending', 'in_progress')]
    console.print(f"  Pending: {len(pending)}")


@app.command()
def agent(
    action: str = typer.Option("list", "--action", "-a", help="Action: list or set"),
    name: str | None = typer.Option(None, "--name", "-n", help="Agent name (for set)"),
    model: str | None = typer.Option(None, "--model", "-m", help="Model (for set)"),
):
    """View or change agent→model mapping."""
    config = load_config()
    if action == "list":
        table = Table(title="Agent Configuration")
        table.add_column("Agent", style="cyan")
        table.add_column("Model", style="green")
        table.add_column("Type", style="yellow")

        for agent_name, agent_cfg in config.agents.items():
            agent_type = "direct" if agent_cfg.direct else "opencode"
            table.add_row(agent_name, agent_cfg.model, agent_type)

        console.print(table)
    elif action == "set" and name and model:
        console.print(f"[yellow]Agent config update not yet persistent. (future)[/yellow]")


@app.command(name="reasonix-run")
def reasonix_run(
    stub: str | None = typer.Argument(None, help="Path to stub .md file (e.g. src/stubs/BP-01-scaffold.md)"),
    list_stubs: bool = typer.Option(False, "--list", "-l", help="List available blueprint stubs"),
    dry_run: bool = typer.Option(False, "--dry-run", "-n", help="Print task text without executing"),
    project_dir: str | None = typer.Option(None, "--dir", "-d", help="Working directory for Reasonix (default: current dir)"),
    timeout: int = typer.Option(300, "--timeout", "-t", help="Timeout in seconds for Reasonix execution"),
):
    """Read a stub file and pass it to Reasonix for autonomous execution.

    Stub files are self-contained markdown blueprints with YAML frontmatter.
    They describe a task with full context, spec, and acceptance criteria,
    designed to be passed to reasonix for autonomous execution.

    Examples:

        # List available stubs
        harness reasonix-run --list

        # Dry-run with BP-01 scaffold blueprint
        harness reasonix-run src/stubs/BP-01-scaffold.md --dry-run

        # Execute stub autonomously via Reasonix
        harness reasonix-run src/stubs/BP-01-scaffold.md

    Requires `reasonix` CLI installed globally: npm install -g reasonix
    """
    if list_stubs:
        from stubs.runner import list_stubs as _list_stubs
        stubs = _list_stubs()
        if not stubs:
            console.print("[yellow]No stub files found in src/stubs/[/yellow]")
            return
        table = Table(title="Available Blueprint Stubs")
        table.add_column("BP", style="cyan")
        table.add_column("Name", style="green")
        table.add_column("Title", style="white")
        table.add_column("Init", justify="center")
        for s in stubs:
            table.add_row(s["bp"], s["name"], s["title"], "✓" if s["init"] else "")
        console.print(table)
        return

    if not stub:
        console.print("[red]No stub file specified. Use --list to see available stubs.[/red]")
        raise typer.Exit(1)

    stub_path = Path(stub).expanduser()
    if not stub_path.exists():
        # Try relative to stubs dir
        alt_path = Path(__file__).parent / "stubs" / stub
        if alt_path.exists():
            stub_path = alt_path
        # Try with .md extension
        elif not stub.endswith(".md"):
            with_md = stub_path.with_suffix(".md")
            if with_md.exists():
                stub_path = with_md
            else:
                alt_with_md = Path(__file__).parent / "stubs" / (stub + ".md")
                if alt_with_md.exists():
                    stub_path = alt_with_md
                else:
                    console.print(f"[red]Stub file not found: {stub}[/red]")
                    console.print("[yellow]Use --list to see available stubs[/yellow]")
                    raise typer.Exit(1)

    console.print(f"[bold]Reading stub:[/bold] {stub_path.name}")

    from stubs.runner import run_stub, parse_stub

    try:
        # Quick parse to show summary
        parsed = parse_stub(stub_path)
        fm = parsed["frontmatter"]
        console.print(f"  BP: {fm.get('bp', '—')}")
        console.print(f"  Title: {fm.get('title', stub_path.stem)}")
        console.print(f"  Init project: {'yes' if fm.get('init') else 'no'}")
        console.print(f"  Body: {len(parsed['body'])} chars")
        console.print("")

        cwd = Path(project_dir).expanduser() if project_dir else None

        result = run_stub(
            stub_path=stub_path,
            project_dir=cwd,
            dry_run=dry_run,
            timeout_sec=timeout,
        )

        if result["action"] == "dry_run":
            console.print("[yellow]Dry-run mode — task would be passed to Reasonix:[/yellow]")
            if result.get("task_text"):
                console.print(Panel(result["task_text"][:2000], title="Task Preview"))
        elif result["action"] == "error":
            console.print(f"[red]Error: {result.get('error', 'Unknown error')}[/red]")
            console.print("[yellow]Install Reasonix: npm install -g reasonix[/yellow]")
            raise typer.Exit(1)
        elif result["action"] == "executed":
            console.print(Panel(
                f"BP: {result['stub']['bp']}\n"
                f"Title: {result['stub']['title']}\n"
                f"Command: {result['command']}\n"
                f"Exit code: {result['returncode']}",
                title="Execution Complete",
            ))
            if result["stdout"]:
                console.print("[bold]Output:[/bold]")
                console.print(result["stdout"][:2000])
            if result["stderr"]:
                console.print("[dim]Stderr:[/dim]")
                console.print(result["stderr"][:500])
        elif result["action"] == "timeout":
            console.print(f"[red]Timed out after {timeout}s[/red]")

    except Exception as e:
        console.print(f"[red]Error running stub: {e}[/red]")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
