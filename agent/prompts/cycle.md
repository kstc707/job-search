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
Interview Scheduled / Offer -> run `python -m jobagent bullets outcome LIB.json --app <id>`
so the bullets on that resume earn a success.

## 3. Apply (Yes rows only)
Check the posting is still open. Apply with `apply-with-custom-resume` using the exact PDF on
the row. Record the bullets used: `python -m jobagent bullets use LIB.json <tex> --app <id> --title "<job>"`.

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
Rewrite the State Index (under 2,000 tokens), append the run log, refresh the Gap Ledger with
`python -m jobagent gaps <all jd_map.md>`, and sync the bullet library to `{BULLETS}`.

## 7. Reply in 5-8 lines.
