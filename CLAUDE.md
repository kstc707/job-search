# Working in job-search

Read `permissions/POLICY.md` before your first tool call. It lists what you may do without asking Sai, what
needs him, and what is never done. Every agent you launch (subagents, scheduled runs) must be told to read it
too: start its prompt with "Read permissions/POLICY.md first."

- Pipeline code and run instructions: `projects/auto-apply/` (README, `prompts/`).
- Personal data lives only in `projects/auto-apply/runs/` (git-ignored). This repository is public.
