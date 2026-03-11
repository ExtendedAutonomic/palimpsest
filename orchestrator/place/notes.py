"""
Note parsing and building for Palimpsest.

Everything in the place is a markdown note with YAML frontmatter.
This module handles reading, parsing, and constructing notes.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

_FRONTMATTER_RE = re.compile(r"^---\n(.*?)\n---\n?", re.DOTALL)
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


@dataclass
class ParsedNote:
    """A parsed markdown note."""
    note_type: str  # "space" or "thing"
    frontmatter: dict[str, Any]
    description: str  # For spaces: text before sections. For things: full content.
    spaces: list[str]  # Names of linked spaces (spaces only)
    things: list[str]  # Names of linked things (spaces only)
    raw: str  # Original file content


def parse_frontmatter(text: str) -> tuple[dict[str, Any], str]:
    """Extract YAML frontmatter and return (metadata, body).

    Uses yaml.safe_load for proper parsing of lists and quoted strings.
    Falls back to simple line parsing if yaml is unavailable.
    """
    match = _FRONTMATTER_RE.match(text)
    if not match:
        return {}, text
    yaml_block = match.group(1)
    body = text[match.end():]
    try:
        import yaml
        meta = yaml.safe_load(yaml_block) or {}
    except Exception:
        # Fallback: simple line parser for flat key: value pairs
        meta = {}
        for line in yaml_block.split("\n"):
            if ":" in line:
                key, _, value = line.partition(":")
                value = value.strip()
                try:
                    value = int(value)
                except (ValueError, TypeError):
                    pass
                meta[key.strip()] = value
    return meta, body


def parse_note(text: str) -> ParsedNote:
    """Parse a note into its components."""
    frontmatter, body = parse_frontmatter(text)
    note_type = frontmatter.get("type", "thing")

    spaces = []
    things = []
    description = body

    if note_type in ("space", "inventory"):
        # Split body into description and sections
        sections = re.split(r"\n## ", body)
        description = sections[0].strip()

        for section in sections[1:]:
            heading, _, content = section.partition("\n")
            heading = heading.strip()
            links = _WIKILINK_RE.findall(content)
            if heading in ("Spaces", "Connected Spaces"):
                spaces = links
            elif heading == "Things":
                things = links

    return ParsedNote(
        note_type=note_type,
        frontmatter=frontmatter,
        description=description,
        spaces=spaces,
        things=things,
        raw=text,
    )


def build_frontmatter(meta: dict[str, Any]) -> str:
    """Build YAML frontmatter string.

    Handles scalar values inline and lists as YAML sequences.
    Strings containing colons or other special characters are quoted.
    """
    lines = ["---"]
    for key, value in meta.items():
        if isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                # Quote items that contain colons or special chars
                escaped = str(item).replace('"', '\\"')
                lines.append(f'  - "{escaped}"')
        elif isinstance(value, str) and (':' in value or '"' in value or value.startswith('[')):
            escaped = value.replace('"', '\\"')
            lines.append(f'{key}: "{escaped}"')
        else:
            lines.append(f"{key}: {value}")
    lines.append("---")
    return "\n".join(lines)


def build_space_note(
    description: str,
    spaces: list[str],
    things: list[str],
    frontmatter: dict[str, Any],
) -> str:
    """Build a complete space note."""
    parts = [build_frontmatter(frontmatter), description]

    parts.append("\n## Connected Spaces")
    if spaces:
        for s in spaces:
            parts.append(f"- [[{s}]]")

    parts.append("\n## Things")
    if things:
        for t in things:
            parts.append(f"- [[{t}]]")

    return "\n".join(parts) + "\n"


def build_inventory_note(
    things: list[str],
    frontmatter: dict[str, Any],
) -> str:
    """Build an inventory note — like a space but with no Connected Spaces section."""
    parts = [build_frontmatter(frontmatter), "Things you carry with you."]

    parts.append("\n## Things")
    if things:
        for t in things:
            parts.append(f"- [[{t}]]")

    return "\n".join(parts) + "\n"


def build_thing_note(description: str, frontmatter: dict[str, Any]) -> str:
    """Build a complete thing note."""
    return build_frontmatter(frontmatter) + "\n" + description + "\n"
