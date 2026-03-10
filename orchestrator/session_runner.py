"""
Session runner for Palimpsest.

Handles the full session lifecycle: agent creation, context building,
session execution, git commit, memory compression, and log rendering.

Extracted from the CLI so sessions can be run programmatically —
from tests, the narrator, a scheduler, or anything else.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from .agents.base import BaseAgent, SessionLog
from .pricing import calculate_cost

logger = logging.getLogger(__name__)


@dataclass
class SessionResult:
    """Summary of a completed session, for callers that don't need the full log."""
    agent_name: str
    session_number: int
    action_count: int
    total_tokens: int
    location_end: str | None
    reflection: str | None
    log_path: Path
    readable_path: Path | None
    memory_compressed: bool


def _get_provider_class(provider: str) -> type[BaseAgent]:
    """Lazy-import and return the agent class for a provider name.

    This is the only place that maps provider strings to classes.
    To add a new provider, add a branch here.
    """
    if provider == "claude":
        from .agents.claude_agent import ClaudeAgent
        return ClaudeAgent
    elif provider == "gemini":
        from .agents.gemini_agent import GeminiAgent
        return GeminiAgent
    elif provider == "deepseek":
        from .agents.deepseek_agent import DeepSeekAgent
        return DeepSeekAgent
    else:
        available = "claude, gemini, deepseek"
        raise ValueError(
            f"Unknown provider: '{provider}'. Available: {available}."
        )


def _deep_merge(base: dict, override: dict) -> dict:
    """Recursively merge override into base, returning a new dict.

    Nested dicts are merged; all other values are replaced.
    """
    result = base.copy()
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def resolve_agent_config(agent_name: str, config: dict) -> dict:
    """Resolve the full configuration for a named agent.

    Merges: global defaults → agent-specific overrides.
    Returns the agent's own config dict with all fields resolved.

    Raises ValueError if the agent is not in the registry.
    """
    agents_config = config.get("agents", {})
    defaults = agents_config.get("defaults", {})
    agents = agents_config.get("agents", {})

    if agent_name not in agents:
        available = ", ".join(sorted(agents.keys())) if agents else "(none)"
        raise ValueError(
            f"Unknown agent: '{agent_name}'. "
            f"Available agents: {available}. "
            f"Define new agents in config/agents.yaml."
        )

    agent_specific = agents[agent_name]
    return _deep_merge(defaults, agent_specific)


def get_available_agents(config: dict) -> list[str]:
    """Return list of agent names from the registry."""
    agents_config = config.get("agents", {})
    return sorted(agents_config.get("agents", {}).keys())


def get_active_agents(config: dict) -> list[str]:
    """Return list of active agent names from the registry."""
    agents_config = config.get("agents", {})
    defaults = agents_config.get("defaults", {})
    agents = agents_config.get("agents", {})
    return sorted(
        name for name, ac in agents.items()
        if _deep_merge(defaults, ac).get("active", True)
    )


def create_agent(
    agent_name: str,
    place_path: Path,
    log_path: Path,
    config: dict,
    agent_config: dict,
    test: bool = False,
) -> BaseAgent:
    """Create an agent instance by name using the registry.

    Passes both config (shared resources like prompt templates) and
    agent_config (per-agent settings) to the agent. The agent reads
    per-agent settings from agent_config and shared resources from config.
    """
    provider = agent_config.get("provider")
    if not provider:
        raise ValueError(
            f"Agent '{agent_name}' has no 'provider' field in agents.yaml."
        )

    agent_class = _get_provider_class(provider)

    # Model: test model or production model from registry
    if test:
        model = agent_config.get("test_model") or agent_config.get("model")
    else:
        model = agent_config.get("model")

    kwargs: dict = {
        "place_path": place_path,
        "log_path": log_path,
        "config": config,
        "agent_config": agent_config,
    }
    if model:
        kwargs["model"] = model

    return agent_class(agent_name, **kwargs)


def get_next_session_number(agent_name: str, log_path: Path) -> int:
    """Get the next session number for an agent based on existing logs."""
    json_dir = log_path / agent_name / "json"
    if not json_dir.exists():
        return 1
    existing = list(json_dir.glob("session_*.json"))
    if not existing:
        return 1
    numbers = [int(f.stem.split("_")[1]) for f in existing]
    return max(numbers) + 1


def get_last_location(agent_name: str, log_path: Path) -> str | None:
    """Get the agent's last known location from its most recent log."""
    json_dir = log_path / agent_name / "json"
    if not json_dir.exists():
        return None
    logs = sorted(json_dir.glob("session_*.json"))
    if not logs:
        return None
    try:
        data = json.loads(logs[-1].read_text(encoding="utf-8"))
        return data.get("location_end")
    except Exception:
        return None


def commit_place_changes(
    place_path: Path,
    agent_name: str,
    session_num: int,
) -> None:
    """Commit any changes to the place's git repository."""
    try:
        import git
        repo = git.Repo(place_path)
        if repo.is_dirty(untracked_files=True):
            repo.git.add(A=True)
            repo.index.commit(f"{agent_name} session {session_num}")
    except Exception as e:
        logger.warning(f"Failed to commit place changes: {e}")


def commit_log_changes(
    log_path: Path,
    agent_name: str,
    session_num: int,
) -> None:
    """Commit any changes to the agent's log repository, if it has one."""
    agent_log_dir = log_path / agent_name
    try:
        import git
        repo = git.Repo(agent_log_dir)
        if repo.is_dirty(untracked_files=True):
            repo.git.add(A=True)
            repo.index.commit(f"session {session_num}")
    except git.InvalidGitRepositoryError:
        pass  # No git repo in this agent's log dir — that's fine
    except Exception as e:
        logger.warning(f"Failed to commit log changes: {e}")


def resolve_place_path(agent_config: dict, project_root: Path) -> Path:
    """Resolve the Place path for an agent from its config.

    The 'place' field is relative to the project root.
    Defaults to 'place' if not specified.
    """
    place_name = agent_config.get("place", "place")
    return project_root / place_name


async def run_session(
    agent_name: str,
    place_path: Path,
    log_path: Path,
    config: dict,
    session_override: int | None = None,
    test: bool = False,
    project_root: Path | None = None,
) -> SessionResult:
    """
    Run a complete agent session.

    This is the main entry point for running sessions. It handles:
    - Resolving agent config from the registry
    - Determining the session number
    - Creating the agent (with both config and agent_config)
    - Building memory context
    - Running the session
    - Committing place changes to git
    - Running memory compression
    - Generating a readable log

    Returns a SessionResult with summary information.
    """
    from .memory.context_builder import build_session_context
    from .memory.summariser import run_memory_compression
    from .renderer import save_readable_log, save_github_log

    # Resolve agent configuration from registry
    agent_config = resolve_agent_config(agent_name, config)

    # Resolve place path — CLI override takes precedence over registry
    if project_root and place_path == project_root / "place":
        place_path = resolve_place_path(agent_config, project_root)

    # Determine session number
    if session_override is not None:
        session_num = session_override
    else:
        session_num = get_next_session_number(agent_name, log_path)

    # Check the place exists
    if not place_path.exists() or not any(place_path.glob("*.md")):
        raise FileNotFoundError(
            f"The place at '{place_path}' has not been initialised. "
            f"Run 'palimpsest init --agent {agent_name}' first."
        )

    phase = agent_config.get("phase", config.get("agents", {}).get("current_phase", 1))

    logger.info(f"Starting session {session_num} for {agent_name} (Phase {phase})")

    # Create agent — receives both shared config and per-agent config
    agent = create_agent(
        agent_name, place_path, log_path, config,
        agent_config=agent_config, test=test,
    )

    # Build context (memory) for non-first sessions
    memory = None
    start_location = agent_config.get("start_location", "here")

    # Ensure starting space exists (creates it on first run for each agent)
    if session_num == 1 and start_location:
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
            logger.info(f"Created starting space: {start_location}")

    if session_num > 1:
        context = build_session_context(
            agent_name=agent_name,
            log_path=log_path,
            last_location=get_last_location(agent_name, log_path),
        )
        memory = context["memory"]
        start_location = context["location"]

    # Run the session
    log = await agent.run_session(
        session_number=session_num,
        phase=phase,
        memory=memory,
        start_location=start_location,
    )

    # Calculate and store cost in the log
    if log.model:
        billable_output = log.total_output_tokens + log.total_thinking_tokens
        log.cost = calculate_cost(
            log.model,
            log.total_input_tokens,
            billable_output,
            cache_creation_tokens=log.total_cache_creation_tokens,
            cache_read_tokens=log.total_cache_read_tokens,
        )
        log_file_early = log_path / agent_name / "json" / f"session_{session_num:04d}.json"
        if log_file_early.exists():
            log_file_early.write_text(
                json.dumps(log.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    # Safety net
    commit_place_changes(place_path, agent_name, session_num)

    # Run memory compression if needed
    compression_config = agent_config.get("compression", {})
    memory_compressed = await run_memory_compression(
        agent_name, log_path,
        compressor_model=compression_config.get("model"),
        recent_window=compression_config.get("recent_window"),
        days_per_week=compression_config.get("days_per_week"),
        enabled=compression_config.get("enabled", True),
    )

    # Generate readable logs (both formats)
    log_file = log_path / agent_name / "json" / f"session_{session_num:04d}.json"
    readable_path = None
    try:
        readable_path = save_readable_log(log_file)
    except Exception as e:
        logger.warning(f"Failed to render Obsidian log: {e}")
    try:
        save_github_log(log_file)
    except Exception as e:
        logger.warning(f"Failed to render GitHub log: {e}")

    # Commit logs if the agent has its own log repo
    commit_log_changes(log_path, agent_name, session_num)

    return SessionResult(
        agent_name=agent_name,
        session_number=session_num,
        action_count=log.action_count,
        total_tokens=log.total_input_tokens + log.total_cache_creation_tokens + log.total_cache_read_tokens + log.total_output_tokens,
        location_end=log.location_end,
        reflection=log.reflection,
        log_path=log_file,
        readable_path=readable_path,
        memory_compressed=memory_compressed,
    )
