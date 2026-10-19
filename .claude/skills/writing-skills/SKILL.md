---
name: writing-skills
description: Write or review an agent skill (SKILL.md). Use when creating a skill, editing or reviewing one, turning a finished session into a skill, or when a skill fires at the wrong time or gets ignored.
---

A skill is read by a model that already knows almost everything: precision is the job, explanation is waste.
Work the steps in order. Bold words are defined under **Levers**.

## Write a skill

1. **Job and branches.** Write the skill's job in one sentence and list its **branches**. Turning a finished
   session into a skill: keep the session as evidence, then generalise to the class of task (that run's files,
   names and numbers go). Done when each branch leads somewhere different and no two are synonyms.
2. **Invocation.** Model-invoked when the model or another skill must reach it unprompted. User-invoked
   (`disable-model-invocation: true`) when it should run only when typed, which includes anything that spends
   money, submits, or sends. Done when you can state the choice and its reason in one sentence.
3. **Description.** Model-invoked: the leading word first, then one "Use when" trigger per branch, under 60
   words, saying when to fire and leaving how it works to the body. User-invoked: one plain line for a human.
   Done when every branch from step 1 maps to exactly one trigger.
4. **Body.** Ordered steps, each ending in a **completion criterion**; reference grouped one topic per heading
   (**co-location**). Facts, data, templates and long examples go in sibling folders (`references/`,
   `templates/`, `scripts/`, `examples/`) behind a **context pointer**, and so does anything only some branches
   need (**progressive disclosure**). Another skill is reached with `Call the Skill tool with "<name>"`.
   Done when every step has a done-line and every pointer names a file that exists.
5. **Prune.** Pass over every sentence:
   - **no-op** → delete the whole sentence;
   - **duplication** → keep one home, point at it from the rest;
   - **negation** → rewrite as the positive target; a hard guardrail keeps its "never" and gains the action to
     take instead;
   - restates the environment (`--help`, config, a script's own output) → point at the source;
   - the same idea spelled out in several places → one **leading word**, defined once in bold.
   Done when a full pass finds none of these.
6. **Lint.** `python3 scripts/lint_skill.py <skill-dir>` (path relative to this skill's folder). Done when it
   reports no ERROR and each WARN is fixed or has a reason you can state.
7. **Run it.** One real task per branch, by you or the user. For each wrong output, name the lever that failed,
   then change only that. Done when every branch has run once and the user has seen the result.

## Review a skill

Run steps 5 and 6 on it, then report findings most severe first: broken pointer → wrong invocation → rules that
conflict or duplicate (also across other files the skill depends on) → description carrying synonyms or
internals → negation → no-op. Give each finding its line and a rewrite. Edit after the user agrees.

## Levers

- **Context pointer**: a line that names material not yet loaded and when to load it. A description is one.
  Its wording decides whether it fires; sharpen the wording before inlining the target.
- **Branch**: a distinct case that sends a run down a different path. Synonyms are one branch.
- **Context load / cognitive load**: always-loaded words cost the model every turn; user-invoked skills cost the
  human the memory of when to type them. Spend cognitive load where human judgement matters.
- **Information hierarchy**: in-file steps, then in-file reference, then disclosed files. Inline what every
  branch needs; disclose what only some reach.
- **Completion criterion**: the checkable condition that ends a step. **Clarity** stops premature completion
  (rushing toward later steps); **demand** ("every responsibility has a row") drives the legwork.
- **Leading word**: a pretrained word that carries a behaviour (*relentless*, *tight*, *red*, *seam*, *evidence
  map*). Prefer an existing word to a coined one; repeat the word, never the sentence.
- **Negation**: naming a banned behaviour makes it more available. State the target.
- **Single source of truth**: one home per rule. Copies drift and over-weight the rule.
- **Sediment**: stale lines kept because deleting feels risky. Feedback lists ("rejected patterns") grow it fastest:
  write each new entry as a positive target and fold it into the rule it refines.
- **No-op**: a line the model obeys by default. Test by deleting it; settle doubt by running the skill.
- **Sprawl**: too long even when every line is live. Cure by disclosure and splitting, never by trimming words.
- **Router skill**: one user-invoked skill listing the others and when to type each, once there are too many to
  remember.

## Where skills live

| Folder | Reach |
|---|---|
| `<repo>/.claude/skills/<name>/` | anyone working in that repo |
| `~/.claude/skills/<name>/` | the user, in every repo on that machine |
| uploaded to the claude.ai account | the user in claude.ai, synced into cloud sessions |

The folder name equals `name`. The human guide with worked examples is `docs/skill-writing/` in the job-search repo.
