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
 OBSERVE   outcome sync (Gmail → tracker), Gmail: did Sai send a draft? did anyone reply?
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
resume tailoring, ATS check, red-team review, gate, cloud form filler and the Chrome autofill extension. What is
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
- **Every submitted resume is arm A:** the posting shapes it, Sai's real record and Built
  projects fill it. For about half the jobs (`auto_apply.v2.arms assign`, a hash of the apply
  URL) the agent also builds an **arm-B target profile**: the resume the posting describes,
  stamped "not for submission", scored next to arm A, with a `gap_plan.md` of how Sai could
  make each missing claim true. Target profiles are never sent; their gaps feed the Gap
  Ledger and the learning projects.
- **Weekly gap → project loop.** Each target profile logs its gaps in the Gap Ledger (merged
  into one row per skill, `This week` +1). On Fridays the top gap that showed up in 3+ target
  profiles that week becomes next week's project (Status In progress); the agent builds it
  across the week, marks it Built, and from then on arm A can claim it. The first week is the
  buffer: it only collects. Form answers and outreach messages stay factual.
- Learning projects the agent builds and pushes (with results from code it ran) are marked
  Built and become usable in arm A right away; Sai gets an FYI with the repo link.
- No LinkedIn automation or scraping. No Tsenta (removed 2026-10-21).
- No second applications: `auto_apply.v2.dedupe` checks every found job against the whole
  Notion tracker (same posting, requisition id, repost on another board, 60-day company cooldown).
  The local ledger can't do this alone because `runs/` is empty in every fresh cloud session.

## Reading the results

Two kinds of insight. The **target profiles** show, job by job, what postings want that Sai's
record does not show yet (ATS score A vs B, and the gaps that repeat across jobs), which is
what the agent learns or builds next. For callbacks, most rejections give no reason, so the learning signal is **rates
by variant** (replies from people per application or per message) and **what people say**
when they reply. Expect small
numbers: a variant needs roughly 30 tries before a difference means much, and the agent is
told to mark small-sample beliefs as low confidence.
