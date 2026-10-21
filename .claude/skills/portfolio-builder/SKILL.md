---
name: portfolio-builder
description: Turn an industry blueprint (an engineering blog post, an open-source repo, or a gap that keeps showing up in postings) into a real, runnable portfolio project with measured results, then record it as Built in Sai's Knowledge Base and frame it for every role family. Use when Sai shares engineering-blog or GitHub links to build from, asks for a project to close a skill gap, asks to update his master record, or when the seeker's Friday report picks the project of the week.
---

# Portfolio builder

A project is resume material only after it has run: real code, real public data (or a clearly
labelled simulation when the project is about methodology), and every number produced by that
code. Blueprints from Uber, Netflix, Etsy, Meta and others are models to build from; their
systems and results are theirs and never go into Sai's experience.

## Fixed places
- Repo: `kstc707/data-portfolio`, one folder per project. If it is not reachable from this
  session, build in `/home/user/data-portfolio/` (git init there), commit locally, and hand Sai
  a zip (`git archive`) and a git bundle (`git bundle create ... main`) before the session ends.
- Projects database: `collection://a3760833-61fa-4e1c-bc57-1ed0327c5d85`
  (all rows: `view://aba0f568-e316-4a86-8bd4-0b33945a6e1e`).
- Gap Ledger: `collection://cc2f945f-15ec-496d-bb3d-13e3fc95537b`.
- Master record: the "Master Record · every role" page under the Resume Knowledge Base
  (`3fe55fb9-8924-81f5-9339-d2ae2b828f45`); its format is in `references/master-record.md`.

## Workflow
1. **Pick and scope.** From each blueprint, name the core idea in one sentence and scale it to
   something one machine can run: 4 CPUs, no GPU, about 20 minutes per full run, 4 GB peak
   memory, at most 2 threads when builds run side by side. Choose a public dataset that is
   reachable from this machine (check with `curl -I` first). Without an API key, LLM steps use
   small local GGUF models through llama-cpp-python; keep a hosted path behind a flag marked
   "not run here".
2. **Planned row.** Create or update the project's row in Projects: Status Planned, Created for
   ("seeker: <gap>" or "seeker: industry blueprint (<source>)"), Source posting (the blueprint
   URL), Family, Domains, Stack, a One-liner with no result numbers, and a page body with the
   build plan and the results it will measure.
3. **Build.** One subagent per project, each given `references/build-brief.md` and a project
   brief (data, approach, what metrics.json must hold). Run at most three at a time on this
   machine. Builders work only in their own folder and run no git commands.
4. **Verify yourself** before believing a report: `pytest -q` passes in the project's venv,
   `results/metrics.json` exists and the README's numbers match it, nothing over 300 KB or any
   data or model file is about to be committed (`git ls-files --others --exclude-standard`).
   A result that went against the hope (a baseline that wins, a strategy that does not help)
   stays in the README as found.
5. **Commit** in the portfolio repo (one commit per batch), update the repo's top-level README
   table, and push when the repo is reachable.
6. **Built row.** Set Status Built, Repo (the folder's GitHub URL), Stack as built, and a
   One-liner carrying the measured numbers exactly as in metrics.json. Close the matching Gap
   Ledger row (Status "Closed (in facts.md)") when the project closes a gap.
7. **Master record.** Add the project as a row to the master record, one cell per role family,
   following `references/master-record.md`. If the Notion page cannot be written, write the
   updated table to a file and give it to Sai to paste.
8. **Tell Sai** per project: the headline result, test count, what was not run and why, and the
   "Understand before an interview" bullets from its README.

## Rules
- Never write an industry system, its scale or its numbers into Sai's experience. A blueprint
  can supply vocabulary for his real work only where that work matches it.
- Never fill in expected or typical numbers; a step that could not run is marked "not run here".
- Data, model weights, venvs and MLflow stores stay git-ignored.
