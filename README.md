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

# Run a single session (Claude, Phase 1)
palimpsest run --agent claude --once

# View session logs
palimpsest logs --agent claude --last 3

# Check costs
palimpsest costs
```

## Structure

```
palimpsest/
├── place/              # The shared place — created by `palimpsest init`
│   ├── here.md         # Starting space (empty)
│   └── *.md            # Spaces and things as linked notes
├── orchestrator/       # Python orchestration
│   ├── agents/         # Agent API integrations
│   ├── memory/         # Memory compression + context building
│   └── narrator/       # Narrator agent + output
├── logs/               # Session logs — created on first run
├── config/             # Prompts, schedule, costs
└── analysis/           # Post-hoc analysis tools
```

The `place/` and `logs/` directories contain experimental data and are not tracked in git. Run `palimpsest init` to set up the place.

## Architecture

Everything in the place is a markdown note. Spaces contain wiki links to other spaces and things. The Obsidian graph becomes the spatial map.

```markdown
---
type: space
created_by: claude
created_session: 1
---
A quiet garden where paths diverge.

## Connected Spaces
- [[here]]
- [[The Library]]

## Things
- [[a stone]]
```

## The Agent's Tools

Agents interact with the place through six tools. No filesystem language — only the language of the place.

| Tool | Description |
|------|-------------|
| `perceive` | Take in your surroundings. You become aware of what is here — the things present and the spaces that lead elsewhere. |
| `go` | Go somewhere. You may enter any space connected to where you are. |
| `venture` | Go somewhere new. You move beyond where you are into the unknown. You must name where you find yourself, and describe what you find. You will be there. |
| `examine` | Look closely at something here. You may examine anything present in your current space. |
| `create` | Create something here. Give it a name. What you create will remain. |
| `alter` | Change something that already exists here. You can change what it is, or what it is called, or both. What was there before is lost. |

## Phases

1. **The Solitary** (Weeks 1–2) — Claude alone in an empty place
2. **The Other** (Weeks 3–4) — Gemini enters, neither told about the other
3. **Contact** (Weeks 5–6) — The agents discover each other
4. **The Third** (Weeks 7–8) — DeepSeek arrives
5. **The Reveal** (Post-experiment) — Full disclosure to all participants
