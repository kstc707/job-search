# Build brief (shared by every project)

Every project in this repo must be real: code that runs end to end on real public data (or a
clearly labelled simulation where the project is about methodology), with every reported
number produced by that code in this environment.

## Rules
1. Work only inside your project folder `/home/user/data-portfolio/<slug>/`. Do not touch other
   project folders. Do not run git commands (the repo is committed once at the end).
2. Environment: `cd <slug> && uv venv .venv --python 3.12 && uv pip install --python .venv -r requirements.txt`
   (fall back to python3 -m venv if uv fails). Pin versions in `requirements.txt`.
3. Machine: 4 CPUs, 15 GB RAM, no GPU, shared with two other builds. Use at most 2 threads
   (`n_jobs=2`, `OMP_NUM_THREADS=2`), keep peak memory under 4 GB and one full pipeline run
   under about 20 minutes. Down-sample data if needed and say so in the README.
4. Data goes in `data/` (git-ignored) via a download script; never commit data. Record the
   dataset source URL, version/date and row counts used in the README.
5. Layout: `README.md`, `requirements.txt`, `run.sh` (reproduces everything from download to
   `results/`), `src/<package>/`, `tests/` (pytest; tests must not need network or the full
   dataset: use small fixtures), `results/metrics.json` (written by the pipeline), and any
   small figures in `results/` (PNG, under 300 KB each).
6. **No invented numbers.** Every number in the README is copied from `results/metrics.json`
   or other pipeline output after a real run. If a step cannot run here (network, missing API
   key), keep the code, mark the step "not run here" in the README with the reason, and
   report it. Never fill in expected or typical values.
7. README sections: Problem (one paragraph, the industry system it is modelled on, linked),
   Data, Approach (with a small architecture diagram in Mermaid or ASCII), Results (table from
   metrics.json), How to run, Design choices and trade-offs, Limitations, and
   "Understand before an interview" (5-7 bullets Sai must be able to explain).
8. Run `pytest -q` and the full `run.sh` before reporting.

## Report back (under 300 words)
Folder; what ran end to end and how long it took; the full contents of `results/metrics.json`;
pytest result; anything not run and why; two resume bullets that use only measured numbers;
and the stack as a comma-separated list.
