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
EXPERIMENTER_MODEL = "claude-sonnet-4-5-20250929"  # TODO: switch to opus for production
MAX_OUTPUT_TOKENS = 8192  # Posts can be longer than narrator chapters


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

        for log_file in sorted(agent_dir.glob("session_*.json")):
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

        readable_dir = agent_dir / "readable"
        for log_file in sorted(agent_dir.glob("session_*.json")):
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


def gather_cost_summary(log_path: Path, config: dict) -> str:
    """
    Build a cost summary the experimenter can reference.
    """
    pricing = config.get("costs", {}).get("pricing", {})
    lines = []
    total_cost = 0.0

    for agent_dir in log_path.iterdir():
        if not agent_dir.is_dir() or agent_dir.name.startswith("."):
            continue
        if agent_dir.name in ("narrator", "experimenter"):
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
                agent_output += tokens.get("output", 0)
                session_count += 1
            except Exception:
                continue

        input_cost = (agent_input / 1_000_000) * model_pricing.get("input", 0)
        output_cost = (agent_output / 1_000_000) * model_pricing.get("output", 0)
        agent_cost = input_cost + output_cost
        total_cost += agent_cost

        lines.append(
            f"{agent_name}: {session_count} sessions, "
            f"{agent_input + agent_output:,} tokens, ${agent_cost:.2f}"
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
) -> str:
    """
    Build the user message for the experimenter.

    Assembles everything the experimenter has access to:
    design docs, session logs, narrator chapters, previous
    posts, and cost data.
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

    # Narrator chapters (if any)
    if narrator_chapters:
        parts.append("## Narrator's chapters\n")
        for chapter in narrator_chapters:
            parts.append(f"### Chapter {chapter['chapter']}: {chapter['title']}\n")
            parts.append(chapter["content"])
            parts.append("")

    # Session logs
    if readable_logs:
        parts.append("## Session logs\n")
        for log_md in readable_logs:
            parts.append(log_md)
            parts.append("\n---\n")

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

    # Save the post
    output_file = experimenter_output_path / f"post_{post_number:04d}.md"
    output_file.write_text(post_text, encoding="utf-8")

    logger.info(f"Post {post_number} saved to {output_file}")

    # Log token usage
    usage = response.usage
    logger.info(
        f"Experimenter tokens — input: {usage.input_tokens:,}, "
        f"output: {usage.output_tokens:,}"
    )

    return output_file
