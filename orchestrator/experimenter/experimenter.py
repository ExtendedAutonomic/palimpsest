"""
Experimenter blog for Palimpsest.

The experimenter writes from outside the experiment — showing working,
sharing what's surprising, being honest about what breaks. Published
alongside the narrator's chronicles but serving a different function:
the narrator writes from inside, the blog writes from outside.

The experimenter sees everything: session logs (including thinking
and reflections), the narrator's chapters, the experiment design
docs, and cost data.

Unlike the narrator (which runs daily), the experimenter writes
when there's something worth writing about.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import anthropic

logger = logging.getLogger(__name__)

# Model — Opus for production
EXPERIMENTER_MODEL = "claude-opus-4-6"
MAX_OUTPUT_TOKENS = 8192  # Posts can be longer than narrator chapters

from ..pricing import calculate_cost


def load_experimenter_prompt(prompt_path: Path | None = None) -> str:
    """
    Load the experimenter system prompt.

    Reads from a dedicated markdown file — the Experimenter Blog Prompt
    note in the vault.
    """
    if prompt_path and prompt_path.exists():
        content = prompt_path.read_text(encoding="utf-8")
        # Strip YAML frontmatter if present
        if content.startswith("---"):
            parts = content.split("---", 2)
            if len(parts) >= 3:
                return parts[2].strip()
        return content.strip()

    raise FileNotFoundError(
        f"Experimenter prompt not found at {prompt_path}. "
        "Provide a path to the experimenter blog prompt markdown file."
    )


def gather_session_logs_range(
    log_path: Path,
    since: datetime | None = None,
    until: datetime | None = None,
    sessions: tuple[int, ...] | None = None,
    agent: str | None = None,
) -> list[dict]:
    """
    Gather session logs across a date range.

    More flexible than the narrator's day-based gathering —
    blog posts might cover multiple days or specific sessions.
    """
    logs = []

    for agent_dir in log_path.iterdir():
        if not agent_dir.is_dir() or agent_dir.name.startswith("."):
            continue
        if agent_dir.name in ("narrator", "experimenter"):
            continue
        if agent and agent_dir.name != agent:
            continue

        json_dir = agent_dir / "json"
        if not json_dir.exists():
            continue
        for log_file in sorted(json_dir.glob("session_*.json")):
            try:
                data = json.loads(log_file.read_text(encoding="utf-8"))

                # Filter by session number if specified
                if sessions and data.get("session_number") not in sessions:
                    continue

                # Filter by date range
                log_time = data.get("start_time", "")
                if log_time:
                    log_dt = datetime.fromisoformat(log_time)
                    if since and log_dt < since:
                        continue
                    if until and log_dt > until:
                        continue

                logs.append(data)
            except Exception as e:
                logger.warning(f"Failed to load {log_file}: {e}")

    return sorted(logs, key=lambda x: x.get("session_number", 0))


def gather_readable_logs_range(
    log_path: Path,
    since: datetime | None = None,
    until: datetime | None = None,
    sessions: tuple[int, ...] | None = None,
    agent: str | None = None,
) -> list[str]:
    """
    Gather readable markdown logs across a date range.
    """
    readable_logs = []

    for agent_dir in log_path.iterdir():
        if not agent_dir.is_dir() or agent_dir.name.startswith("."):
            continue
        if agent_dir.name in ("narrator", "experimenter"):
            continue
        if agent and agent_dir.name != agent:
            continue

        readable_dir = agent_dir / "obsidian_logs"
        json_dir = agent_dir / "json"
        if not json_dir.exists():
            continue
        for log_file in sorted(json_dir.glob("session_*.json")):
            try:
                data = json.loads(log_file.read_text(encoding="utf-8"))

                if sessions and data.get("session_number") not in sessions:
                    continue

                log_time = data.get("start_time", "")
                if log_time:
                    log_dt = datetime.fromisoformat(log_time)
                    if since and log_dt < since:
                        continue
                    if until and log_dt > until:
                        continue

                # Try readable version first
                readable_file = readable_dir / log_file.name.replace(
                    ".json", ".md"
                )
                if readable_file.exists():
                    readable_logs.append(
                        readable_file.read_text(encoding="utf-8")
                    )
                else:
                    from ..renderer import render_session_markdown
                    readable_logs.append(
                        render_session_markdown(log_file)
                    )
            except Exception as e:
                logger.warning(f"Failed to load readable log for {log_file}: {e}")

    return readable_logs


def gather_narrator_chapters(
    narrator_output_path: Path,
    chapters: tuple[int, ...] | None = None,
) -> list[dict]:
    """
    Load narrator chapters — the experimenter can reference and quote these.
    """
    entries = []

    if not narrator_output_path.exists():
        return entries

    for entry_file in sorted(narrator_output_path.glob("chapter_*.md")):
        try:
            chapter_num = int(entry_file.stem.split("_")[1])
            if chapters and chapter_num not in chapters:
                continue

            content = entry_file.read_text(encoding="utf-8")
            title = ""
            for line in content.split("\n"):
                if line.startswith("# "):
                    title = line[2:].strip()
                    break

            entries.append({
                "chapter": chapter_num,
                "title": title,
                "content": content,
            })
        except Exception as e:
            logger.warning(f"Failed to load narrator chapter {entry_file}: {e}")

    return sorted(entries, key=lambda x: x["chapter"])


def gather_compressed_memories(log_path: Path, agent: str | None = None) -> list[dict]:
    """
    Load compressed memory files for each agent.

    These show what the agent actually receives as its memory of
    older sessions — the lossy, reshaped version of its own past.
    The experimenter can compare this against the full session logs
    to write about what was kept, what was lost, and how the
    compression reshapes the agent's self-understanding.
    """
    memories = []

    for agent_dir in sorted(log_path.iterdir()):
        if not agent_dir.is_dir() or agent_dir.name.startswith("."):
            continue
        if agent_dir.name in ("narrator", "experimenter"):
            continue
        if agent and agent_dir.name != agent:
            continue

        compressed_file = agent_dir / "compressed_memory.md"
        if compressed_file.exists():
            try:
                content = compressed_file.read_text(encoding="utf-8")
                memories.append({
                    "agent": agent_dir.name,
                    "content": content,
                })
            except Exception as e:
                logger.warning(f"Failed to load compressed memory for {agent_dir.name}: {e}")

    return memories


def gather_cost_summary(log_path: Path, config: dict) -> str:
    """
    Build a cost summary the experimenter can reference.

    Covers primary agents (session_*.json), narrator (chapter_*.json
    sidecars), and experimenter (post_*.json sidecars).
    Prefers stored cost; falls back to calculating from tokens + model.
    """
    from ..pricing import calculate_cost as _calculate_cost
    lines = []
    total_cost = 0.0

    # Primary agents
    for agent_dir in sorted(log_path.iterdir()):
        if not agent_dir.is_dir() or agent_dir.name.startswith("."):
            continue
        if agent_dir.name in ("narrator", "experimenter"):
            continue

        agent_name = agent_dir.name
        agent_cost = 0.0
        session_count = 0
        total_tokens = 0

        json_dir = agent_dir / "json"
        if not json_dir.exists():
            continue
        for log_file in sorted(json_dir.glob("session_*.json")):
            try:
                data = json.loads(log_file.read_text(encoding="utf-8"))
                tokens = data.get("tokens", {})
                input_tokens = tokens.get("input", 0)
                output_tokens = tokens.get("output", 0)
                total_tokens += input_tokens + output_tokens
                session_count += 1
                if data.get("cost") is not None:
                    agent_cost += data["cost"]
                elif data.get("model"):
                    agent_cost += _calculate_cost(data["model"], input_tokens, output_tokens)
            except Exception:
                continue

        total_cost += agent_cost
        lines.append(
            f"{agent_name}: {session_count} sessions, "
            f"{total_tokens:,} tokens, ${agent_cost:.2f}"
        )

    # Observer agents — narrator and experimenter sidecars
    observer_specs = [
        ("narrator", "chapter_*.json", "chapters"),
        ("experimenter", "post_*.json", "posts"),
    ]
    for dir_name, glob_pattern, label in observer_specs:
        observer_dir = log_path / dir_name
        if not observer_dir.exists():
            continue
        observer_cost = 0.0
        item_count = 0
        total_tokens = 0
        for sidecar in sorted(observer_dir.glob(glob_pattern)):
            try:
                data = json.loads(sidecar.read_text(encoding="utf-8"))
                tokens = data.get("tokens", {})
                total_tokens += tokens.get("input", 0) + tokens.get("output", 0)
                item_count += 1
                if data.get("cost") is not None:
                    observer_cost += data["cost"]
                elif data.get("model"):
                    observer_cost += _calculate_cost(
                        data["model"],
                        tokens.get("input", 0),
                        tokens.get("output", 0),
                    )
            except Exception:
                continue
        total_cost += observer_cost
        lines.append(
            f"{dir_name}: {item_count} {label}, "
            f"{total_tokens:,} tokens, ${observer_cost:.2f}"
        )

    budget = config.get("costs", {}).get("budget", {})
    cap = budget.get("total_cap", 200)
    lines.append(f"Total: ${total_cost:.2f} / ${cap:.2f}")

    return "\n".join(lines)


def get_previous_posts(experimenter_output_path: Path) -> list[dict]:
    """
    Load previous blog posts for continuity.
    """
    posts = []

    if not experimenter_output_path.exists():
        return posts

    for post_file in sorted(experimenter_output_path.glob("post_*.md")):
        try:
            content = post_file.read_text(encoding="utf-8")
            post_num = int(post_file.stem.split("_")[1])
            title = ""
            for line in content.split("\n"):
                if line.startswith("# "):
                    title = line[2:].strip()
                    break
            posts.append({
                "number": post_num,
                "title": title,
                "content": content,
            })
        except Exception as e:
            logger.warning(f"Failed to load blog post {post_file}: {e}")

    return sorted(posts, key=lambda x: x["number"])


def get_next_post_number(experimenter_output_path: Path) -> int:
    """Get the next post number based on existing posts."""
    if not experimenter_output_path.exists():
        return 1
    existing = list(experimenter_output_path.glob("post_*.md"))
    if not existing:
        return 1
    numbers = []
    for f in existing:
        try:
            numbers.append(int(f.stem.split("_")[1]))
        except (ValueError, IndexError):
            pass
    return max(numbers) + 1 if numbers else 1


def load_design_docs(design_doc_paths: list[Path]) -> str:
    """
    Load the experiment design documents from the vault.

    These give the experimenter full context for what the experiment
    is and how it works, so it can write about it.
    """
    parts = []

    for doc_path in design_doc_paths:
        if not doc_path.exists():
            logger.warning(f"Design doc not found: {doc_path}")
            continue
        try:
            content = doc_path.read_text(encoding="utf-8")
            # Strip YAML frontmatter
            if content.startswith("---"):
                fm_parts = content.split("---", 2)
                if len(fm_parts) >= 3:
                    content = fm_parts[2].strip()
            parts.append(f"### {doc_path.stem}\n")
            parts.append(content)
            parts.append("")
        except Exception as e:
            logger.warning(f"Failed to load design doc {doc_path}: {e}")

    return "\n".join(parts) if parts else ""


def build_experimenter_input(
    readable_logs: list[str],
    narrator_chapters: list[dict],
    previous_posts: list[dict],
    design_docs: str,
    cost_summary: str,
    post_number: int,
    topic: str | None = None,
    compressed_memories: list[dict] | None = None,
) -> str:
    """
    Build the user message for the experimenter.

    Assembles everything the experimenter has access to:
    design docs, session logs, compressed memories, narrator
    chapters, previous posts, and cost data.
    """
    parts = []

    # Design docs (experiment context)
    if design_docs:
        parts.append("## Experiment design\n")
        parts.append(design_docs)
        parts.append("")

    # Previous posts for continuity
    if previous_posts:
        parts.append("## Your previous posts\n")
        for post in previous_posts:
            parts.append(f"### Post {post['number']}: {post['title']}\n")
            parts.append(post["content"])
            parts.append("")

    # Narrator chapters intentionally excluded from experimenter input.
    # The experimenter writes from outside the experiment and should form
    # its own perspective from session logs rather than being led by the
    # narrator's framing.

    # Session logs
    if readable_logs:
        parts.append("## Session logs\n")
        for log_md in readable_logs:
            parts.append(log_md)
            parts.append("\n---\n")

    # Compressed memories — what the agent actually remembers
    if compressed_memories:
        parts.append("## Compressed memories\n")
        parts.append(
            "These are the compressed memories each agent receives at session "
            "start in place of the full session logs above. Compare what was "
            "kept against what actually happened.\n"
        )
        for mem in compressed_memories:
            parts.append(f"### {mem['agent']}\n")
            parts.append(mem["content"])
            parts.append("")

    # Cost data
    if cost_summary:
        parts.append("## Cost summary\n")
        parts.append(cost_summary)
        parts.append("")

    # Instruction
    if post_number == 1 and not previous_posts:
        intro = (
            f"Write Post {post_number}. "
            "This is the first post. Introduce the experiment to readers: "
            "what Palimpsest is, why it exists, how it works. "
            "Use the design docs above for context. "
            "Then cover what happened in the session(s) provided. "
            "The reader should finish understanding both the experiment "
            "and what has happened so far."
        )
        if topic:
            intro += f" The experimenter also wants to cover: {topic}"
        parts.append(intro)
    elif topic:
        parts.append(
            f"Write Post {post_number}. "
            f"The experimenter wants to write about: {topic}"
        )
    else:
        parts.append(
            f"Write Post {post_number}. "
            f"Write about whatever is most interesting from the material above."
        )

    return "\n".join(parts)


# Default design doc paths in the vault
DEFAULT_DESIGN_DOC_NAMES = [
    "Palimpsest",
    "Palimpsest - Technical Architecture",
    "Palimpsest - Experimental Design",
    "Palimpsest - Insights",
]


async def run_experimenter(
    log_path: Path,
    experimenter_prompt_path: Path,
    config: dict,
    experimenter_output_path: Path | None = None,
    narrator_output_path: Path | None = None,
    design_docs_path: Path | None = None,
    topic: str | None = None,
    since: datetime | None = None,
    until: datetime | None = None,
    sessions: tuple[int, ...] | None = None,
    agent: str | None = None,
    narrator_chapters: tuple[int, ...] | None = None,
    include_memories: bool = True,
    model: str = EXPERIMENTER_MODEL,
) -> Path:
    """
    Run the experimenter to produce a blog post.

    Gathers all available material — session logs, narrator chapters,
    design docs, cost data — and produces a post.

    Returns the path to the saved post file.
    """
    if experimenter_output_path is None:
        experimenter_output_path = log_path / "experimenter"
    experimenter_output_path.mkdir(parents=True, exist_ok=True)

    if narrator_output_path is None:
        narrator_output_path = log_path / "narrator"

    if design_docs_path is None:
        design_docs_path = Path("D:/Vault/Projects/Active/Palimpsest")

    # Load the experimenter system prompt
    system_prompt = load_experimenter_prompt(experimenter_prompt_path)

    # Gather session logs
    readable_logs = gather_readable_logs_range(
        log_path, since=since, until=until, sessions=sessions, agent=agent,
    )

    # Gather narrator chapters
    chapters = gather_narrator_chapters(
        narrator_output_path, chapters=narrator_chapters,
    )

    # Previous posts
    previous_posts = get_previous_posts(experimenter_output_path)

    # Design docs
    design_doc_paths = [
        design_docs_path / f"{name}.md"
        for name in DEFAULT_DESIGN_DOC_NAMES
    ]
    design_docs = load_design_docs(design_doc_paths)

    # Cost summary
    cost_summary = gather_cost_summary(log_path, config)

    # Compressed memories — included by default so the experimenter
    # can compare what the agent remembers against the full logs.
    # Use --no-memories to exclude (e.g. for posts covering sessions
    # before compression has occurred).
    compressed_memories = (
        gather_compressed_memories(log_path, agent=agent)
        if include_memories else None
    )

    # Determine post number
    post_number = get_next_post_number(experimenter_output_path)

    # Build the input
    user_message = build_experimenter_input(
        readable_logs=readable_logs,
        narrator_chapters=chapters,
        previous_posts=previous_posts,
        design_docs=design_docs,
        cost_summary=cost_summary,
        post_number=post_number,
        topic=topic,
        compressed_memories=compressed_memories,
    )

    logger.info(
        f"Running experimenter (Post {post_number}, "
        f"{len(readable_logs)} session logs, "
        f"{len(chapters)} narrator chapters)"
    )

    # Call the API
    client = anthropic.AsyncAnthropic()

    response = await client.messages.create(
        model=model,
        max_tokens=MAX_OUTPUT_TOKENS,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )

    post_text = response.content[0].text

    # Token usage and cost
    usage = response.usage
    post_cost = calculate_cost(model, usage.input_tokens, usage.output_tokens)
    total_post_tokens = usage.input_tokens + usage.output_tokens

    logger.info(
        f"Experimenter tokens — input: {usage.input_tokens:,}, "
        f"output: {usage.output_tokens:,}, cost: ${post_cost:.2f}"
    )

    # Derive which sessions were actually included
    session_logs_raw = gather_session_logs_range(
        log_path, since=since, until=until, sessions=sessions, agent=agent,
    )
    included_sessions = sorted(s["session_number"] for s in session_logs_raw if "session_number" in s)
    sessions_str = ", ".join(str(s) for s in included_sessions) if included_sessions else ""

    # Derive phase from session logs (use latest if mixed)
    phases = sorted(set(s.get("phase", 1) for s in session_logs_raw))
    phase = phases[-1] if phases else config.get("schedule", {}).get("current_phase", 1)

    # Build frontmatter
    now = datetime.now(timezone.utc)
    frontmatter = (
        f"---\n"
        f"type: experimenter\n"
        f"post: {post_number}\n"
        f"phase: {phase}\n"
        f"date: {now.strftime('%Y-%m-%d')}\n"
        f"model: {model}\n"
        f"tokens: {total_post_tokens:,}\n"
        f"cost: ${post_cost:.2f}\n"
    )
    if sessions_str:
        frontmatter += f"sessions: {sessions_str}\n"
    frontmatter += f"---\n\n"

    # Save the post
    output_file = experimenter_output_path / f"post_{post_number:04d}.md"
    output_file.write_text(frontmatter + post_text, encoding="utf-8")

    # Save cost sidecar — same structure as session logs for palimpsest costs
    sidecar = {
        "model": model,
        "phase": phase,
        "tokens": {"input": usage.input_tokens, "output": usage.output_tokens},
        "cost": post_cost,
    }
    sidecar_file = experimenter_output_path / f"post_{post_number:04d}.json"
    sidecar_file.write_text(json.dumps(sidecar, indent=2), encoding="utf-8")

    logger.info(f"Post {post_number} saved to {output_file}")

    return output_file
