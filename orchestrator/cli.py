"""
Palimpsest CLI — command-line interface for running the experiment.

Usage:
    palimpsest init                          # Initialise the place + git
    palimpsest init --agent claude_b         # Initialise a specific agent's place
    palimpsest run --agent claude --once     # Single session
    palimpsest agents                        # List registered agents
    palimpsest place --tree                  # View the place
    palimpsest logs --agent claude --last 3  # View recent logs
    palimpsest costs                         # Check spend
    palimpsest render                        # Re-render readable logs
    palimpsest compress --agent gemini        # Recompress memory standalone
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
    """Load and merge all config files.

    Config files:
        prompts.yaml  — shared prompt templates
        agents.yaml   — agent registry, defaults, current_phase
        costs.yaml    — pricing and budget
    """
    config = {}
    for name in ["prompts", "agents", "costs"]:
        config_file = CONFIG_PATH / f"{name}.yaml"
        if config_file.exists():
            with open(config_file, encoding="utf-8") as f:
                config[name] = yaml.safe_load(f) or {}
        else:
            config[name] = {}
    # Flatten prompts for easier access
    config["prompts"] = config.get("prompts", {})
    return config


def validate_agent_name(config: dict, agent_name: str) -> None:
    """Validate that an agent name exists in the registry."""
    from .session_runner import get_available_agents
    available = get_available_agents(config)
    if agent_name not in available:
        raise click.BadParameter(
            f"Unknown agent: '{agent_name}'. "
            f"Available: {', '.join(available)}. "
            f"Define new agents in config/agents.yaml."
        )


def parse_sessions(values: tuple[str, ...]) -> tuple[int, ...] | None:
    """Parse session arguments into a flat tuple of ints.

    Accepts individual numbers ("3") and ranges ("3-6").
    Returns None if no values provided.
    """
    if not values:
        return None
    result = []
    for v in values:
        if "-" in v:
            parts = v.split("-", 1)
            try:
                start, end = int(parts[0]), int(parts[1])
                result.extend(range(start, end + 1))
            except ValueError:
                raise click.BadParameter(f"Invalid session range: {v}")
        else:
            try:
                result.append(int(v))
            except ValueError:
                raise click.BadParameter(f"Invalid session number: {v}")
    return tuple(sorted(set(result)))


def setup_logging(verbose: bool = False) -> None:
    """Configure logging."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


@click.group()
@click.option("--verbose", "-v", is_flag=True, help="Verbose logging")
def cli(verbose: bool) -> None:
    """Palimpsest — an experiment in AI phenomenology."""
    setup_logging(verbose)


@cli.command()
@click.option("--agent", "-a", type=str, default=None,
              help="Initialise a specific agent's place (creates its place directory)")
def init(agent: str | None) -> None:
    """Initialise the place with the starting structure."""
    import git

    config = load_config()

    if agent:
        validate_agent_name(config, agent)
        from .session_runner import resolve_agent_config, resolve_place_path
        agent_config = resolve_agent_config(agent, config)
        place_path = resolve_place_path(agent_config, PROJECT_ROOT)
        start_location = agent_config.get("start_location", "here")
        _init_place(place_path, start_location)
        click.echo(f"\nPlace for {agent} ready: {place_path}")
    else:
        _init_place(PLACE_PATH, "here")
        click.echo(f"\nThe place is ready: {PLACE_PATH}")

    click.echo()
    click.echo("One space. Empty.")


def _init_place(place_path: Path, start_location: str) -> None:
    """Create and git-initialise a place directory."""
    import git

    place_path.mkdir(parents=True, exist_ok=True)

    start_note = place_path / f"{start_location}.md"
    if not start_note.exists():
        start_note.write_text(
            "---\n"
            "type: space\n"
            "created_by: place\n"
            "created_session: 0\n"
            "updated_by: place\n"
            "updated_session: 0\n"
            "---\n",
            encoding="utf-8",
        )
        click.echo(f"  Created starting space: {start_location}")

    obsidian_dir = place_path / ".obsidian"
    obsidian_dir.mkdir(exist_ok=True)
    app_json = obsidian_dir / "app.json"
    if not app_json.exists():
        app_json.write_text(json.dumps({
            "promptDelete": False,
            "alwaysUpdateLinks": True,
        }, indent=2))

    try:
        repo = git.Repo(place_path)
        click.echo("  Git repository already exists.")
    except git.InvalidGitRepositoryError:
        repo = git.Repo.init(place_path)
        gitignore = place_path / ".gitignore"
        gitignore.write_text(
            ".obsidian/workspace.json\n"
            ".obsidian/workspace-mobile.json\n"
        )
        repo.index.add([".gitignore"])
        repo.index.commit("The place exists")
        click.echo("  Git repository initialised.")


@cli.command()
@click.option("--agent", "-a", type=str, required=True,
              help="Which agent to run (from agents.yaml)")
@click.option("--once", is_flag=True, help="Run a single session")
@click.option("--session", "-s", type=int, default=None,
              help="Override session number")
@click.option("--test", is_flag=True, help="Use cheaper test model instead of production")
@click.option("--place", type=click.Path(exists=True), default=None,
              help="Override place directory (for test runs)")
@click.option("--logs", type=click.Path(), default=None,
              help="Override log directory (for test runs)")
def run(agent: str, once: bool, session: int | None, test: bool, place: str | None, logs: str | None) -> None:
    """Run an agent session."""
    config = load_config()
    validate_agent_name(config, agent)

    place_path = Path(place) if place else PLACE_PATH
    log_path = Path(logs) if logs else LOG_PATH
    if logs:
        log_path.mkdir(parents=True, exist_ok=True)

    if once:
        asyncio.run(_run_once(
            agent, config, session_override=session, test=test,
            place_path=place_path, log_path=log_path,
        ))
    else:
        click.echo("Specify --once to run a session.")


async def _run_once(
    agent_name: str,
    config: dict,
    session_override: int | None = None,
    test: bool = False,
    place_path: Path | None = None,
    log_path: Path | None = None,
) -> None:
    """CLI wrapper for running a single session."""
    from .session_runner import run_session, resolve_agent_config

    if place_path is None:
        place_path = PLACE_PATH
    if log_path is None:
        log_path = LOG_PATH

    agent_config = resolve_agent_config(agent_name, config)
    model = agent_config.get("test_model", "test") if test else agent_config.get("model", "production")
    model_label = f"test ({model})" if test else f"production ({model})"
    click.echo(f"Starting session for {agent_name} ({model_label})")

    result = await run_session(
        agent_name=agent_name,
        place_path=place_path,
        log_path=log_path,
        config=config,
        session_override=session_override,
        test=test,
        project_root=PROJECT_ROOT,
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
def agents() -> None:
    """List registered agents and their configuration."""
    config = load_config()
    from .session_runner import get_available_agents, resolve_agent_config

    phase = config.get("agents", {}).get("current_phase", "?")
    click.echo(f"Current phase: {phase}")

    for name in get_available_agents(config):
        ac = resolve_agent_config(name, config)
        status = "active" if ac.get("active", True) else "inactive"
        desc = ac.get("description", "")
        provider = ac.get("provider", "?")
        model = ac.get("model", "?")
        place = ac.get("place", "place")
        nudge_raw = ac.get("nudge", "...")
        if nudge_raw == "...":
            nudge_display = "..."
        elif nudge_raw.strip() == "":
            nudge_display = repr(nudge_raw)
        else:
            nudge_display = nudge_raw

        click.echo(f"\n  {name} [{status}]")
        if desc:
            click.echo(f"    {desc}")
        click.echo(f"    provider: {provider}, model: {model}")
        click.echo(f"    place: {place}, nudge: {nudge_display}")


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
        json_dir = LOG_PATH / agent / "json"
        if not json_dir.exists():
            click.echo(f"No logs for {agent}")
            return
        log_files = sorted(json_dir.glob("session_*.json"))[-last:]
    else:
        log_files = sorted(LOG_PATH.glob("*/json/session_*.json"))[-last:]

    for lf in log_files:
        data = json.loads(lf.read_text(encoding="utf-8"))
        click.echo(f"\n{'='*60}")
        click.echo(f"Agent: {data['agent_name']} | Session: {data['session_number']}")
        tokens = data.get('tokens', {})
        total_tokens = (tokens.get('input', 0) + tokens.get('cache_creation', 0)
                        + tokens.get('cache_read', 0) + tokens.get('output', 0))
        click.echo(f"Actions: {data.get('action_count', '?')} | Tokens: {total_tokens:,}")
        if data.get("reflection"):
            click.echo(f"\nReflection:\n{data['reflection'][:500]}")
        click.echo(f"{'='*60}")


@cli.command()
def costs() -> None:
    """Check experiment costs so far."""
    from .pricing import calculate_cost
    config = load_config()

    total_cost = 0.0

    for agent_dir in sorted(LOG_PATH.iterdir()):
        if not agent_dir.is_dir() or agent_dir.name.startswith("."):
            continue
        if agent_dir.name in ("narrator", "experimenter"):
            continue

        agent_name = agent_dir.name
        agent_cost = 0.0
        total_tokens = 0
        session_count = 0

        json_dir = agent_dir / "json"
        if json_dir.exists():
            for log_file in sorted(json_dir.glob("session_*.json")):
                try:
                    data = json.loads(log_file.read_text(encoding="utf-8"))
                    tokens = data.get("tokens", {})
                    input_tokens = tokens.get("input", 0)
                    output_tokens = tokens.get("output", 0)
                    thinking_tokens = tokens.get("thinking", 0)
                    cache_creation = tokens.get("cache_creation", 0)
                    cache_read = tokens.get("cache_read", 0)
                    total_tokens += input_tokens + cache_creation + cache_read + output_tokens + thinking_tokens
                    session_count += 1
                    if data.get("cost") is not None:
                        agent_cost += data["cost"]
                    elif data.get("model"):
                        agent_cost += calculate_cost(
                            data["model"], input_tokens, output_tokens + thinking_tokens,
                            cache_creation_tokens=cache_creation,
                            cache_read_tokens=cache_read,
                        )
                except Exception:
                    continue

        compression_file = agent_dir / "json" / "compression_costs.json"
        if compression_file.exists():
            try:
                compressions = json.loads(compression_file.read_text(encoding="utf-8"))
                for c in compressions:
                    c_input = c.get("input_tokens", 0)
                    c_output = c.get("output_tokens", 0)
                    total_tokens += c_input + c_output
                    agent_cost += calculate_cost(c["model"], c_input, c_output)
            except Exception:
                pass

        total_cost += agent_cost
        click.echo(f"{agent_name}: {session_count} sessions, "
                   f"{total_tokens:,} tokens, ${agent_cost:.2f}")

    click.echo("")
    observer_specs = [
        ("narrator", "chapter_*.json", "chapters"),
        ("experimenter", "post_*.json", "posts"),
    ]
    for dir_name, glob_pattern, label in observer_specs:
        observer_dir = LOG_PATH / dir_name
        if not observer_dir.exists():
            continue
        observer_cost = 0.0
        item_count = 0
        total_tokens = 0
        for sidecar in sorted(observer_dir.glob(glob_pattern)):
            try:
                data = json.loads(sidecar.read_text(encoding="utf-8"))
                tokens = data.get("tokens", {})
                input_tokens = tokens.get("input", 0)
                output_tokens = tokens.get("output", 0)
                total_tokens += input_tokens + output_tokens
                item_count += 1
                if data.get("cost") is not None:
                    observer_cost += data["cost"]
                elif data.get("model"):
                    observer_cost += calculate_cost(data["model"], input_tokens, output_tokens)
            except Exception:
                continue
        total_cost += observer_cost
        click.echo(f"{dir_name}: {item_count} {label}, "
                   f"{total_tokens:,} tokens, ${observer_cost:.2f}")

    budget = config.get("costs", {}).get("budget", {})
    cap = budget.get("total_cap", 200)
    click.echo(f"\nTotal: ${total_cost:.2f} / ${cap:.2f}")


@cli.command()
@click.option("--agent", "-a", type=str, default=None)
@click.option("--session", "-s", type=str, multiple=True)
@click.option("--format", "-f", "fmt", type=click.Choice(["both", "obsidian", "github"]), default="both")
def render(agent: str | None, session: tuple[str, ...], fmt: str) -> None:
    """Re-render readable logs from session JSON files."""
    from .renderer import save_readable_log, save_github_log

    sessions = parse_sessions(session)

    if agent:
        agent_dirs = [LOG_PATH / agent]
    else:
        agent_dirs = [
            d for d in sorted(LOG_PATH.iterdir())
            if d.is_dir() and d.name not in ("narrator", "experimenter", ".git")
            and not d.name.startswith(".")
        ]

    rendered = 0
    for agent_dir in agent_dirs:
        if not agent_dir.exists():
            click.echo(f"No logs for {agent_dir.name}")
            continue
        json_dir = agent_dir / "json"
        if not json_dir.exists():
            continue
        log_files = sorted(json_dir.glob("session_*.json"))
        if sessions:
            log_files = [f for f in log_files if int(f.stem.split("_")[1]) in sessions]

        for log_file in log_files:
            try:
                if fmt in ("both", "obsidian"):
                    save_readable_log(log_file)
                if fmt in ("both", "github"):
                    save_github_log(log_file)
                rendered += 1
                click.echo(f"  {agent_dir.name}/{log_file.name} -> {fmt}")
            except Exception as e:
                click.echo(f"  {agent_dir.name}/{log_file.name} FAILED: {e}", err=True)

    click.echo(f"\nRendered {rendered} session(s).")


@cli.command()
@click.option("--agent", "-a", type=str, required=True,
              help="Which agent to compress memory for")
def compress(agent: str) -> None:
    """Run memory compression for an agent without running a session.

    Useful when you need to recompress from scratch (e.g. after wiping
    compressed_memory.md) or force compression before the next session.
    """
    config = load_config()
    validate_agent_name(config, agent)

    from .session_runner import resolve_agent_config
    from .memory.summariser import run_memory_compression

    agent_config = resolve_agent_config(agent, config)
    compression_config = agent_config.get("compression", {})

    model = compression_config.get("model") or agent_config.get("model")
    provider = agent_config.get("provider")

    click.echo(f"Compressing memory for {agent} (model: {model}, provider: {provider})")

    compressed = asyncio.run(run_memory_compression(
        agent, LOG_PATH,
        compressor_model=model,
        compressor_provider=provider,
        recent_window=compression_config.get("recent_window"),
        days_per_week=compression_config.get("days_per_week"),
        enabled=compression_config.get("enabled", True),
    ))

    if compressed:
        compressed_file = LOG_PATH / agent / "compressed_memory.md"
        click.echo(f"Compression complete. Output: {compressed_file}")
    else:
        click.echo("Nothing to compress (not enough sessions beyond the recent window).")


if __name__ == "__main__":
    cli()
