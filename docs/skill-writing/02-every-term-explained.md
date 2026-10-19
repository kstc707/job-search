# 2. Every term explained

Part A is what a skill *is* (files and fields). Part B is the vocabulary from Matt's
[`writing-for-agents`](https://github.com/mattpocock/skills/blob/main/skills/productivity/writing-for-agents/SKILL.md),
explained plainly, with a data-analysis comparison and an example from your own skills where one exists.

## Part A: anatomy of a skill

A skill is a **folder** whose name is the skill's name. Only `SKILL.md` is required.

```
writing-skills/                 <- folder name = skill name
├── SKILL.md                    <- required: frontmatter + body
├── REFERENCE.md                <- optional sibling file, read only when SKILL.md points at it
├── scripts/lint_skill.py       <- optional code the skill tells the model to run
└── agents/openai.yaml          <- Matt only: settings for OpenAI's Codex. Claude ignores it.
```

Where the folder lives decides who gets it:

| Location | Who sees it |
|---|---|
| `<repo>/.claude/skills/<name>/` | Anyone working in that repo (your `tsenta-apply`) |
| `~/.claude/skills/<name>/` | You, in every repo on that machine |
| Uploaded to your claude.ai account | You, in claude.ai and synced into cloud sessions (your `sai-resume-tailor`) |
| Inside a plugin | Everyone who installs the plugin (how Matt ships his) |

### Frontmatter
The block between the two `---` lines at the top of `SKILL.md`. It is YAML: `key: value` lines.

| Field | Meaning |
|---|---|
| `name` | Lowercase, hyphens. Must match the folder. What you type after `/`. |
| `description` | **The only part always in the model's context.** The model reads it on every turn to decide whether to load the skill. |
| `disable-model-invocation: true` | Only a human typing `/name` can start it. The model can't, and no other skill can. |
| `argument-hint` | Placeholder shown after `/name` in the menu, e.g. `"What will the next session be used for?"` (Matt's `handoff`). |
| `allowed-tools` | Tools the skill may use without a permission prompt while it runs. |

### How a skill gets loaded (three levels)
1. **Always:** name + description, for every skill installed. This costs context on every turn.
2. **When the skill fires:** the body of `SKILL.md` is read in.
3. **When the body points at a file and the run needs it:** that sibling file is read.

Data comparison: level 1 is a table's **index**, level 2 is the row, level 3 is a join you only run when you need
those columns. You keep the index small because it is scanned every time.

## Part B: Matt's vocabulary

### Context window
Everything the model can "see" at once: system prompt, conversation, files read, tool results. It is limited, and
attention spreads thinner the more is in it.

### Context pointer
A line in the model's context that **names material that isn't loaded** and says **when to go get it**. A skill
description is a pointer. So is a line like "Code and background: `projects/auto-apply/`" in a skill body.
The *wording* decides how reliably the model follows it, not how good the target is.
*Data comparison:* a foreign key. Useless if it points at a row that doesn't exist (your `scripts/originality.py`).

### Branch
A distinct case the skill handles, so different runs take different paths. `tsenta-apply` has two branches at
step 4: Greenhouse/Ashby → 5a, everything else → 5b. A good description lists one trigger per branch.

### Context load vs cognitive load
- **Context load:** cost to the *model*: always-loaded words (descriptions, `CLAUDE.md`) paid on every turn.
- **Cognitive load:** cost to *you*: remembering which skills exist and when to type them.
Making a skill user-invoked moves cost from context load to cognitive load. Matt says spend cognitive load where
your judgement matters (e.g. before spending application credits).

### Steps vs reference
- **Steps:** ordered actions ("1. Decode the job description. 2. Build the evidence map...").
- **Reference:** facts and rules consulted when needed ("Header: kstc707@gmail.com...").
A skill can be all steps (a recipe), all reference (a rulebook), or both. Yours are both.

### Information hierarchy (the ladder)
Where each piece sits, ranked by how urgently the model needs it:
1. **In-file step:** in `SKILL.md`, in order.
2. **In-file reference:** in `SKILL.md`, looked up when needed.
3. **Disclosed reference:** in another file, read only when a pointer fires.

### Progressive disclosure
Moving material **down** that ladder, out of `SKILL.md` and behind a pointer. The test: *does every run need this?*
Yes → keep inline. Only some runs → move it out. Your `references/facts.md` is a good example.

### Co-location
Once you know what stays in a file, keep a topic's definition, rules and caveats **together under one heading**.
The opposite is scattering: your page-break rules sit in Layout rules *and* in the checklist *and* in Rejected
patterns.

### Sprawl
A document too long even though every line is true and unique. The fix is disclosure and splitting, not trimming
words.

### Completion criterion
The condition that tells the model a step is **done**. Two qualities:
- **Clarity:** can it tell done from not-done? "Understand the job" is vague. "`jd_map.md` exists and every
  responsibility has a row" is clear.
- **Demand:** how much work it forces. "Every bullet traces to a map row" forces more digging than "write bullets".

### Premature completion
The model ending a step early because it can see the steps after it and wants to get there. A clear criterion
stops it. Splitting steps into a separate skill or subagent (so the later steps aren't visible) is the heavier fix.

### Legwork
The digging a model does *inside* a step because the criterion demands it (reading every responsibility, checking
every number against `facts.md`), without that digging being written as its own step.

### Leading word
A short word the model already knows from training that carries a whole behaviour: **relentless**, **tight**,
**red**, **seam**, **tracer bullet**, **frontier**. Define it once (in **bold**), then reuse the word, not the
sentence. Prefer an existing word to an invented one; an invented word has to be fully defined.
*Your example:* **evidence map**. *A candidate you could add:* **core problem** (you already use it in steps 1, 3
and the summary rule; bolding it and reusing it makes it a leading word).

### Negation
Steering by "don't". Naming the banned thing puts it in context and makes it more likely. Write the target
behaviour instead. Keep "never" for hard guardrails that can't be phrased positively, and pair it with what to do.

### Single source of truth / duplication
Each rule lives in **one** place. Duplication costs tokens, drifts out of sync (your three emails), and makes a rule
look more important than it is.

### Environment as source of truth / cache
Files like `requirements.txt`, `--help` output, or `build.sh` already *are* the truth. A skill that copies them is a
**cache** and goes stale. Write down only what the model can't find by looking: unwritten conventions, the reason
for a choice, gotchas.

### Relevance and sediment
Every line should still bear on the task. **Sediment** is old lines that pile up because adding feels safe and
deleting feels risky. Your "Rejected patterns" list is where sediment will build up unless you prune it.

### No-op
An instruction the model already follows without being told ("be clear", "write professionally"). It costs
context and changes nothing. Test: delete the sentence; does behaviour change? If not, delete the whole sentence.
A weak leading word can be a no-op too ("be thorough"); a stronger word ("relentless") is the fix.

### Model-invoked vs user-invoked
- **Model-invoked:** description written for the model, with trigger cases. Model or you can start it.
- **User-invoked:** `disable-model-invocation: true`, description is a one-line human summary, only you can start it.
Test: *could the model usefully reach for this on its own?* If it only ever runs by hand, make it user-invoked.

### Router skill
When you have more user-invoked skills than you can remember, one user-invoked skill that lists the others and when
to use each. Matt's is `ask-matt`.

### Splitting (by sequence, by invocation)
- **By sequence:** break a long run of steps into two skills so the model can't rush step 3 to reach step 9.
- **By invocation:** split part off into its own model-invoked skill when it has its own trigger word or another
  skill needs to call it. (`sai-resume-tailor` split off from `tsenta-apply` is exactly this, and it's correct.)

Next: [tutorial and examples](03-tutorial-and-examples.md).
