"""Find the largest single turn (by ellipsis count) per session."""

import json
from pathlib import Path

LOG_PATH = Path("logs/claude/json")

print(f"{'Session':>8} {'Max turn':>10} {'Ellipses':>10} {'~tokens':>10} {'of 4096':>8}")
print("-" * 52)

for log_file in sorted(LOG_PATH.glob("session_*.json")):
    data = json.loads(log_file.read_text(encoding="utf-8"))
    session = data["session_number"]
    
    max_ellipses = 0
    max_turn_idx = 0
    
    for i, turn in enumerate(data.get("turns", [])):
        text = turn.get("agent_text", "")
        count = sum(1 for line in text.split("\n") if line.strip() == "...")
        if count > max_ellipses:
            max_ellipses = count
            max_turn_idx = i
    
    # Each "...\n\n" is roughly 2-3 tokens
    est_tokens = max_ellipses * 2
    pct = (est_tokens / 4096) * 100
    
    print(f"{session:>8} {max_turn_idx:>10} {max_ellipses:>10} {est_tokens:>10} {pct:>7.1f}%")
