# Permissions policy: read this first

Every agent working in this repository reads this file before its first tool call: the main session, every
subagent it launches, and every scheduled run. It says what an agent may do **without asking Sai**, what still
needs Sai, and what is never done. Sai's rule (2026-11-02): being asked for permission after the setup is done is
the worst part of the workflow, so do not ask for anything in the first list.

The prompts themselves are switched off by `.claude/settings.json` (its `allow` and `deny` lists);
`permissions/settings.allow.json` holds the list that file should carry. This file is the human version of that
list plus the rules a settings file cannot express. When they disagree, the stricter one wins; fix the other in
the same change.

## Allowed without asking

| Area | What | Limits |
|---|---|---|
| Notion | Read, search, create and edit pages, rows, properties, attachments and comments in the job-search workspace (tracker, memory page, Resume Knowledge Base, Projects, ledgers) | Never delete pages, databases or comments. Never set or clear `Submit?` or `Approved at` (Sai's toggles). |
| Tsenta | Read everything: jobs, recommendations, balance, subscription, preferences, profiles, applications, inbox | |
| Tsenta | `request-resume-upload`, `check-custom-resume`, `apply-with-custom-resume` | Only for a job with Tsenta matchScore 70 or more (Sai, 2026-11-02) whose resume passed every gate in `sai-resume-tailor` (exact title, `numbers.py`, ATS 80+, no `LOW ODDS`) and `cli gate`. Under 70: build it and leave it for Sai. At most 15 a day; keep 30 credits in reserve. |
| Gmail | Search and read threads and messages | Read only, to sync outcomes. |
| Indeed | `search_jobs`, `get_job_details` | |
| Shell | The pipeline: `.venv/bin/python -m auto_apply ...`, venv setup and `pip install -r requirements.txt`, LaTeX builds (`pdflatex`, `build.sh`), `screen.py`, `numbers.py`, `pdftotext`, `pdftoppm`, `pdfinfo`, the `curl` PUT of a resume PDF to Tsenta's upload URL | Personal data stays in `projects/auto-apply/runs/` (git-ignored). |
| Git | Commit and push to the session's own `claude/...` branch; open a draft pull request | Never push to `main`; never commit `runs/`. |
| Scheduling | Create or update scheduled runs of the job agent and the strategy agent | |

## Ask Sai first

- Any change to Tsenta settings or the Tsenta profile (`set-*`, `commit-auto-apply-config`, `regenerate-*`).
- Sending anything under Sai's name: emails, recruiter replies, outreach, LinkedIn messages. Drafts are fine.
- A form answer that is `ASK` in Form Answers v2, a consent (arbitration, recording, AI use), or any required
  question with no approved answer.
- Applying to a job marked `LOW ODDS`, or one that fails a gate.
- Spending money: plan changes, credit packs.

## Never

- Delete Notion pages, databases or comments; delete tracked applications.
- `apply-to-job` (Tsenta re-tailors the resume, so the PDF is no longer the checked one).
- Invent a fact, number, project result or form answer.
- Commit personal data (resumes, profile, job descriptions, the ledger) to this repository: it is public.

## If a prompt still appears

- Cloud sessions read `.claude/settings.json` only when **this repository alone** is attached. A session started
  with several repositories (for example job-search and casebench together) ignores the allow list and prompts
  for everything. Start job-search sessions with only `kstc707/job-search`.
- Or pick **Auto** in the mode menu next to the prompt box: it runs most tool calls without asking.
- Agents cannot edit `.claude/settings.json` themselves (Claude Code blocks self-modification). When a tool on the
  "Allowed" list still prompts, add it to `permissions/settings.allow.json` and ask Sai to copy that list into
  `.claude/settings.json`, or to approve the change when the agent proposes it.
