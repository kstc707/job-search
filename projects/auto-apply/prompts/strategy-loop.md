# Strategy agent: one cycle

**Read `permissions/POLICY.md` first**, then the Notion memory page `3f755fb9-8924-81a1-b4c8-fe6cc3265094`
(Sai's decisions there override this file).

Why this exists (Sai, 2026-11-02): the success rate is 0. Applying more of the same will not change that. This
agent treats the job search as an experiment: every application belongs to a **strategy arm** (a fixed set of
choices: which roles, which resume approach, which sources), outcomes are counted per arm, and each cycle the agent
shifts applications toward arms that get answers and replaces arms that do not, changing **one variable at a time**
so the next result says what caused it.

## Fixed rules
- Never change a fact rule: employers, dates, degrees and numbers come from the knowledge base; no invented content.
  Strategies change *which jobs* and *how real facts are presented*, never the facts.
- At most 4 active arms. At most one new arm per cycle, and it differs from its parent arm in exactly one variable.
- Retire an arm only with evidence: 15 or more decided applications, 0 positive, and the lowest posterior mean.
- An arm with a positive outcome is never retired in the same cycle.

## Variables an arm can set
role family and title keywords · seniority filter (entry / ≤2 years / unstated) · industry focus · location tier
order · posting age (≤24 h, ≤72 h) · source (Tsenta, company boards, Indeed) · resume approach (one page vs two,
project-weighted vs experience-weighted, summary angle) · project mode (built only vs planned allowed) ·
application timing (same day as posting vs batch).

## Steps
1. **Outcomes.** Run step 1 of `prompts/v2-cycle.md` (outcome sync from Gmail and the Tsenta inbox) so the tracker
   is current. Rejections that arrive within 24 hours of applying mean an automated knockout; note them per arm.
2. **Data.** Save all tracker rows (all-rows view, every page) to `runs/v2/tracker.json`, and the JSON block under
   **Strategy arms** on the memory page to `runs/strategies.json`.
3. **Score.** `.venv/bin/python -m auto_apply.v2.strategy runs/v2/tracker.json runs/strategies.json --slots <N>`
   where N is the next job run's application count (default 8). It prints per-arm sent / positive / rejected /
   silent / pending, the posterior mean, and the slot split for the next run.
4. **Diagnose.** For each arm read the Notes of its rejected and silent rows: knockouts (years, degree, industry),
   gaps the red-team accepted, fast rejections. Write one line per arm: what the evidence says.
5. **Decide.** Apply the fixed rules: retire at most one arm, add at most one new arm (one variable changed from
   the best arm, with a written hypothesis "If we change X, then Y, because Z"). If nothing has 5+ decided
   applications yet, change nothing and say so: deciding on 2 data points is noise.
6. **Write.** On the memory page: update the **Strategy arms** JSON block; set **Next run plan** to the slot split
   (arm → number of applications); append a dated entry to **Strategy log**: the table from step 3, the diagnosis,
   the decision and its reason. The job run (`prompts/v2-cycle.md`) reads Next run plan and tags each row with
   `[arm:<id>]` in Notes.
7. **Report** (3-5 lines): positive outcomes so far by arm, what changed and why, next run's split. Put "NEEDS SAI:"
   first if any interview, assessment or recruiter message is waiting.
