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

The user will specify which sessions to cover (e.g. "sessions 3-6") and optionally a topic. If it's not clear, ask.

Read the following files:

1. **Experimenter prompt** - read in full. This is your voice, style guide, and quality standard. Internalise everything: the tone, the examples, and every bullet in "What to avoid."

2. **Design docs** - read all four. 

3. **Previous posts** - list `D:\Code\palimpsest\logs\experimenter\` and read any existing `post_NNNN.md` files. These give you continuity.

4. **Session logs** - read the readable markdown logs for the specified sessions at `D:\Code\palimpsest\logs\claude\readable\session_NNNN.md`.

5. **Compressed memories** - read `D:\Code\palimpsest\logs\claude\compressed_memory.md` if it exists. This is the lossy, compressed version of older sessions that the agent actually receives as memory. Always read it unless the user explicitly says to skip compressed memories.

If any files failed to read or were missing, stop and report the failures. Do not proceed. If everything read successfully, continue to the next step.

### Step 2: Determine post number

Look at existing posts in `D:\Code\palimpsest\logs\experimenter\` and take the next number.

### Step 3: Write the post

The experimenter prompt you read in Step 1 is the authority on voice, tone, structure, and format. Follow it completely.

Build the frontmatter and include it at the top of the draft:

```yaml
---
type: experimenter
post: [number]
phase: [current phase]
date: [today, YYYY-MM-DD]
model: [model writing this post]
sessions: [comma-separated]
---
```

If phase, model, or any other frontmatter field is unknown, ask the user before writing.

Save the draft to `D:\Code\palimpsest\logs\experimenter\post_NNNN.md` and tell the user it's saved.

### Step 4: Edit pass

Re-read the **full experimenter prompt** (`D:\Vault\Projects\Active\Palimpsest\Experimenter Blog Prompt.md`). Go through the draft and audit it against every section. For each violation, fix it. Save the edited version over the draft file and tell the user what you changed.

## Collaborative editing

After the formal workflow, the user will typically iterate on the post with you in real time. They may be editing the same file simultaneously in their editor. **Always re-read the file immediately before making any edit**, even if you read it moments ago. The version in your context may already be stale.

## Edit-only mode

The user may ask to just run the edit pass on an existing post. In that case: read the post and the full experimenter prompt, then do Step 4 only.
