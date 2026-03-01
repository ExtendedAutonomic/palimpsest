"""
Palimpsest CLI — command-line interface for running the experiment.

Usage:
    palimpsest init                          # Initialise the place + git
    palimpsest run --agent claude --once     # Single test session
    palimpsest run --schedule                # Run daily schedule
    palimpsest place --tree                  # View the place
    palimpsest logs --agent claude --last 3  # View recent logs
    palimpsest narrate                       # Run narrator
    palimpsest costs                         # Check spend
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

import click
import yaml
from dotenv import load_dotenv

load_dotenv()

# Project root — two levels up from this file
PROJECT_ROOT = Path(__file__).resolve().parent.parent
PLACE_PATH = PROJECT_ROOT / "place"
LOG_PATH = PROJECT_ROOT / "logs"
CONFIG_PATH = PROJECT_ROOT / "config"


def load_config() -> dict:
    """Load and merge all config files."""
    config = {}
    for name in ["prompts", "schedule", "costs"]:
        config_file = CONFIG_PATH / f"{name}.yaml"
        if config_file.exists():
            with open(config_file, encoding="utf-8") as f:
                config[name] = yaml.safe_load(f) or {}
        else:
            config[name] = {}
    # Flatten for easier access
    config["prompts"] = config.get("prompts", {})
    config["session"] = config.get("schedule", {}).get("session", {})
    return config


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging")
def cli(verbose: bool) -> None:
    """Palimpsest — an experiment in AI phenomenology."""
    setup_logging(verbose)


@cli.command()
def init() -> None:
    """Initialise the place with the starting structure."""
    import git

    click.echo("Initialising the place...")

    # Ensure place directory exists
    PLACE_PATH.mkdir(parents=True, exist_ok=True)

    # Create the founding space
    here_note = PLACE_PATH / "here.md"
    if not here_note.exists():
        here_note.write_text(
            "---\n"
            "type: space\n"
            "created_by: place\n"
            "created_session: 0\n"
            "updated_by: place\n"
            "updated_session: 0\n"
            "---\n",
            encoding="utf-8",
        )

    # Create minimal .obsidian config
    obsidian_dir = PLACE_PATH / ".obsidian"
    obsidian_dir.mkdir(exist_ok=True)

    app_json = obsidian_dir / "app.json"
    if not app_json.exists():
        app_json.write_text(json.dumps({
            "promptDelete": False,
            "alwaysUpdateLinks": True,
        }, indent=2))

    # Initialise git repo
    try:
        repo = git.Repo(PLACE_PATH)
        click.echo("Git repository already exists.")
    except git.InvalidGitRepositoryError:
        repo = git.Repo.init(PLACE_PATH)
        # Create .gitignore
        gitignore = PLACE_PATH / ".gitignore"
        gitignore.write_text(
            ".obsidian/workspace.json\n"
            ".obsidian/workspace-mobile.json\n"
        )
        repo.index.add([".gitignore"])
        repo.index.commit("The place exists")
        click.echo("Git repository initialised.")

    click.echo(f"\nThe place is ready: {PLACE_PATH}")
    click.echo()
    click.echo("  here.md")
    click.echo()
    click.echo("One space. Empty.")


@cli.command()
@click.option("--agent", "-a", type=click.Choice(["claude", "gemini", "deepseek"]),
              required=True, help="Which agent to run")
@click.option("--once", is_flag=True, help="Run a single session then stop")
@click.option("--session", "-s", type=int, default=None,
              help="Override session number")
@click.option("--phase", "-p", type=int, default=1,
              help="Current experiment phase")
@click.option("--schedule", is_flag=True, help="Run on the configured schedule")
def run(agent: str, once: bool, session: int | None, phase: int, schedule: bool) -> None:
    """Run an agent session."""
    config = load_config()

    if once:
        asyncio.run(_run_once(agent, config, session_override=session, phase=phase))
    elif schedule:
        click.echo("Scheduled mode not yet implemented. Use --once for now.")
    else:
        click.echo("Specify --once for a single session or --schedule for recurring.")


async def _run_once(
    agent_name: str,
    config: dict,
    session_override: int | None = None,
    phase: int = 1,
) -> None:
    """CLI wrapper for running a single session."""
    from .session_runner import run_session

    click.echo(f"Starting session for {agent_name} (Phase {phase})")

    result = await run_session(
        agent_name=agent_name,
        place_path=PLACE_PATH,
        log_path=LOG_PATH,
        config=config,
        session_override=session_override,
        phase=phase,
    )

    click.echo(f"\nSession {result.session_number} complete.")
    click.echo(f"  Actions: {result.action_count}")
    click.echo(f"  Tokens: {result.total_tokens:,}")
    click.echo(f"  Final location: {result.location_end}")
    if result.memory_compressed:
        click.echo("  Memory compressed.")
    if result.reflection:
        click.echo(f"\nReflection:\n{result.reflection[:500]}")


@cli.command()
@click.option("--tree", is_flag=True, help="Show the place as a tree")
def place(tree: bool) -> None:
    """View the state of the place."""
    if tree:
        _print_tree(PLACE_PATH)
    else:
        click.echo(f"The place: {PLACE_PATH}")
        file_count = sum(1 for _ in PLACE_PATH.rglob("*") if _.is_file() and not any(
            p.startswith(".") for p in _.relative_to(PLACE_PATH).parts
        ))
        click.echo(f"Things: {file_count}")


def _print_tree(path: Path, prefix: str = "", is_last: bool = True) -> None:
    """Print a directory tree, excluding hidden things."""
    name = path.name or str(path)
    connector = "\u2514\u2500\u2500 " if is_last else "\u251c\u2500\u2500 "
    if prefix:
        click.echo(f"{prefix}{connector}{name}")
    else:
        click.echo(name)

    if path.is_dir():
        children = sorted(
            [c for c in path.iterdir() if not c.name.startswith(".")],
            key=lambda c: (c.is_file(), c.name),
        )
        for i, child in enumerate(children):
            is_last_child = (i == len(children) - 1)
            extension = "    " if is_last else "\u2502   "
            _print_tree(child, prefix + (extension if prefix else ""), is_last_child)


@cli.command()
@click.option("--agent", "-a", type=str, help="Filter by agent")
@click.option("--last", "-n", type=int, default=1, help="Number of sessions to show")
def logs(agent: str | None, last: int) -> None:
    """View session logs."""
    if agent:
        agent_dir = LOG_PATH / agent
        if not agent_dir.exists():
            click.echo(f"No logs for {agent}")
            return
        log_files = sorted(agent_dir.glob("session_*.json"))[-last:]
    else:
        log_files = sorted(LOG_PATH.rglob("session_*.json"))[-last:]

    for lf in log_files:
        data = json.loads(lf.read_text(encoding="utf-8"))
        click.echo(f"\n{'='*60}")
        click.echo(f"Agent: {data['agent_name']} | Session: {data['session_number']}")
        click.echo(f"Actions: {data.get('action_count', '?')} | "
                    f"Tokens: {data.get('tokens', {}).get('input', 0) + data.get('tokens', {}).get('output', 0)}")
        if data.get("reflection"):
            click.echo(f"\nReflection:\n{data['reflection'][:500]}")
        click.echo(f"{'='*60}")


@cli.command()
def costs() -> None:
    """Check experiment costs so far."""
    config = load_config()
    pricing = config.get("costs", {}).get("pricing", {})

    total_cost = 0.0
    for agent_dir in LOG_PATH.iterdir():
        if not agent_dir.is_dir() or agent_dir.name.startswith("."):
            continue
        agent_name = agent_dir.name
        model_key = config.get("costs", {}).get("models", {}).get(agent_name)
        if not model_key or model_key not in pricing:
            continue
        model_pricing = pricing[model_key]

        agent_input = 0
        agent_output = 0
        session_count = 0

        for log_file in agent_dir.glob("session_*.json"):
            try:
                data = json.loads(log_file.read_text(encoding="utf-8"))
                tokens = data.get("tokens", {})
                agent_input += tokens.get("input", 0)
                agent_output += tokens.get("output", 0) + tokens.get("thinking", 0)
                session_count += 1
            except Exception:
                continue

        input_cost = (agent_input / 1_000_000) * model_pricing.get("input", 0)
        output_cost = (agent_output / 1_000_000) * model_pricing.get("output", 0)
        agent_cost = input_cost + output_cost
        total_cost += agent_cost

        click.echo(f"{agent_name}: {session_count} sessions, "
                    f"{agent_input + agent_output:,} tokens, ${agent_cost:.2f}")

    budget = config.get("costs", {}).get("budget", {})
    cap = budget.get("total_cap", 200)
    click.echo(f"\nTotal: ${total_cost:.2f} / ${cap:.2f}")


@cli.command()
def narrate() -> None:
    """Run the narrator agent."""
    click.echo("Narrator not yet implemented.")


if __name__ == "__main__":
    cli()
