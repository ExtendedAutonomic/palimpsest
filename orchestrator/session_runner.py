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


# Test model overrides — cheaper models for development
TEST_MODELS = {
    "claude": "claude-sonnet-4-5-20250929",
    "gemini": "gemini-2.5-flash",
}

# Default starting locations per agent (used on session 1 only)
START_LOCATIONS = {
    "claude": "here",
    "gemini": "there",
    "deepseek": "somewhere",
}


def create_agent(
    agent_name: str,
    place_path: Path,
    log_path: Path,
    config: dict,
    test: bool = False,
) -> BaseAgent:
    """Create an agent instance by name."""
    from .agents.claude_agent import ClaudeAgent
    from .agents.gemini_agent import GeminiAgent
    from .agents.deepseek_agent import DeepSeekAgent

    agents = {
        "claude": ClaudeAgent,
        "gemini": GeminiAgent,
        "deepseek": DeepSeekAgent,
    }

    agent_class = agents.get(agent_name)
    if not agent_class:
        raise ValueError(f"Unknown agent: {agent_name}")

    kwargs: dict = {"place_path": place_path, "log_path": log_path, "config": config}
    if test and agent_name in TEST_MODELS:
        kwargs["model"] = TEST_MODELS[agent_name]

    return agent_class(**kwargs)


def get_next_session_number(agent_name: str, log_path: Path) -> int:
    """Get the next session number for an agent based on existing logs."""
    agent_log_dir = log_path / agent_name
    if not agent_log_dir.exists():
        return 1
    existing = list(agent_log_dir.glob("session_*.json"))
    if not existing:
        return 1
    numbers = [int(f.stem.split("_")[1]) for f in existing]
    return max(numbers) + 1


def get_last_location(agent_name: str, log_path: Path) -> str | None:
    """Get the agent's last known location from its most recent log."""
    agent_log_dir = log_path / agent_name
    if not agent_log_dir.exists():
        return None
    logs = sorted(agent_log_dir.glob("session_*.json"))
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


async def run_session(
    agent_name: str,
    place_path: Path,
    log_path: Path,
    config: dict,
    session_override: int | None = None,
    test: bool = False,
) -> SessionResult:
    """
    Run a complete agent session.

    This is the main entry point for running sessions. It handles:
    - Determining the session number
    - Creating the agent
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

    # Determine session number
    if session_override is not None:
        session_num = session_override
    else:
        session_num = get_next_session_number(agent_name, log_path)

    # Check the place exists
    if not place_path.exists() or not any(place_path.glob("*.md")):
        raise FileNotFoundError(
            f"The place has not been initialised. Run 'palimpsest init' first."
        )

    phase = config.get("schedule", {}).get("current_phase", 1)

    logger.info(f"Starting session {session_num} for {agent_name} (Phase {phase})")

    # Create agent
    agent = create_agent(agent_name, place_path, log_path, config, test=test)

    # Build context (memory) for non-first sessions
    memory = None
    start_location = START_LOCATIONS.get(agent_name, "here")

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
        # Thinking tokens are billed at output rate (both Anthropic and Google)
        billable_output = log.total_output_tokens + log.total_thinking_tokens
        log.cost = calculate_cost(
            log.model,
            log.total_input_tokens,
            billable_output,
            cache_creation_tokens=log.total_cache_creation_tokens,
            cache_read_tokens=log.total_cache_read_tokens,
        )
        log_file_early = log_path / agent_name / f"session_{session_num:04d}.json"
        if log_file_early.exists():
            log_file_early.write_text(
                json.dumps(log.to_dict(), indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    # Commit place changes to git
    commit_place_changes(place_path, agent_name, session_num)

    # Run memory compression if needed
    memory_compressed = await run_memory_compression(agent_name, log_path)

    # Generate readable logs (both formats)
    log_file = log_path / agent_name / f"session_{session_num:04d}.json"
    readable_path = None
    try:
        readable_path = save_readable_log(log_file)
    except Exception as e:
        logger.warning(f"Failed to render Obsidian log: {e}")
    try:
        save_github_log(log_file)
    except Exception as e:
        logger.warning(f"Failed to render GitHub log: {e}")

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
