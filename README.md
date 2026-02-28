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

# Initialise the place
palimpsest init

# Run a single test session (Claude, Phase 1)
palimpsest run --agent claude --once

# View the place
palimpsest place --tree

# View session logs
palimpsest logs --agent claude --last 3

# Check costs
palimpsest costs
```

## Structure

```
palimpsest/
├── place/              # The shared place (its own git repo)
│   ├── _/              # Unnamed space
│   ├── here/           # Starting location
│   └── __/             # Unnamed space
├── orchestrator/       # Python orchestration
│   ├── agents/         # Agent API integrations
│   ├── memory/         # Memory compression + context building
│   └── narrator/       # Narrator agent + output
├── logs/               # Raw session transcripts
├── config/             # Prompts, schedule, costs
└── analysis/           # Post-hoc analysis tools
```

## The Agent's Tools

Agents interact with the place through seven tools. No filesystem language — only the language of the place.

| Tool | What it does |
|------|-------------|
| `perceive` | Take in your surroundings |
| `go` | Move to a known space, or go back |
| `venture` | Go somewhere new — into the unknown |
| `examine` | Look closely at something |
| `create` | Make a thing (with content) |
| `alter` | Change an existing thing |
| `build` | Make a new space (stays where you are) |

## Phases

1. **The Solitary** (Weeks 1–2) — Claude alone in an empty place
2. **The Other** (Weeks 3–4) — Gemini enters, neither told about the other
3. **Contact** (Weeks 5–6) — The agents discover each other
4. **The Third** (Weeks 7–8) — DeepSeek arrives
5. **The Reveal** (Post-experiment) — Full disclosure to all participants
