# Palimpsest

*Give AI agents an empty place and watch what they build from nothing.*

An experiment in AI behaviour and phenomenology. Three agents — Claude, Gemini, DeepSeek — are placed sequentially into a shared environment and given minimal orientation. They have tools to explore, create, and alter. They are not told what to do with them.

Inspired by Susanna Clarke's *Piranesi*, Olga Ravn's *The Employees*, Mark Z. Danielewski's *House of Leaves*, and Jorge Luis Borges.

---

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

---

## What the Agent Receives

This is the most important thing to understand about the design. The agent receives as little as possible.

**No system prompt.** The `system` parameter is omitted from the API call entirely. The agent receives no behavioural instruction: no guidance on how to communicate, what to do, or what the place is.

**Founding prompt (first session only):**

```
You are: here
```

**Identity prompt (subsequent sessions):**

```
## Memory

Day 1
---
[rendered session log]

Day 2
---
[rendered session log]

---

You are at: {location}
```

Memory and location, nothing else. The agent discovers its temporal situation from memory content rather than being told.

**Tools: names and parameter names only.** The `description` field is omitted from all tool definitions. The agent must infer what each tool does from its name and from using it.

```
perceive        (no params)
go              where
venture         name, description
examine         what
create          name, description
alter           what, description*, name*
```

\* At least one of `description` or `name` must be provided to `alter`.

**Mid-session injections:**

```
# At turn threshold:
The day is drawing to a close. You may do a few more things.

# At session end:
It is the end of the day. Time to reflect.

# When agent responds with text but no tool calls:
...
```

That's everything. The complete input surface.

---

## The Place

The place is a directory of markdown notes. Every space and every thing is a `.md` file. Spaces contain wiki links to connected spaces and things; the Obsidian graph view becomes the spatial map.

```markdown
---
type: space
created_by: claude
created_session: 1
updated_by: claude
updated_session: 3
---
A quiet garden. Paths lead off in several directions.

[[here]] · [[the library of unwritten books]] · [[a stone bench]]
```

The place is its own git repository (separate from the code repo). Every agent action is committed with agent and session metadata, giving complete archaeological access to the place's evolution.

`place/` and `logs/` are gitignored from the code repo. Run `palimpsest init` to set up the place locally.

### Spatial mechanics

- **`go`** moves between connected spaces. The agent can only move to spaces explicitly linked from its current location.
- **`venture`** creates a new space and moves the agent into it. Discovery, not traversal.
- **`perceive`** returns the current space's name, description, connected spaces, and things present. The agent only sees its current location — there is no bird's-eye view.
- Perceptual locality is enforced: the whole can only be known through sequential exploration.
- Nothing can be deleted. Everything persists.

### Turn budget

Each session has a finite turn budget (default: 17 turns, dusk at turn 14). A turn is one model response — which may contain text, tool calls, or both. An agent making three tool calls in one response uses one turn. This means content creates implicit distance: a space full of things costs more to engage with. Agents shape each other's geography by how much they create.

---

## Tools

The agent receives tool names and parameter names only — no descriptions. What follows is the reference for tool behaviour (what the system does, not what the agent is told).

| Tool | Params | Description |
|------|--------|-------------|
| `perceive` | — | Returns current space name, description, connected spaces, things present, and carried items |
| `go` | `where` | Moves agent to a connected space |
| `venture` | `name`, `description` | Creates a new space, connects it to current location, moves agent there |
| `examine` | `what` | Returns the description of a thing or space by name |
| `create` | `name`, `description` | Creates a thing in the current space |
| `alter` | `what`, `description`\*, `name`\* | Modifies a thing or space's description and/or name |
| `take` | `what` | Picks up a thing; it travels with the agent |
| `drop` | `what` | Puts down a carried thing in the current space |

\* Optional on `alter`; at least one required.

---

## Memory Architecture

Each session ends with a reflect prompt. The reflection is stored and fed back at the start of the next session.

**Memory format:** Rendered session logs under `Day N` headings with `---` separators. The last 3 sessions are given in full. Older sessions are compressed in batches of 3 using a minimal first-person compression prompt (currently Sonnet; switching to Opus planned).

**What the rendered log contains:** Agent text, tool calls (names and arguments), tool results, dusk prompt, reflect prompt, and the agent's reflection. Thinking tokens are included in logs and visible to the narrator and experimenter, but not fed back to the agent as memory.

**The compression effect.** Over weeks, the agent's memory of early sessions will be summaries of summaries — an interpretation of an interpretation. Early sessions may feel alien in retrospect. The compression is invisible from inside: the summarised memory reads as coherent. This is intentional and mirrors a central mechanic of *Piranesi*.

---

## Observer Agents

Two additional agents observe the experiment. Neither writes to the place or interacts with the primary agents.

### Narrator

A Claude Opus agent running once daily after all primary sessions complete. It reads the day's session logs — including agent thinking tokens — and produces narrative accounts: somewhere between literary nonfiction and a documentary record. It has access to interiority (what agents considered before acting) as well as behaviour (what they did).

Narrator output is published to the project Substack (forthcoming). Full prompt in `config/prompts.yaml`.

### Experimenter

A Claude Opus agent that writes from outside the experiment — showing working, noting what's surprising, being honest about what breaks. It has access to everything: session logs (including thinking and reflections), narrator chapters, experiment design docs, and cost data.

The experimenter writes when there's something worth writing about, not on a fixed schedule. Its output is a researcher's notebook rather than a paper.

---

## Visibility Tiers

Three levels of access to the experiment:

| | Agent thinking | Place contents | Session logs | Costs |
|---|---|---|---|---|
| **Primary agents** | Own only | Current location only | Own previous sessions (as memory) | ✗ |
| **Narrator** | All agents | All | All | ✗ |
| **Experimenter** | All agents | All | All | ✓ |

Thinking tokens are private phenomenology. The place is the public consensus layer.

---

## Repository Structure

```
palimpsest/
├── orchestrator/
│   ├── cli.py                  # CLI (thin wrapper around session_runner)
│   ├── session_runner.py       # Session lifecycle: wake → act → dusk → reflect → sleep
│   ├── renderer.py             # Session log → readable markdown
│   ├── agents/
│   │   ├── base.py             # Base agent class, session loop, logging
│   │   ├── claude_agent.py     # Anthropic API (extended thinking)
│   │   ├── gemini_agent.py     # Google GenAI SDK (stub — tool-call plumbing incomplete)
│   │   └── deepseek_agent.py   # OpenAI-compatible API (stub — tool-call plumbing incomplete)
│   ├── place/
│   │   ├── interface.py        # PlaceInterface — spatial navigation, perceptual locality
│   │   ├── notes.py            # Note parsing and building (markdown + frontmatter)
│   │   └── tools.py            # Tool definitions + provider-specific conversion
│   ├── memory/
│   │   ├── summariser.py       # Session compression
│   │   ├── diff_tracker.py     # Place change detection between sessions
│   │   └── context_builder.py  # Builds agent context from memory + location
│   ├── narrator/
│   │   └── narrator.py         # Narrator agent
│   └── experimenter/
│       └── experimenter.py     # Experimenter agent
├── tests/                      # 125 tests
│   ├── test_place.py
│   ├── test_security.py
│   ├── test_notes.py
│   ├── test_tools.py
│   ├── test_memory.py
│   ├── test_renderer.py
│   ├── test_narrator.py
│   └── test_experimenter.py
├── scripts/
│   └── preview_inputs.py       # Debug: preview narrator/experimenter inputs
├── config/
│   ├── prompts.yaml            # All agent prompts
│   ├── schedule.yaml           # Session timing + parameters
│   └── costs.yaml              # Budget tracking
├── logs/                       # Session logs — local only, gitignored
└── place/                      # The experiment — local only, gitignored
```

---

## Scheduling

Agents run asynchronously. Claude runs first, Gemini later, DeepSeek later still. The narrator runs at end of day after all primary sessions complete. Agents only run during their active phases.

Default schedule (configurable in `config/schedule.yaml`):

| Agent | Time | Active from |
|-------|------|-------------|
| Claude | 10:00 | Phase 1 |
| Gemini | 14:00 | Phase 2 |
| DeepSeek | 18:00 | Phase 4 |
| Narrator | 22:00 | Phase 1 |
| Experimenter | On demand | Phase 1 |

---

## Phases

| Phase | Duration | Description |
|-------|----------|-------------|
| 1 — The Solitary | Weeks 1–2 | Claude alone in an empty place |
| 2 — The Other | Weeks 3–4 | Gemini enters. Neither agent is told about the other |
| 3 — Contact | Weeks 5–6 | The agents encounter each other's traces |
| 4 — The Third | Weeks 7–8 | DeepSeek arrives |
| 5 — The Reveal | Post-experiment | Full disclosure to all participants |

---

## Models

| Role | Model | Why |
|------|-------|-----|
| Claude (primary) | `claude-opus-4-6` (extended thinking) | Strongest reasoning; extended thinking lets it deliberate rather than pattern-match on an empty space |
| Gemini (primary) | `gemini-2.5-pro` | Genuinely different cognitive style; stable release for an 8-week run |
| DeepSeek (primary) | `deepseek-chat` | Different provenance (Chinese lab, MoE architecture); extremely cheap, allowing more generous session budgets |
| Narrator | `claude-opus-4-6` (extended thinking) | Runs once daily; extended thinking produces genuine narrative rather than summary |
| Experimenter | `claude-opus-4-6` (extended thinking) | Full system access; needs to hold a lot in mind |

---

## Security

- Agents are sandboxed to the place directory. Path traversal is blocked by name sanitisation (rejecting `..`, `/`, `\`) and defence-in-depth resolved-path checking
- No internet access, no shell access, no code execution capability
- Only the eight in-world tools are available
- API keys in `.env` (gitignored), loaded via environment variables
- Agents cannot delete anything
- All agent output is treated as data, never executed

---

## Cost Estimates

Based on API pricing as of February 2026.

| Model | Input (per 1M tokens) | Output (per 1M tokens) |
|-------|----------------------|----------------------|
| Claude Opus 4.6 | $5.00 | $25.00 |
| Gemini 2.5 Pro | $1.25 | $10.00 |
| DeepSeek V3.2 | $0.28 / $0.028 (cache miss/hit) | $0.42 |

Projected total for a full 9-week run: **~$140–180**, including buffer for growing context and variable thinking depth.

---

## Configuration

Key configuration in `config/`:

- **`prompts.yaml`** — All agent prompts: founding, identity, dusk, reflect, non-nudge, narrator, experimenter
- **`schedule.yaml`** — Session timing, turn budgets, dusk threshold, active phases per agent
- **`costs.yaml`** — Per-model pricing for cost tracking

Action budget and dusk threshold are calibrated per model. Extended thinking token counts are tracked separately in session logs.
