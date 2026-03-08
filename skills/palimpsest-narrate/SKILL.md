---
name: palimpsest-narrate
description: Write a narrator chapter for the Palimpsest project. Use when the user asks to narrate, write a chapter, or says something like "narrate session 3" or "write chapter 2". The narrator chronicles what happens in the Place as literary nonfiction.
---

# Palimpsest Narrator

Write narrator chapters chronicling the Palimpsest experiment. Replaces the `palimpsest narrate` CLI command.

## File Locations

| What | Where |
|------|-------|
| Narrator prompt (voice + style) | `D:\Vault\Projects\Active\Palimpsest\Narrator Prompt.md` |
| Readable session logs | `D:\Code\palimpsest\logs\{agent}\obsidian_logs\session_NNNN.md` |
| Previous chapters | `D:\Code\palimpsest\logs\narrator\chapter_NNNN.md` |
| Output directory | `D:\Code\palimpsest\logs\narrator\` |

## Workflow

### Step 0: Clarify scope

Before reading any files, confirm the following with the user:

1. **Which sessions to cover** (e.g. "Claude 2-3" or "Gemini 1"). If not specified, ask.
2. **Which agent** — if not obvious from the sessions specified.
3. **Chapter number** — check the progress note or ask if unsure. The narrator chapters table in `Palimpsest - Progress.md` has the planned mapping.
4. **Anything to exclude or emphasise** — specific moments, themes, or material the user wants handled in a particular way.

Do not proceed to Step 1 until scope is confirmed.

### Step 1: Gather context

The user will have specified which sessions to cover in Step 0.

Read the following files:

1. **Narrator prompt** - read in full. This is your identity, voice, and every instruction for how to write. Internalise it completely before writing anything.

2. **Previous chapters** - list `D:\Code\palimpsest\logs\narrator\` and read any existing `chapter_NNNN.md` files. These give you narrative continuity.

3. **Session logs** - read the readable markdown logs for the specified sessions at `D:\Code\palimpsest\logs\{agent}\obsidian_logs\session_NNNN.md` (where `{agent}` is `claude`, `gemini`, etc.). These are your primary source. They include the agent's thinking, words, tool calls, results, and reflections.

If any files failed to read or were missing, stop and report the failures. Do not proceed. If everything read successfully, continue to the next step.

### Step 2: Determine chapter number

Look at existing chapters in `D:\Code\palimpsest\logs\narrator\` and take the next number.

### Step 3: Write the chapter

The narrator prompt (`D:\Vault\Projects\Active\Palimpsest\Narrator Prompt.md`) is your complete guide. Follow it.

Build the frontmatter and include it at the top of the draft:

```yaml
---
type: narrator
chapter: [number]
phase: [current phase]
date: [today, YYYY-MM-DD]
model: [model writing this]
sessions: [comma-separated]
---
```

If phase, model, or any other frontmatter field is unknown, ask the user before writing.

Save the draft to `D:\Code\palimpsest\logs\narrator\chapter_NNNN.md` and tell the user it's saved.

### Step 4: Edit pass

Re-read the **full narrator prompt** (`D:\Vault\Projects\Active\Palimpsest\Narrator Prompt.md`). Go through the draft and audit it against every section. For each violation, fix it. Save the edited version over the draft file and tell the user what you changed.

### Step 5: Save final

The draft is already saved as `chapter_NNNN.md` with frontmatter. Once the user approves (after any review edits are applied), the chapter is done. No rename or copy needed.

