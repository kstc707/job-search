# Agentic vs. fixed-workflow resume benchmark

`workflow_test.py` builds resumes with **2 fixed API calls per job** (requirements, then resume)
and no agent loop. It reads the same skill rules, facts file and LaTeX template the agentic
builders use, runs on the same model (`claude-opus-5-5`), and grades every output with the
pipeline's own `jobagent audit` and `jobagent score`. It writes no cover letter, because the
current pipeline writes none. It never applies, and never touches Notion, Tsenta, or the
pipeline's own files.

`test_inputs/` and `test_outputs/` are git-ignored (they hold personal resume data).

## Run

```
pip install anthropic
export ANTHROPIC_API_KEY=...          # never commit it
python benchmark/workflow_test.py benchmark/test_inputs/*.md \
    --builder-rules <path to builder_prompt10.md>   # optional: the agentic builder's extra rules
```

Or pick random jobs: `--random 5 --jd-dir <folder of jds>` (add `--seed N` to repeat a pick).
Local model instead of the API: `--provider ollama --ollama-model qwen3:4b --out benchmark/test_outputs/qwen3_4b`
(needs `ollama serve` running; `--num-ctx`, `--num-predict`, `--think` tune it). Token counts come from Ollama's
`prompt_eval_count` / `eval_count`; there is no prompt caching.

Options: `--effort` (default `high`), `--max-tokens` (default 64000), `--out`.

Outputs per job in `test_outputs/workflow/<slug>/`: `requirements.json`, `jd_map.md`, the
`.tex` and compiled `.pdf`. Run-level `calls.json` (one row per API call: input, output, cache
read/write tokens, seconds, stop reason) and `results.json` (per-job totals plus pages, audit
pass, coverage, score). The script prints a summary table at the end.

The jobs picked for a run, and the filled-in comparison table, go in the git-ignored
`test_outputs/comparison.md`.

## Comparison template

Agentic: start a fresh session, run the 5 jobs, then `/cost` after each job (or once at the end
and divide by 5, noting which). Time with a stopwatch from your prompt to the final PDF.

| Job | Version | API calls / turns | Input tokens | Cache read | Output tokens | Est. cost ($) | Wall-clock (s) | Pages | Audit pass | Coverage | Score | Fix rounds needed |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| <job 1> | workflow | | | | | | | | | | | 0 |
| <job 1> | agentic | | | | | | | | | | | |
| ... | | | | | | | | | | | | |
| **Total** | workflow | | | | | | | | | | | |
| **Total** | agentic | | | | | | | | | | | |

Cost at Opus 5.5 rates: input $4 / MTok, cache read $0.20 / MTok, cache write ~$5 / MTok,
output $20 / MTok.

## Quality checklist (score each resume 0/1 per row, side by side)

Hide which version made which PDF before you judge (rename to A/B).

1. **Facts:** every title, employer and date matches facts.md (TCS Jun 2022 – Jul 2024, Graduate Assistant Nov 2024 – May 2026, no Pantech, no B.Tech line).
2. **Header:** the current email, phone and GitHub from facts.md; no LinkedIn.
3. **Summary:** starts "Data Analyst with 4+ years of experience", walks the posting's preferred qualifications in their wording, one real number, location/onsite terms if stated.
4. **Coverage:** each role (Shelby, Graduate Assistant, TCS) touches ~90% of the posting's core requirements with the posting's tool names.
5. **Interview lessons:** insider detail (JustWare, Criminal Court exclusion, joint-review report), an insight-to-decision story per role, posting phrases attached to real actions.
6. **Skills:** category names mirror the posting; nearly every listed tool appears; each line fits one row.
7. **Bullets:** bold lead-in, what/how/tools/result, at most 2 lines, no one-word last lines.
8. **Projects:** last, the most relevant 2–3, specific numbers, no repeat of experience lead-ins.
9. **Layout:** compiles; 2 pages; page 1 full; page 2 starts at a heading; spacing as in the template.
10. **No copying:** no sentence lifted from the example or another resume (audit `copies` / `near_duplicates` empty).
11. **Would you send it as is?** (yes = 1)

Totals: workflow ___ / 55, agentic ___ / 55. Note any job where one version needed a manual fix.
