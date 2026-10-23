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
| [fedex_freight_project](fedex_freight_project) | Data Science (LTL demand, public data) | Data + EDA done, direction TBD |

## Working on a project

```
cd projects/<project-name>
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

Then follow that project's own README for setup and usage specifics.
