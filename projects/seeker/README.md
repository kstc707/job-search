# Seeker: an autonomous job-seeker experiment

**Question:** if an agent with Sai's knowledge and materials looks for a job on its own, in
the real market, what does it do, and what does it learn from rejections and silence? Does
it keep mass-applying, or does it start approaching hiring managers and team members? Which
skills does it decide are worth learning?

A simulation can only show what a model expects recruiting to be. This runs against real
postings and real people, as Sai, so it has to stay honest and within limits Sai sets.

## How it runs

A scheduled cloud session wakes once a weekday and follows [`prompts/daily.md`](prompts/daily.md):

```
 OBSERVE   outcome sync (Tsenta inbox → tracker), Gmail: did Sai send a draft? did anyone reply?
    ▼
 DECIDE    read Beliefs + signals + remaining weekly budget → pick today's moves,
    │      each with a hypothesis and a variant tag (v=...)
    ▼
 ACT       apply (≤3/day, ≤12/week)  ·  reach a person (drafts, ≤5 new/week)
    │      follow up (1 per person)  ·  build a learning project (public repo)
    ▼
 REFLECT   Journal entry, Beliefs rewritten with evidence, Needs Sai list
           Fridays: weekly report comparing variants
```

It reuses the auto-apply pipeline (`projects/auto-apply`): the v2 outcome sync, search,
resume tailoring, ATS check, red-team review, gate, form filler and Tsenta submit. What is
new is the loop around it: the agent chooses its own strategy and keeps a record of why.

## Where to watch it (Notion, under the job-search memory page)

| Page | What it shows |
|---|---|
| Job-Seeker Experiment | Charter (Sai's rules), Needs Sai, Open questions, **Beliefs** |
| Seeker Journal | One row per run: strategy, hypotheses, counts, signals, belief changes. Weekly reports. |
| Seeker Contacts | Every person it chose to approach, why, the draft, and what happened |
| Job Applications Tracker | Its applications, Notes starting `[seeker <date> v=<tag>]` |
| Projects (Resume Knowledge Base) | Learning projects it started (`Created for: seeker: <gap>`) |

## Limits (the Charter on the Notion page is the source of truth)

- Applies on its own, capped. Never sets `Submit?`/`Approved at` (those are Sai's v2 approvals).
- Outreach is drafted, never sent. Sai sends from Gmail; the agent sees it in Sent and tracks replies.
- **Resume experiment, two arms.** Each job is assigned by `auto_apply.v2.arms assign` (a hash
  of the apply URL) to arm A (the posting shapes the resume, Sai's real record and Built
  projects fill it) or arm B (the posting is the source: titles, bullets, tools, projects and
  numbers written to match it; name, contact, education, employers, dates and work
  authorization stay fixed, and no licenses, certifications or clearance). Sai discloses the
  experiment to anyone who calls back on an arm-B application. Form answers and outreach
  messages stay factual in both arms. `auto_apply.v2.arms tally` compares callback rates.
- Learning projects the agent builds and pushes (with results from code it ran) are marked
  Built and become usable in arm A right away; Sai gets an FYI with the repo link.
- No LinkedIn automation or scraping. No Tsenta settings changes.
- No second applications: `auto_apply.v2.dedupe` checks every found job against the whole
  Notion tracker (same posting, requisition id, repost on another board, 60-day company cooldown).
  The local ledger can't do this alone because `runs/` is empty in every fresh cloud session.

## Reading the results

The headline result is the **arm comparison**: callbacks from a person per application, arm A
vs arm B, with Fisher's exact test (`auto_apply.v2.arms tally`; read anything under 30
applications per arm as a hint). Because the arm comes from a hash of the job's URL, the
two arms see the same kinds of jobs, so a difference comes from the resume, not from where
it was sent. Beyond that, most rejections give no reason, so the learning signal is **rates
by variant** (replies from people per application or per message) and **what people say**
when they reply. Expect small
numbers: a variant needs roughly 30 tries before a difference means much, and the agent is
told to mark small-sample beliefs as low confidence.
