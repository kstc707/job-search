# Decisions and rejected patterns: history

Why the rules are what they are. Read when changing a rule, not on a normal run.

- 2026-11-02 (later): Sai builds the projects himself. Planned projects are written straight onto the resume and
  listed in the delivery note; no Notion rows or build plans (they cost tokens and slowed every build). The ATS
  check and the AI check run on every resume before it is sent (rule 10).

- 2026-11-02: Knight Transportation rejected the resume in 5 days (applied 2026-10-27). The posting showed no title,
  so the build guessed "Operations Analyst"; the real title was "Dedicated Support Specialist". screen.py gave an
  empty or self-chosen title full marks, so the resume scored 96-100. Freight KPIs sat in Skills only, the first
  project was not a transportation one, 32 numbers were not in the knowledge base, the summary said 2+ years
  against the Profile page's 4+, and a known required gap (transportation-industry experience) was sent without a
  flag. A friend's resume for the same posting used the exact title, the posting's phrases word for word in every
  bullet, freight KPIs in bullets and two transportation projects. → "Hard rules first" at the top of SKILL.md;
  screen.py scores the exact title (empty = 0), posting phrases and domain terms in bullets; scripts/numbers.py
  checks every number against the knowledge base. Not copied from the friend's resume: invented metrics and domain
  claims on jobs that had no such work.

- 2026-10-19: goal is an interview call, not a job offer. Projects move to a Notion knowledge base, one page each;
  when none fits a posting, a planned project is designed from it and added to To build, written with no result
  numbers. The level decides where the oversell goes. Experience bullets run long and name mechanisms.
- 2026-10-19: one email everywhere (Profile page); dates use a plain hyphen.
- 2026-10-17: posting's tools may be used on real work; the old do-not-claim tool list is lifted. Three fixed roles
  (Data Analyst Intern, Graduate Assistant, Data Analyst at TCS from Jun 2022); no bachelor's line; the early client
  stays unnamed.
- Example bullets reused for a different kind of role → the example is now a placeholder skeleton.
- A page 2 holding only one project's two bullets → Page shape (two complete entries).
- Six bullets per role added to fill page 1 → bullet counts by level.
- The fellowship percentage shown → Profile page education line.
- Sep 2026 resume with 10 estimated metrics and two invented projects; each line failed the first interview
  question about it → numbers only from the knowledge base; planned projects carry no result numbers.
- 2026-10-19: the do-not-claim checks are removed. Every check now measures one thing: how likely the resume is to
  pass the automated filters (ATS score from `screen.py`, then the AI screen).
