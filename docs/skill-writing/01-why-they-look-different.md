# 1. Why Matt's skills look one way and yours look another

Compared: [mattpocock/skills](https://github.com/mattpocock/skills) (38 live skills) against your two:
`.claude/skills/tsenta-apply/SKILL.md` (in this repo) and `sai-resume-tailor` (your claude.ai account skill).

## The short answer

The two sets were built for different jobs, and they were built in different ways.

| | Matt's skills | Your skills |
|---|---|---|
| **What they teach** | A *way of thinking* (how to interview, debug, test). Mostly **process**. | A *specific procedure with your data* (which MCP tool, which file, which fact). Mostly **procedure + facts**. |
| **Who reads them** | Thousands of strangers, any model, any repo | You, one model, one pipeline |
| **How they were written** | Drafted, then pruned against a written style guide (`writing-for-agents`) and a repo rulebook (`CLAUDE.md`) | Grown from feedback sessions: each rejected resume added a rule |
| **Style guide they follow** | Matt's own: "delete what the model already knows" | Anthropic's `skill-creator`: "make descriptions a little bit pushy" so they trigger |

Length is **not** the main difference. Your bodies are 76 and 81 lines; Matt's median is 70.
The difference is *what kind of sentence* fills those lines.

## The numbers

| Measure | Matt (38 skills) | Yours (2 skills) |
|---|---|---|
| Body length | median 70 lines (7 to 160) | 76 and 81 lines |
| Skills only *you* can start (`disable-model-invocation: true`) | 23 of 38 | 0 of 2 |
| Description length, model-invoked skills | median 30 words | 66 and 82 words |
| Skills that push detail into sibling files | 15 of 38 | 1 of 2 (`sai-resume-tailor`: `references/`, `templates/`, `scripts/`) |
| Lines that steer with "never / do not / don't" | usually 5–15% | 12% (tsenta-apply), 21% (resume tailor) |
| Pointers to files that don't exist | 0 found | 1: `scripts/originality.py` |

(Measured with `.claude/skills/writing-skills/scripts/lint_skill.py`, which you can run yourself.)

## Ten specific differences

### 1. Who can start the skill
Matt decides, for every skill, whether **the model** may fire it on its own or only **you** can (by typing `/name`).
23 of his 38 are user-only. Those carry `disable-model-invocation: true` and a one-line description for humans:

```yaml
name: grill-me
description: A relentless interview to sharpen a plan or design.
disable-model-invocation: true
```

Both of yours are model-invoked. That is right for `sai-resume-tailor` (`tsenta-apply` has to reach it). It is
worth a second thought for `tsenta-apply`: it **spends real application credits**. A skill that costs money when
it fires is a classic candidate for user-only, so it runs only when you type `/tsenta-apply`.
(Trade-off: you would lose "find jobs and apply" in plain English triggering it.)

### 2. What goes in the description
The description is the only part of a skill that sits in the model's context **all the time**, on every turn,
whether or not the skill fires. Matt treats every word there as a cost.

Matt (24 words): *"Test-driven development. Use when the user wants to build features or fix bugs test-first, mentions
"red-green-refactor", or wants integration tests."*
The leading word comes first ("Test-driven development"), then **distinct** cases that should trigger it.

Yours (82 words) adds three things Matt cuts:
- **Synonyms of one case:** "asks for a resume, CV, or an updated/tailored version" is one trigger written three ways.
- **How it works inside:** "Tsenta searches, Claude tailors the PDF (sai-resume-tailor), guard checks run, then
  Greenhouse jobs go through our own form filler..." The body already says this.
- **What it contains:** "Contains his verified facts, the LaTeX template, and his standing style rules."

Why yours look like that: Anthropic's `skill-creator` tells authors that Claude "undertriggers" and to make
descriptions "a little bit pushy". Matt's view is that a sharper *word* triggers better than more words. Both views
are real; the fix that serves both is: keep every *distinct* trigger, drop the synonyms and the internals.

### 3. Leading words instead of spelled-out rules
Matt packs a whole behaviour into one word the model already understands, defines it once in **bold**, and then
reuses the word. In `grilling` the words are **design tree**, **rounds**, **frontier**. In `diagnosing-bugs` they
are **tight** and **red** ("a loop that goes red on this bug"). In `tdd`: **seam**, **tracer bullet**.

You already do this once, and it is your best writing: the **evidence map** in `sai-resume-tailor`
("every bullet must come from a row of this map"). Most of the rest is spelled out rule by rule.

### 4. Saying what to do, not what to avoid
Matt's rule: "Don't think of an elephant" puts the elephant in your head. Naming a banned behaviour makes it
*more* available to the model. He states the target instead, and keeps "never" only for hard guardrails.

Your resume skill's "Rejected patterns" list is entirely negatives, and some of it names the exact thing you do
not want (`Invented "realistic estimate" metrics or invented projects`). Your hard guardrails are legitimate
negatives and should stay: *"Never call `apply-with-custom-resume` without Sai's go-ahead."*

### 5. One source of truth
Matt keeps each rule in exactly one place. In `sai-resume-tailor` several rules live in two or three places:
- "Page 1 full" appears in Layout rules and in **two** checklist items.
- "Never change fonts/margins/spacing" appears under Files, Layout rules and the checklist.
- "Never cut explanation" appears in Content rules and again in Layout rules.

Across your setup the contact email has **three** different values in three places: `kstc707@gmail.com`
(resume skill), `saitejakoppolu24@gmail.com` (`projects/auto-apply/prompts/v2-cycle.md`, "One email
everywhere"), and `skppolu1@memphis.edu` (your chat preferences). Whichever the model reads last wins. The same
happens with metrics: the resume skill says invented metrics fail interviews, your chat preferences say every
bullet needs "a strong, believable metric" and allow "partly aspirational" content. Pick one and point the other
places at it.

### 6. Stale pointers (Matt calls this sediment)
- `sai-resume-tailor` tells the model to run `scripts/originality.py` (step 5 and the checklist). **That file
  does not exist** in the skill folder. Every run is told to pass a check it cannot run.
- `tsenta-apply` step 5a says "run the audit first (cycle step 5 command)" for `jobagent audit`. Step 5 of
  `v2-cycle.md` does not contain that command, and nothing in this repo defines `jobagent`.

Matt's repo rule is that pointers are kept true whenever something changes ("a router that lies").

### 7. Progressive disclosure (only load what this run needs)
Matt moves material that only *some* runs need into sibling files and points at it: `tdd` → `tests.md`,
`mocking.md`; `prototype` → `UI.md` or `LOGIC.md` depending on the branch.

`sai-resume-tailor` already does this well with `references/facts.md`, `templates/`, `scripts/`, `examples/`.
What's left inline but only used by some runs: "Related requests" (application-form history, outreach emails) and
the long "Rejected patterns" list. In `tsenta-apply`, each job takes **either** 5a (our filler) **or** 5b (Tsenta),
never both.

### 8. Every step ends in a checkable "done"
Matt's steps end with a **completion criterion** the model can verify. From `diagnosing-bugs`:
"Phase 1 is done when ... you can name **one command** ... that you have **already run at least once**."

You do this well in `tsenta-apply` with exit codes ("Exit 2 = blocked ... Fix the resume (never the rules) and
rerun"). The resume skill's step 5 ends with "Fix every issue in the checklist", which is good, but the checklist
has duplicate items and one item it cannot pass (`originality.py`).

### 9. Calling other skills
Matt always writes the exact action: *Call the Skill tool with "grilling".* (His `.agents/invocation.md` explains
that naming the tool raises the hit rate over a bare mention.) Yours says "follow the `sai-resume-tailor` skill
there", which the model usually but not always treats as an instruction to load it.

### 10. Story vs instruction
Your resume skill explains history: "Everything below reflects decisions he made after rejecting weaker versions",
"the Sep 2026 Google Search Quality resume used 10 estimated metrics". Matt keeps a *why* only when the model
could not find it by itself and it changes behaviour. Some of yours pass that test ("He said: always oversell, I can
deliver it" sets the tone in one line). Many are history the model does not need to act.

## What you already do better than Matt's average

- **Real data in a separate file** (`references/facts.md`) with a "do not claim" list. That is exactly the
  disclosed reference Matt recommends.
- **Scripts that check the output** (`build.sh`, the CLI gate with exit codes) instead of rules the model has to
  remember. Matt's `retro` skill calls this "default to building the check over writing the rule".
- **A feedback loop** ("when he rejects a phrasing ... add one line to Rejected patterns"). Matt's skills don't
  learn; yours do. The improvement is to make the loop write *positive* targets and prune old lines.

Next: [every term explained](02-every-term-explained.md).
