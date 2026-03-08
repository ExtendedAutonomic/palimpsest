"""Preview the memory context each agent would receive on their next session."""

from pathlib import Path
from orchestrator.memory.summariser import build_agent_memory

LOG_PATH = Path("logs")
OUTPUT_DIR = Path("logs/_memory_previews")
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

for agent in ("claude", "gemini"):
    memory = build_agent_memory(agent, LOG_PATH)
    if not memory:
        print(f"{agent}: no memory to render")
        continue
    out = OUTPUT_DIR / f"{agent}_next_memory.md"
    out.write_text(memory, encoding="utf-8")
    print(f"{agent}: {out}")
