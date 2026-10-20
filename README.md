# Job Search — AI Engineering & Data Science Portfolio

Working repo for job-search portfolio projects. See [PROJECT_IDEAS.md](PROJECT_IDEAS.md) for the
full shortlist of project ideas and guidance on which ones to prioritize per role type.

## Structure

```
projects/
  <project-name>/   one self-contained project per directory
```

Each project has its own README, dependencies, and tests. This repo is a monorepo of independent
portfolio pieces, not a shared codebase — nothing under `projects/` imports across project
boundaries.

## Projects

| Project | Track | Status |
|---|---|---|
| [llm-data-analyst](projects/llm-data-analyst) | AI Engineering + Data Science (hybrid) | Working scaffold |
| [gemma4-paper-track](projects/gemma4-paper-track) | AI Engineering research (Kaggle paper track) | Plan + tooling |
| [auto-apply](projects/auto-apply) | AI Engineering (agent pipeline + guardrails) | Working, tested |

## Agent team

Claude Code subagents in [`.claude/agents/`](.claude/agents) (adapted from the MIT-licensed
VoltAgent and wshobson subagent collections, rewritten for this pipeline):

| Agent | Job | Can't |
|---|---|---|
| [workflow-engineer](.claude/agents/workflow-engineer.md) | Changes `projects/auto-apply` code and tests as the process changes | Submit applications, write to Tsenta/Notion, weaken a safety check |
| [data-analyst](.claude/agents/data-analyst.md) | Reads the ledger and tracker snapshot, reports what gets responses | Modify any data; writes reports only under `runs/analysis/` |

Ask for one by name, e.g. "use the data-analyst agent to compare filler vs Tsenta response rates".

## Working on a project

```
cd projects/<project-name>
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Then follow that project's own README for setup and usage specifics.
