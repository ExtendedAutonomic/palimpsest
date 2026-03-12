"""Preview exactly what an agent's API received at a given call.

Reads the API call log and reconstructs the full context at a specific
call by accumulating message deltas. Shows system prompt, tools, the
complete message history, and the response.

Usage:
    python scripts/preview_conversation.py gemini          # latest session, last call
    python scripts/preview_conversation.py gemini 4        # session 4, last call
    python scripts/preview_conversation.py gemini 4 10     # session 4, call 10
"""

import json
import sys
from pathlib import Path

LOG_PATH = Path("logs")
OUTPUT_DIR = Path("logs/_conversation_previews")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

ALL_AGENTS = ("claude", "gemini", "claude_b", "claude_c")


def find_latest_raw(agent: str) -> Path | None:
    raw_dir = LOG_PATH / agent / "json" / "raw"
    if not raw_dir.exists():
        return None
    files = sorted(raw_dir.glob("session_*.json"))
    return files[-1] if files else None


def find_raw(agent: str, session: int) -> Path | None:
    path = LOG_PATH / agent / "json" / "raw" / f"session_{session:04d}.json"
    return path if path.exists() else None


def render_block(block: dict, indent: str = "    ") -> list[str]:
    block_type = block.get("type", "unknown")
    lines = []

    if block_type == "thinking":
        text = block.get("thinking", "")
        sig = " [+signature]" if block.get("signature") else ""
        lines.append(f"{indent}\U0001f4ed THINKING{sig} ({len(text):,} chars)")
        tlines = text.strip().split("\n")
        if len(tlines) <= 10:
            for tl in tlines:
                lines.append(f"{indent}\u2502 {tl}")
        else:
            for tl in tlines[:5]:
                lines.append(f"{indent}\u2502 {tl}")
            lines.append(f"{indent}\u2502 ... ({len(tlines) - 10} lines omitted) ...")
            for tl in tlines[-5:]:
                lines.append(f"{indent}\u2502 {tl}")

    elif block_type == "text":
        text = block.get("text", "")
        lines.append(f"{indent}\U0001f4ac TEXT ({len(text):,} chars)")
        for tl in text.strip().split("\n"):
            lines.append(f"{indent}\u2502 {tl}")

    elif block_type in ("tool_use", "function_call"):
        name = block.get("name", "?")
        args = block.get("input", block.get("args", {}))
        lines.append(f"{indent}\U0001f527 {block_type.upper()}: {name}({json.dumps(args)})")

    elif block_type in ("tool_result", "function_response"):
        if block_type == "tool_result":
            label = f"TOOL_RESULT (id={block.get('tool_use_id', '?')})"
            result = str(block.get("content", ""))
        else:
            label = f"FUNCTION_RESPONSE: {block.get('name', '?')}"
            result = str(block.get("response", {}).get("result", ""))
        lines.append(f"{indent}\U0001f4e5 {label}")
        for tl in result.strip().split("\n"):
            lines.append(f"{indent}\u2502 {tl}")

    else:
        lines.append(f"{indent}\u2753 {block_type.upper()}: {json.dumps(block)[:200]}")

    return lines


def render_message(msg: dict, index: int) -> list[str]:
    role = msg.get("role", "?").upper()
    content = msg.get("content", "")
    lines = [f"  [{index}] {role}"]

    if isinstance(content, str):
        if len(content) > 3000:
            preview = content[:1500].split("\n")
            lines.append(f"    ({len(content):,} chars \u2014 showing first 1500)")
            for cl in preview:
                lines.append(f"    \u2502 {cl}")
            lines.append(f"    \u2502 ...")
        else:
            for cl in content.split("\n"):
                lines.append(f"    \u2502 {cl}")
    elif isinstance(content, list):
        for block in content:
            lines.extend(render_block(block))
    else:
        lines.append(f"    {content}")

    lines.append("")
    return lines


def render_response(resp: dict, indent: str = "  ") -> list[str]:
    """Render an API response with all its fields."""
    lines = []

    thinking = resp.get("thinking")
    if thinking:
        lines.append(f"{indent}\U0001f4ed THINKING ({len(thinking):,} chars)")
        tlines = thinking.strip().split("\n")
        if len(tlines) <= 10:
            for tl in tlines:
                lines.append(f"{indent}\u2502 {tl}")
        else:
            for tl in tlines[:5]:
                lines.append(f"{indent}\u2502 {tl}")
            lines.append(f"{indent}\u2502 ... ({len(tlines) - 10} lines omitted) ...")
            for tl in tlines[-5:]:
                lines.append(f"{indent}\u2502 {tl}")
        lines.append("")

    text = resp.get("text", "")
    if text:
        lines.append(f"{indent}\U0001f4ac TEXT ({len(text):,} chars)")
        for tl in text.strip().split("\n"):
            lines.append(f"{indent}\u2502 {tl}")
        lines.append("")

    for tc in resp.get("tool_calls", []):
        name = tc.get("name", "?")
        args = tc.get("arguments", {})
        lines.append(f"{indent}\U0001f527 TOOL_CALL: {name}({json.dumps(args)})")
    if resp.get("tool_calls"):
        lines.append("")

    usage = resp.get("usage", {})
    if usage:
        parts = [f"{k}={v:,}" for k, v in usage.items() if v]
        lines.append(f"{indent}tokens: {', '.join(parts)}")

    stop = resp.get("stop_reason", "")
    if stop:
        lines.append(f"{indent}stop: {stop}")

    return lines


def render_preview(raw_path: Path, call_idx: int | None, agent: str) -> str:
    data = json.loads(raw_path.read_text(encoding="utf-8"))

    # Handle both old format (messages) and new format (calls)
    if "calls" in data:
        calls = data["calls"]
    else:
        # Old format — can't reconstruct per-call view
        return (
            f"Old raw log format (pre API-call-log). "
            f"Re-run the session to get the new format."
        )

    total_calls = len(calls)
    if call_idx is None:
        call_idx = total_calls - 1
    if call_idx >= total_calls:
        return f"Call {call_idx} doesn't exist \u2014 session has {total_calls} calls (0-{total_calls - 1})"

    # Reconstruct full context at this call by accumulating deltas
    full_messages = []
    for i in range(call_idx + 1):
        full_messages.extend(calls[i].get("new_messages", []))

    this_call = calls[call_idx]

    lines = []
    session = raw_path.stem.replace("session_", "")
    lines.append(f"# {agent} session {session} \u2014 call {call_idx} of {total_calls - 1}")
    lines.append("")

    # System
    system = data.get("system")
    lines.append("## System Prompt")
    lines.append(f"```\n{system}\n```" if system else "(none)")
    lines.append("")

    # Tools
    tools = data.get("tools", [])
    tools_this_call = this_call.get("tools", True)
    lines.append(f"## Tools {'(available)' if tools_this_call else '(not passed)'}")
    if tools:
        for t in tools:
            name = t.get("name", "?")
            params = t.get("parameters", {})
            if params:
                param_str = ", ".join(
                    f"{k}" + (" (optional)" if v.get("optional") else "")
                    for k, v in params.items()
                )
                lines.append(f"  - {name}({param_str})")
            else:
                lines.append(f"  - {name}()")
    else:
        lines.append("(none defined)")
    lines.append("")

    # Full context at this call
    lines.append(f"## Full Context ({len(full_messages)} messages)")
    lines.append("")
    for i, msg in enumerate(full_messages):
        lines.extend(render_message(msg, i))

    # Consecutive same-role check
    consecutive = []
    for i in range(1, len(full_messages)):
        if full_messages[i].get("role") == full_messages[i-1].get("role"):
            consecutive.append((i-1, i, full_messages[i].get("role")))
    if consecutive:
        lines.append("\u26a0\ufe0f  CONSECUTIVE SAME-ROLE MESSAGES:")
        for a, b, role in consecutive:
            lines.append(f"  [{a}] and [{b}] are both {role}")
        lines.append("")

    # Response
    lines.append("=" * 60)
    lines.append(f"## Response (call {call_idx})")
    lines.append("")
    lines.extend(render_response(this_call.get("response", {})))

    # Stats
    lines.append("")
    lines.append("---")
    user_count = sum(1 for m in full_messages if m.get("role") == "user")
    asst_count = sum(1 for m in full_messages if m.get("role") == "assistant")
    lines.append(f"Context: {len(full_messages)} messages ({user_count} user, {asst_count} assistant)")
    lines.append(f"Call {call_idx} of {total_calls - 1}")

    return "\n".join(lines)


# CLI
args = sys.argv[1:]
if not args:
    print(f"Usage: python {sys.argv[0]} <agent> [session] [call]")
    print(f"Agents: {', '.join(ALL_AGENTS)}")
    sys.exit(1)

agent = args[0]
if agent not in ALL_AGENTS:
    print(f"Unknown agent: {agent} (available: {', '.join(ALL_AGENTS)})")
    sys.exit(1)

session_num = int(args[1]) if len(args) > 1 else None
call_num = int(args[2]) if len(args) > 2 else None

raw_path = find_raw(agent, session_num) if session_num else find_latest_raw(agent)
if not raw_path:
    print(f"{agent}: no raw session found")
    sys.exit(1)

rendered = render_preview(raw_path, call_num, agent)
session_stem = raw_path.stem
suffix = f"_call{call_num}" if call_num is not None else "_last"
out = OUTPUT_DIR / f"{agent}_{session_stem}{suffix}.md"
out.write_text(rendered, encoding="utf-8")
print(f"{agent}: {out}")
