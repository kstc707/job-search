# Job-search agent: one cycle

Placeholders in braces are filled in the scheduled trigger's prompt, not stored here.

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

## 4. Scout (once a day)
Tsenta recommendations, then web search for the same targets. Selection rules from the memory
page. Sai needs no sponsorship: never skip a job for no-sponsorship language. For each pick,
fetch and save the JD to the row, then build its resume (step 5) before showing it to Sai.

## 5. Build and audit resumes
Sub-agents, 4-5 jobs each, using the `sai-resume-tailor` skill. Bullet wording may repeat an
earlier resume only if `python -m jobagent bullets reusable LIB.json --family <ai|ds|da>` lists
it (proven success rate). Every PDF must pass:

    python -m jobagent audit <tex> --facts <facts.md> --example <example.tex> \
        --pdf <pdf> --jd-map <jd_map.md> --others <resumes dir> --approved LIB.json

A failed audit goes back to the builder once. Attach passing PDFs to the row.

## 6. Update state
Rewrite the State Index (under 2,000 tokens), append the run log, and refresh the Gap Ledger
`{GAPS}` with `python -m jobagent gaps <all jd_map.md>`.

## 7. Reply in 5-8 lines.
