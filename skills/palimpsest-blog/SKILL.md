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
| Readable session logs | `D:\Code\palimpsest\logs\{agent}\obsidian_logs\session_NNNN.md` |
| Previous posts | `D:\Code\palimpsest\logs\experimenter\post_NNNN.md` |
| Compressed memories | `D:\Code\palimpsest\logs\claude\compressed_memory.md` |
| Output directory | `D:\Code\palimpsest\logs\experimenter\` |
| Image attachments | `D:\Code\palimpsest\logs\experimenter\attachments\` |
| Export script | `D:\Code\palimpsest\scripts\export_substack.py` |
| Export output | `D:\Code\palimpsest\exports\post_NNNN\` |

## Workflow

### Step 0: Clarify scope

Before reading any files, confirm the following with the user:

1. **Which sessions to cover** (e.g. "Claude 1 + Gemini 1"). If not specified, ask.
2. **Point in time** — what does the writer know at the time of writing? The post should not reference sessions or events beyond this point. If not specified, ask. For example: "written after Claude session 6 and Gemini session 1" means no references to Claude 7+ or Gemini 2+.
3. **Topic or angle** — is there a specific focus, or should the post find its own shape from the material?
4. **Anything to exclude** — specific sessions, topics, or material the user wants left out.

Do not proceed to Step 1 until scope is confirmed.

### Step 1: Gather context

The user will have specified which sessions to cover and the temporal scope in Step 0.

Read the following files:

1. **Experimenter prompt** - read in full. This is your voice, style guide, and quality standard. Internalise everything: the tone, the examples, and every bullet in "What to avoid."

2. **Design docs** - read all four. 

3. **Previous posts** - list `D:\Code\palimpsest\logs\experimenter\` and read any existing `post_NNNN.md` files. These give you continuity.

4. **Session logs** - read the readable markdown logs for the specified sessions at `D:\Code\palimpsest\logs\{agent}\obsidian_logs\session_NNNN.md` (where `{agent}` is `claude`, `gemini`, etc.).

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

Additional checks:

- **Images:** The post should have at least 2-3 image placeholders (screenshots, Obsidian graphs, session log excerpts). If it has fewer, identify where images would strengthen the post and add placeholders.
- **Narrative continuity:** Re-read the previous posts and check for consistency: pronouns, terminology, how things were described, back-references to earlier posts. Flag and fix any contradictions or false attributions (e.g. claiming the previous post asked a question it didn't).
- **Strengthening suggestions:** After completing the edit pass, think about what could make the post stronger or more interesting, including connections to other material in the vault (Insights note, design docs, narrator chapters, literary references, philosophical threads). Present these as a separate list of recommendations for the user to consider. Do not apply them automatically.

## Collaborative editing

After the formal workflow, the user will typically iterate on the post with you in real time. They may be editing the same file simultaneously in their editor. **Always re-read the file immediately before making any edit**, even if you read it moments ago. The version in your context may already be stale.

## Edit-only mode

The user may ask to just run the edit pass on an existing post. In that case: read the post and the full experimenter prompt, then do Step 4 only.

## Publishing to Substack

When the user is ready to publish, run the export script:

```
python scripts/export_substack.py <post_number>
python scripts/export_substack.py all
```

This strips frontmatter, converts Obsidian image embeds (`![[file|size]]`) to standard markdown, copies images to `exports/post_NNNN/images/` numbered in order of appearance, and reports any missing images. The output markdown can be pasted directly into Substack's editor. Images must be inserted manually at each `![...]` reference.
