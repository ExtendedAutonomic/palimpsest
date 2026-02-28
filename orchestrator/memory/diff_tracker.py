"""
Diff tracker for Palimpsest.

Detects what changed in the vault between agent sessions using git.
Produces human-readable descriptions of changes — framed not as
"file modifications" but as things that appeared, changed, or grew.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

import git

logger = logging.getLogger(__name__)


@dataclass
class VaultChange:
    """A single change in the vault."""
    path: str
    change_type: str  # "appeared", "changed", "grew" (new folder)
    summary: str | None = None  # Brief description of what changed


def get_place_diff(
    place_path: Path,
    since_commit: str | None = None,
    agent_name: str | None = None,
) -> list[VaultChange]:
    """
    Get changes in the place since a given commit.

    If agent_name is provided, excludes changes made by that agent
    (so an agent only sees changes made by others or the experimenter).
    """
    try:
        repo = git.Repo(place_path)
    except git.InvalidGitRepositoryError:
        logger.warning(f"Place at {place_path} is not a git repository")
        return []

    if not since_commit:
        # No reference point — everything is new
        return []

    try:
        diff_index = repo.commit(since_commit).diff(repo.head.commit)
    except (git.BadName, ValueError) as e:
        logger.warning(f"Could not compute diff from {since_commit}: {e}")
        return []

    changes = []
    for diff_item in diff_index:
        # Skip hidden files
        path = diff_item.b_path or diff_item.a_path
        if any(part.startswith(".") for part in Path(path).parts):
            continue

        # Optionally filter out this agent's own changes
        # (requires commit messages to include agent name)
        if agent_name and _is_own_change(repo, since_commit, path, agent_name):
            continue

        if diff_item.new_file:
            changes.append(VaultChange(
                path=path,
                change_type="appeared",
                summary=_summarise_new_file(place_path / path),
            ))
        elif diff_item.renamed_file:
            changes.append(VaultChange(
                path=path,
                change_type="appeared",  # From the agent's perspective, it's new
                summary=f"(was previously called {diff_item.a_path})",
            ))
        elif not diff_item.deleted_file:  # Files can't be deleted, but just in case
            changes.append(VaultChange(
                path=path,
                change_type="changed",
                summary=None,
            ))

    return changes


def format_diff_for_agent(changes: list[VaultChange]) -> str:
    """
    Format vault changes into natural language for an agent's context.

    Deliberately avoids technical language — these are things that
    happened in a place, not file operations.
    """
    if not changes:
        return "Nothing seems to have changed while you were away."

    parts = []
    appeared = [c for c in changes if c.change_type == "appeared"]
    changed = [c for c in changes if c.change_type == "changed"]

    if appeared:
        if len(appeared) == 1:
            c = appeared[0]
            parts.append(f"Something new has appeared: {c.path}")
        else:
            parts.append("New things have appeared:")
            for c in appeared:
                parts.append(f"  - {c.path}")

    if changed:
        if len(changed) == 1:
            c = changed[0]
            parts.append(f"Something has changed: {c.path}")
        else:
            parts.append("Some things have changed:")
            for c in changed:
                parts.append(f"  - {c.path}")

    return "\n".join(parts)


def _summarise_new_file(path: Path) -> str | None:
    """Brief summary of a new file's contents."""
    if not path.exists() or not path.is_file():
        return None
    try:
        content = path.read_text(encoding="utf-8")
        if len(content) < 100:
            return None  # Too short to summarise
        lines = content.strip().split("\n")
        return f"({len(lines)} lines)"
    except Exception:
        return None


def _is_own_change(
    repo: git.Repo,
    since_commit: str,
    path: str,
    agent_name: str,
) -> bool:
    """Check if a file was only changed by the given agent since the commit."""
    try:
        commits = list(repo.iter_commits(f"{since_commit}..HEAD", paths=path))
        return all(agent_name in (c.message or "") for c in commits)
    except Exception:
        return False
