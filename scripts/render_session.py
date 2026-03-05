"""
Render (or re-render) a session log to readable markdown.

Usage:
    python scripts/render_session.py --agent claude --session 4
    python scripts/render_session.py --agent claude  # renders latest
"""

import argparse
from pathlib import Path

BASE_DIR = Path(__file__).parent.parent
LOG_PATH = BASE_DIR / "logs"

import sys
sys.path.insert(0, str(BASE_DIR))

from orchestrator.renderer import save_readable_log


def main():
    parser = argparse.ArgumentParser(description="Render a session log to readable markdown.")
    parser.add_argument("--agent", "-a", required=True, help="Agent name")
    parser.add_argument("--session", "-s", type=int, default=None, help="Session number (default: latest)")
    args = parser.parse_args()

    agent_log_dir = LOG_PATH / args.agent
    if not agent_log_dir.exists():
        print(f"No logs found for agent '{args.agent}'")
        sys.exit(1)

    if args.session is not None:
        log_file = agent_log_dir / f"session_{args.session:04d}.json"
    else:
        logs = sorted(agent_log_dir.glob("session_*.json"))
        if not logs:
            print(f"No session logs found for agent '{args.agent}'")
            sys.exit(1)
        log_file = logs[-1]

    if not log_file.exists():
        print(f"Log not found: {log_file}")
        sys.exit(1)

    readable_path = save_readable_log(log_file)
    print(f"Rendered: {readable_path}")


if __name__ == "__main__":
    main()
