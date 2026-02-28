# Palimpsest

*Give AI agents an empty place and tell them only this: if you wish to understand where you are, you must look; if you wish to understand what you are, you must decide.*

An experiment in AI phenomenology inspired by Susanna Clarke's *Piranesi*, Olga Ravn's *The Employees*, Mark Z. Danielewski's *House of Leaves*, and Jorge Luis Borges.

## Quick Start

```bash
# Install
pip install -e .

# Configure API keys
cp .env.example .env
# Edit .env with your keys

# Run a single test session (Claude, Phase 1)
palimpsest run --agent claude --once

# Run the daily schedule
palimpsest run --schedule

# View vault state
palimpsest vault --tree

# View session logs
palimpsest logs --agent claude --last 3

# Run the narrator
palimpsest narrate

# Check costs
palimpsest costs
```

## Structure

```
palimpsest/
├── vault/              # The shared place (Obsidian vault + git repo)
├── orchestrator/       # Python orchestration
│   ├── agents/         # Agent API integrations
│   ├── memory/         # Memory compression + context building
│   └── narrator/       # Narrator agent + output
├── logs/               # Raw session transcripts
├── config/             # Prompts, schedule, costs
└── analysis/           # Post-hoc analysis tools
```

## Phases

1. **The Solitary** (Weeks 1–2) — Claude alone in an empty vault
2. **The Other** (Weeks 3–4) — Gemini enters, neither told about the other
3. **Contact** (Weeks 5–6) — The agents discover each other
4. **The Third** (Weeks 7–8) — DeepSeek arrives
5. **The Reveal** (Post-experiment) — Full disclosure to all participants
