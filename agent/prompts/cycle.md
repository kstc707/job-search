# Job-search agent: one cycle

Placeholders in braces are filled in the scheduled trigger's prompt, not stored here.
`{CONFIG}` is the person's config JSON (see `config.example.json`): their limits, thresholds
and daily cap. Nothing personal is stored in this repo.

## 0. Gate (always first, keep it cheap)
Run one query on the tracker `{TRACKER}`:
- rows with `Submit? = Yes` and Status in (Drafted, Approved, empty)
- rows with Status = Drafted and an empty Resume
- rows with Status = Waiting (an application still sending)

If all three are empty and the last scout run was today, reply `nothing to do` and stop.

## 1. Read state, not history
Read the State Index page `{STATE_INDEX}` and the memory page `{MEMORY}` (Decisions, Selection
Rules, Learned Lessons). Do not reread old conversation to rebuild state.

## 2. Track
For every Waiting row, read the Tsenta application status. Sent -> Applied. Failed -> write the
reason to the Failure Ledger `{FAILURES}`; second failure for the same employer + ATS -> set
`Submit? = No`, note `LEFT after 2 failures: <reason>`.
Interview Scheduled / Offer (or a recruiter reply) -> download every sent resume PDF to
`work/sent/<app>.pdf`, run `python -m jobagent bullets scan work/sent --success <all successful
apps> --families <app=family,...> --out LIB.json`, and write its bullets to `{BULLETS}`.

## 3. Apply (Yes rows only)
Check the posting is still open. Apply with `apply-with-custom-resume` using the exact PDF on
the row. The PDF on the row is the record of which bullets were used.

## 4. Scout and score (once a day, at most `daily_cap` jobs, default 15)
Tsenta recommendations, then web search for the same targets. Save each job description to
`jds/<slug>.md`: a JSON header with the feed fields (`title`, `companyName`, `locations`,
`yearsOfExperienceMin`, `degreeRequirements`, `sponsorship`, `clearanceRequired`,
`datePosted`), a blank line, then the posting text. Skip anything already in the tracker.
Run the pre-build gate (no model tokens):

    python -m jobagent rank jds/*.md --config {CONFIG} --facts <facts.md>

It drops every job that fails a knockout (citizenship, clearance, sponsorship when needed,
too many years, degree, senior title, student-only) or scores under `thresholds.build`, and
returns the rest best first, capped. Build resumes only for those. Optionally ask the research
agent for a hiring signal (0-1) on each.

## 5. Build, audit and score resumes
Sub-agents, 4-5 jobs each, using the resume skill. Bullet wording may repeat an earlier resume
only if `python -m jobagent bullets reusable LIB.json --family <ai|ds|da>` lists it (proven
success rate). Every PDF must pass:

    python -m jobagent audit <tex> --facts <facts.md> --example <example.tex> \
        --pdf <pdf> --jd-map <jd_map.md> --others <resumes dir> --approved LIB.json

A failed audit goes back to the builder once. Re-run every audit in the main session after
all builders finish (builders run in parallel and compare against a folder that is still
changing). Then score the finished resume:

    python -m jobagent score jds/<slug>.md --config {CONFIG} --facts <facts.md> \
        --jd-map <jd_map.md> --tex <tex> --pdf <pdf> [--signal 0-1]

Attach the PDF and write the score to the row. `auto` (>= thresholds.auto): set `Submit? = Yes`
and apply in step 3 of the next run. `review` (>= thresholds.review): leave `Submit?` empty
for the person. `skip`: note why and do not apply.

### Keep Notion writes few
Every Notion write can need approval, so batch them: one `create-pages` call per run for all
new rows (properties, Notes, Score, and the Resume file IDs from `create-attachment` in the
same call), one `update-page` per row only when its Status changes, and one rewrite of the
State Index at the end.

## 6. Update state
Rewrite the State Index (under 2,000 tokens), append the run log, and refresh the Gap Ledger
`{GAPS}` with `python -m jobagent gaps <all jd_map.md>`.

## 7. Reply in 5-8 lines.
