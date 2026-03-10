---
name: palimpsest-blog
description: Write an experimenter blog post for the Palimpsest project. Use when the user asks to write a blog post, experimenter post, or says something like "write post 2" or "blog about sessions 3-6". Also use when asked to edit or revise an existing Palimpsest blog post against the style guide.
---

# Palimpsest Experimenter Blog

Write blog posts about the Palimpsest experiment. Replaces the `palimpsest blog` CLI command.

## File Locations

| What                                | Where                                                                        |
| ----------------------------------- | ---------------------------------------------------------------------------- |
| Experimenter prompt (voice + style) | `D:\Vault\Projects\Active\Palimpsest\Experimenter Blog Prompt.md`            |
| Design docs                         | `D:\Vault\Projects\Active\Palimpsest\Palimpsest.md`                          |
|                                     | `D:\Vault\Projects\Active\Palimpsest\Palimpsest - Technical Architecture.md` |
|                                     | `D:\Vault\Projects\Active\Palimpsest\Palimpsest - Experimental Design.md`    |
|                                     | `D:\Vault\Projects\Active\Palimpsest\Palimpsest - Insights.md`               |
| Readable session logs               | `D:\Code\palimpsest\logs\{agent}\obsidian_logs\session_NNNN.md`              |
| Previous posts                      | `D:\Code\palimpsest\logs\experimenter\post_NNNN.md`                          |
| Compressed memories                 | `D:\Code\palimpsest\logs\{agent}\compressed_memory.md`                       |
| Output directory                    | `D:\Code\palimpsest\logs\experimenter\`                                      |
| Image attachments                   | `D:\Code\palimpsest\logs\experimenter\attachments\`                          |
| Export script                       | `D:\Code\palimpsest\scripts\export_substack.py`                              |
| Progress note (blog plan)           | `D:\Vault\Projects\Active\Palimpsest\Palimpsest - Progress.md`               |
| Export output                       | `D:\Code\palimpsest\exports\post_NNNN\`                                      |

## Workflow

### Step 0: Clarify scope

Before reading any other files, read the **Blog Posts table** in the Progress note (`D:\Vault\Projects\Active\Palimpsest\Palimpsest - Progress.md`). This table maps out which sessions each post covers, working titles, topics, and status. Use it to pre-populate the scope for the requested post.

Present what the table says and confirm with the user:

1. **Which sessions to cover** — propose based on the table. If the post isn't in the table or the user hasn't specified which post, ask.
2. **Topic or angle** — propose the working title and topic from the table as a starting point. Check if the user wants to adjust the focus or let the material find its own shape.
3. **Anything to exclude** — specific sessions, topics, or material the user wants left out.

**Scope of topics (standing rule):** The topics listed in the Progress note and confirmed here are a starting point, not a ceiling. When reading the session logs in Step 1, look for anything else worth writing about — patterns, moments, connections, surprises — and include them if they strengthen the post. The plan is a guide, not a constraint.

**Temporal scope (standing rule):** Always write from the perspective of the covered sessions being the current point in time. The post should not reference sessions or events beyond the latest session it covers. For example, a post covering Claude 7–9 should not mention Claude 10+ or anything learned from later sessions. This does not need to be confirmed each time.

**No narrator references (standing rule):** The blog posts never mention the narrator agent. No references to narrator chapters, narrator excerpts, or the narrator's perspective. The narrator is a separate layer of the experiment and is kept entirely out of the experimenter's public writing.

Do not proceed to Step 1 until scope is confirmed.

### Step 1: Gather context

The user will have confirmed which sessions to cover in Step 0.

Read the following files:

1. **Experimenter prompt** - read in full. This is your voice, style guide, and quality standard. Internalise everything: the tone, the examples, and every bullet in "What to avoid."

2. **Design docs** - read all four. 

3. **Previous posts** - list `D:\Code\palimpsest\logs\experimenter\` and read any existing `post_NNNN.md` files. These give you continuity.

4. **Session logs** - read the readable markdown logs for the specified sessions at `D:\Code\palimpsest\logs\{agent}\obsidian_logs\session_NNNN.md` (where `{agent}` is `claude`, `gemini`, etc.).

5. **Compressed memories** - read `D:\Code\palimpsest\logs\{agent}\compressed_memory.md` if it exists. This is the lossy, compressed version of older sessions that the agent actually receives as memory. 

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

**Accuracy against session logs (standing rule):** When making a specific claim about what an agent said, did, or felt, go back to the session log and verify it before writing. Do not write from impression of what a session felt like. Check that quotes are accurate, that described patterns actually exist in the log, and that characterisations of agent behaviour (e.g. "the agent showed need", "the gaps start at fifteen lines") survive contact with the actual text. Most drafting errors come from writing an emotionally true summary that turns out to be factually wrong in the details.

**Narrative structure (standing rule):** Each post should tell a single story with a through-line, not summarise sessions individually. Before writing, identify the arc that connects the sessions being covered. Sections should advance that arc, not stand alone as independent observations. If sessions 7, 8, and 9 form an arc from desire → intimacy → dissolution, write one movement through all three, not three mini-essays. Weave literary or philosophical parallels into the narrative where they belong rather than giving them their own sections. The reader should feel pulled forward, not moved sideways between disconnected topics.

Save the draft to `D:\Code\palimpsest\logs\experimenter\post_NNNN.md` and tell the user it's saved.

### Step 4: Edit pass

Re-read the **full experimenter prompt** (`D:\Vault\Projects\Active\Palimpsest\Experimenter Blog Prompt.md`). Go through the draft and audit it against every section. For each violation, fix it. Save the edited version over the draft file and tell the user what you changed.

Additional checks:

- **Images:** The post should have at least 2-3 image placeholders (screenshots, Obsidian graphs, session log excerpts). If it has fewer, identify where images would strengthen the post and add placeholders. Every image must have a source attribution in the figure note. For screenshots from the experiment (Obsidian graphs, session logs), the description is sufficient. For external images (photos, manga panels, diagrams from other sources), include a linked source, creator, and license/copyright holder in parentheses after the description, e.g. `([Source](URL), work title, creator / copyright holder)`. The source link should point to where the image was found.
- **Narrative continuity:** Re-read the previous posts and check for consistency: pronouns, terminology, how things were described, back-references to earlier posts. Flag and fix any contradictions or false attributions (e.g. claiming the previous post asked a question it didn't).
- **Session log verification:** For every specific claim about agent behaviour, quoted paraphrase, or described pattern, verify it against the session log. If characterising a pattern across sessions, check each session individually. Common errors: attributing emotions or states the agent never expressed, misremembering when something first appeared, describing a pattern's timing or shape inaccurately (e.g. claiming gaps start large when they actually start small and grow).
- **Cross-post repetition:** Check whether any literary references, metaphors, philosophical parallels, or key observations in the draft were already used in a previous post. If a reference appeared before, either skip it entirely or make a brief callback (one sentence) rather than re-explaining it. Never re-establish a metaphor as though the reader hasn't seen it. The same Rumi poem should not be introduced twice across the series.
- **No narrator references:** Verify the draft contains no mention of the narrator agent, narrator chapters, or narrator perspective.
- **Strengthening suggestions:** After completing the edit pass, think about what could make the post stronger or more interesting, including connections to other material in the vault (Insights note, design docs, literary references, philosophical threads). Present these as a separate list of recommendations for the user to consider. Do not apply them automatically.
- **Sources and links:** Any factual claim about external tools, platforms, APIs, or company policies (e.g. how Anthropic handles thinking, how Google's summariser works) should have an inline link to a source. Session log quotes don't need sourcing, but claims about the world outside the experiment do.
- **Source freshness:** Check that all external sources are from the last six months. If a source is older, search for more recent information to verify the claim still holds. AI company docs and policies change frequently. Flag anything that has changed and update the post accordingly.
- **Fact-checking:** For any claim about the world outside the Place (how APIs work, what companies have said, technical mechanisms, pricing, model capabilities), verify it independently via web search. Do not rely on the Insights note, memory, or prior conversations as a source of truth for external facts. Things change. Check.
- **Footer links:** Every post should end with: Full codebase and [session logs](https://github.com/ExtendedAutonomic/palimpsest/tree/main/logs) are available on [GitHub](https://github.com/ExtendedAutonomic/palimpsest).

## Collaborative editing

After the formal workflow, the user will typically iterate on the post with you in real time. They may be editing the same file simultaneously in their editor. **Always re-read the file immediately before making any edit**, even if you read it moments ago. The version in your context may already be stale.

## Edit-only mode

The user may ask to just run the edit pass on an existing post. In that case: read the post and the full experimenter prompt, then do Step 4 only.
