"""Count agent-produced ellipses per session, with breakdown."""

import json
from pathlib import Path

LOG_PATH = Path("logs/claude/json")

for log_file in sorted(LOG_PATH.glob("session_*.json")):
    data = json.loads(log_file.read_text(encoding="utf-8"))
    session = data["session_number"]
    
    turn_count = 0
    reflection_count = 0
    
    for turn in data.get("turns", []):
        text = turn.get("agent_text", "")
        for line in text.split("\n"):
            if line.strip() == "...":
                turn_count += 1
    
    reflection = data.get("reflection", "") or ""
    for line in reflection.split("\n"):
        if line.strip() == "...":
            reflection_count += 1
    
    total = turn_count + reflection_count
    num_turns = len(data.get("turns", []))
    print(f"Session {session}: {total} (turns: {turn_count}, reflection: {reflection_count}, num_turns: {num_turns})")
