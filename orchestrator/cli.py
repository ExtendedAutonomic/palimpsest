"""
Palimpsest CLI — command-line interface for running the experiment.

Usage:
    palimpsest init                          # Initialise the place + git
    palimpsest run --agent claude --once     # Single test session
    palimpsest run --schedule                # Run daily schedule
    palimpsest place --tree                  # View the place
    palimpsest logs --agent claude --last 3  # View recent logs
    palimpsest narrate                       # Run narrator
    palimpsest blog                          # Write a blog post
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
@click.option("--once", is_flag=True, help="Run a single session")
@click.option("--session", "-s", type=int, default=None,
              help="Override session number")
@click.option("--test", is_flag=True, help="Use cheaper test model (Sonnet) instead of production (Opus)")
def run(agent: str, once: bool, session: int | None, test: bool) -> None:
    """Run an agent session."""
    config = load_config()

    if once:
        asyncio.run(_run_once(agent, config, session_override=session, test=test))
    else:
        click.echo("Specify --once to run a session.")


async def _run_once(
    agent_name: str,
    config: dict,
    session_override: int | None = None,
    test: bool = False,
) -> None:
    """CLI wrapper for running a single session."""
    from .session_runner import run_session

    model_label = "test (Sonnet)" if test else "production (Opus)"
    click.echo(f"Starting session for {agent_name} ({model_label})")

    result = await run_session(
        agent_name=agent_name,
        place_path=PLACE_PATH,
        log_path=LOG_PATH,
        config=config,
        session_override=session_override,
        test=test,
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

    # Primary agents
    for agent_dir in sorted(LOG_PATH.iterdir()):
        if not agent_dir.is_dir() or agent_dir.name.startswith("."):
            continue
        if agent_dir.name in ("narrator", "experimenter"):
            continue

        agent_name = agent_dir.name
        agent_cost = 0.0
        total_tokens = 0
        session_count = 0

        for log_file in sorted(agent_dir.glob("session_*.json")):
            try:
                data = json.loads(log_file.read_text(encoding="utf-8"))
                tokens = data.get("tokens", {})
                input_tokens = tokens.get("input", 0)
                output_tokens = tokens.get("output", 0)
                cache_creation = tokens.get("cache_creation", 0)
                cache_read = tokens.get("cache_read", 0)
                total_tokens += input_tokens + cache_creation + cache_read + output_tokens
                session_count += 1
                if data.get("cost") is not None:
                    agent_cost += data["cost"]
                elif data.get("model"):
                    agent_cost += calculate_cost(
                        data["model"], input_tokens, output_tokens,
                        cache_creation_tokens=cache_creation,
                        cache_read_tokens=cache_read,
                    )
            except Exception:
                continue

        # Add compression costs for this agent
        compression_file = agent_dir / "compression_costs.json"
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

    # Observer agents — narrator and experimenter sidecars
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
@click.option("--day", "-d", type=str, default=None,
              help="Date to narrate (YYYY-MM-DD). Defaults to today.")
@click.option("--prompt", "-p", type=click.Path(exists=True), default=None,
              help="Path to narrator prompt markdown file.")
@click.option("--session", "-s", type=str, multiple=True,
              help="Session(s) to include. Accepts numbers (3) and ranges (3-6).")
@click.option("--test", is_flag=True, help="Use Sonnet instead of Opus.")
def narrate(day: str | None, prompt: str | None, session: tuple[str, ...], test: bool) -> None:
    """Run the narrator agent to chronicle the day's events."""
    asyncio.run(_run_narrator(day, prompt, parse_sessions(session), test=test))


async def _run_narrator(day_str: str | None, prompt_path_str: str | None, sessions: tuple[int, ...] | None = None, test: bool = False) -> None:
    """CLI wrapper for running the narrator."""
    from datetime import datetime, timezone
    from .narrator.narrator import run_narrator

    # Parse day
    day = None
    if day_str:
        day = datetime.strptime(day_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)

    # Resolve narrator prompt path
    if prompt_path_str:
        narrator_prompt_path = Path(prompt_path_str)
    else:
        # Default: look in vault, then fall back to config
        vault_prompt = Path("D:/Vault/Projects/Active/Palimpsest/Narrator Prompt.md")
        if vault_prompt.exists():
            narrator_prompt_path = vault_prompt
        else:
            narrator_prompt_path = CONFIG_PATH / "narrator_prompt.md"

    from .narrator.narrator import NARRATOR_MODEL
    TEST_MODEL = "claude-sonnet-4-5-20250929"
    model = TEST_MODEL if test else NARRATOR_MODEL

    click.echo(f"Running narrator ({'test/Sonnet' if test else 'Opus'})...")
    click.echo(f"  Prompt: {narrator_prompt_path}")
    if day:
        click.echo(f"  Day: {day.strftime('%Y-%m-%d')}")

    try:
        output_file = await run_narrator(
            log_path=LOG_PATH,
            narrator_prompt_path=narrator_prompt_path,
            day=day,
            sessions=sessions,
            model=model,
        )
        click.echo(f"\nChapter saved: {output_file}")
        click.echo()
        # Print the chapter
        content = output_file.read_text(encoding="utf-8")
        click.echo(content)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)


@cli.command()
@click.option("--topic", "-t", type=str, default=None,
              help="What the post should be about. If omitted, writes about whatever is most interesting.")
@click.option("--since", type=str, default=None,
              help="Include sessions from this date (YYYY-MM-DD).")
@click.option("--until", type=str, default=None,
              help="Include sessions up to this date (YYYY-MM-DD).")
@click.option("--session", "-s", type=str, multiple=True,
              help="Session(s) to include. Accepts numbers (3) and ranges (3-6).")
@click.option("--agent", "-a", type=str, default=None,
              help="Filter sessions by agent name.")
@click.option("--chapter", "-c", type=int, multiple=True,
              help="Narrator chapter(s) to include. Can be repeated.")
@click.option("--prompt", "-p", type=click.Path(exists=True), default=None,
              help="Path to experimenter blog prompt markdown file.")
@click.option("--no-memories", is_flag=True, help="Exclude compressed memory files from context.")
@click.option("--test", is_flag=True, help="Use Sonnet instead of Opus.")
def blog(
    topic: str | None,
    since: str | None,
    until: str | None,
    session: tuple[str, ...],
    agent: str | None,
    chapter: tuple[int, ...],
    prompt: str | None,
    no_memories: bool,
    test: bool,
) -> None:
    """Write an experimenter blog post about the experiment."""
    asyncio.run(_run_blog(
        topic=topic,
        since_str=since,
        until_str=until,
        sessions=parse_sessions(session),
        agent=agent,
        chapters=chapter or None,
        prompt_path_str=prompt,
        include_memories=not no_memories,
        test=test,
    ))


async def _run_blog(
    topic: str | None = None,
    since_str: str | None = None,
    until_str: str | None = None,
    sessions: tuple[int, ...] | None = None,
    agent: str | None = None,
    chapters: tuple[int, ...] | None = None,
    prompt_path_str: str | None = None,
    include_memories: bool = True,
    test: bool = False,
) -> None:
    """CLI wrapper for running the experimenter."""
    from datetime import datetime, timezone
    from .experimenter.experimenter import run_experimenter

    config = load_config()

    # Parse dates
    since = None
    if since_str:
        since = datetime.strptime(since_str, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    until = None
    if until_str:
        until = datetime.strptime(until_str, "%Y-%m-%d").replace(
            hour=23, minute=59, second=59, tzinfo=timezone.utc
        )

    # Resolve prompt path
    if prompt_path_str:
        experimenter_prompt_path = Path(prompt_path_str)
    else:
        vault_prompt = Path("D:/Vault/Projects/Active/Palimpsest/Experimenter Blog Prompt.md")
        if vault_prompt.exists():
            experimenter_prompt_path = vault_prompt
        else:
            experimenter_prompt_path = CONFIG_PATH / "experimenter_prompt.md"

    from .experimenter.experimenter import EXPERIMENTER_MODEL
    TEST_MODEL = "claude-sonnet-4-5-20250929"
    model = TEST_MODEL if test else EXPERIMENTER_MODEL

    click.echo(f"Writing blog post ({'test/Sonnet' if test else 'Opus'})...")
    click.echo(f"  Prompt: {experimenter_prompt_path}")
    if topic:
        click.echo(f"  Topic: {topic}")
    if since:
        click.echo(f"  Since: {since.strftime('%Y-%m-%d')}")
    if until:
        click.echo(f"  Until: {until.strftime('%Y-%m-%d')}")
    if sessions:
        click.echo(f"  Sessions: {', '.join(str(s) for s in sessions)}")
    if agent:
        click.echo(f"  Agent: {agent}")
    if chapters:
        click.echo(f"  Narrator chapters: {', '.join(str(c) for c in chapters)}")
    if not include_memories:
        click.echo("  Excluding compressed memories")

    try:
        output_file = await run_experimenter(
            log_path=LOG_PATH,
            experimenter_prompt_path=experimenter_prompt_path,
            config=config,
            topic=topic,
            since=since,
            until=until,
            sessions=sessions,
            agent=agent,
            narrator_chapters=chapters,
            include_memories=include_memories,
            model=model,
        )
        click.echo(f"\nPost saved: {output_file}")
        click.echo()
        # Print the post
        content = output_file.read_text(encoding="utf-8")
        click.echo(content)
    except ValueError as e:
        click.echo(f"Error: {e}", err=True)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}", err=True)


if __name__ == "__main__":
    cli()
