"""Preview the memory context each agent would receive on their next session."""

import sys
from pathlib import Path
from orchestrator.memory.summariser import build_agent_memory

LOG_PATH = Path("logs")
OUTPUT_DIR = Path("logs/_memory_previews")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

ALL_AGENTS = ("claude", "gemini", "claude_b", "claude_c")

# Accept optional agent name(s) as arguments, otherwise run all
agents = sys.argv[1:] if len(sys.argv) > 1 else ALL_AGENTS

for agent in agents:
    if agent not in ALL_AGENTS:
        print(f"{agent}: unknown agent (available: {', '.join(ALL_AGENTS)})")
        continue
    memory = build_agent_memory(agent, LOG_PATH)
    if not memory:
        print(f"{agent}: no memory to render")
        continue
    out = OUTPUT_DIR / f"{agent}_next_memory.md"
    out.write_text(memory, encoding="utf-8")
    print(f"{agent}: {out}")
