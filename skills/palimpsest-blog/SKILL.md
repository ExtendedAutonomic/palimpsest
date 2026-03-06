---
name: palimpsest-blog
description: Write an experimenter blog post for the Palimpsest project. Use when the user asks to write a blog post, experimenter post, or says something like "write post 2" or "blog about sessions 3-6". Also use when asked to edit or revise an existing Palimpsest blog post against the style guide.
---

# Palimpsest Experimenter Blog

Write blog posts about the Palimpsest experiment. Replaces the `palimpsest blog` CLI command.

## File Locations

| What | Where |
|------|-------|
| Experimenter prompt (voice + style) | `D:\Vault\Projects\Active\Palimpsest\Experimenter Blog Prompt.md` |
| Design docs | `D:\Vault\Projects\Active\Palimpsest\Palimpsest.md` |
| | `D:\Vault\Projects\Active\Palimpsest\Palimpsest - Technical Architecture.md` |
| | `D:\Vault\Projects\Active\Palimpsest\Palimpsest - Experimental Design.md` |
| | `D:\Vault\Projects\Active\Palimpsest\Palimpsest - Insights.md` |
| Readable session logs | `D:\Code\palimpsest\logs\claude\readable\session_NNNN.md` |
| Previous posts | `D:\Code\palimpsest\logs\experimenter\post_NNNN.md` |
| Compressed memories | `D:\Code\palimpsest\logs\claude\compressed_memory.md` |
| Output directory | `D:\Code\palimpsest\logs\experimenter\` |

## Workflow

### Step 1: Gather context

The user will specify which sessions to cover (e.g. "sessions 3-6") and optionally a topic or `--no-memories`. If it's not clear, ask.

Read the following files:

1. **Experimenter prompt** - read in full. This is your voice, style guide, and quality standard. Internalise everything: the tone, the examples, and every bullet in "What to avoid."

2. **Design docs** - read all four. Strip YAML frontmatter mentally; you only need the content.

3. **Previous posts** - list `D:\Code\palimpsest\logs\experimenter\` and read any existing `post_NNNN.md` files. These give you continuity.

4. **Session logs** - read the readable markdown logs for the specified sessions at `D:\Code\palimpsest\logs\claude\readable\session_NNNN.md`.

5. **Compressed memories** (optional) - read `D:\Code\palimpsest\logs\claude\compressed_memory.md` if relevant. Skip if the user says `--no-memories` or if sessions predate compression.

### Step 2: Determine post number

Look at existing posts in `D:\Code\palimpsest\logs\experimenter\` and take the next number.

### Step 3: Write the post

The experimenter prompt you read in Step 1 is the authority on voice, tone, structure, and format. Follow it completely. 

Save the draft (no frontmatter) to `D:\Code\palimpsest\logs\experimenter\post_NNNN_draft.md` and tell the user it's saved.

### Step 4: Edit pass

Re-read the **full experimenter prompt** (`D:\Vault\Projects\Active\Palimpsest\Experimenter Blog Prompt.md`). Go through the draft and audit it against every section. For each violation, fix it. Save the edited version over the draft file and tell the user what you changed.

### Step 5: Save final

Once approved, build frontmatter and save:

```yaml
---
type: experimenter
post: [number]
phase: [current phase]
date: [today, YYYY-MM-DD]
model: [ask user]
sessions: [comma-separated]
---
```

Write frontmatter + post to `D:\Code\palimpsest\logs\experimenter\post_NNNN.md` and delete the draft file.  If phase, model, or any other frontmatter field is unknown, ask the user.

## Edit-only mode

The user may ask to just run the edit pass on an existing post. In that case: read the post and the full experimenter prompt, then do Step 4 only.
