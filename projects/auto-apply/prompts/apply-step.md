# Apply step: the Submit? toggle is the filter

Replaces step 3 ("Apply") of `agent/prompts/cycle.md`. Sai's rule (2026-10-14): when a row's
**Submit? = Yes**, the agent drafts the resume if the row has none, checks it, and submits.
No other approval. Rows without Submit? = Yes are never sent.

## Setup (once per run, only if there are Yes rows)
```bash
cd /home/user/job-search
git fetch -q origin claude/vigilant-feynman-x99oem
git worktree add -f /home/user/auto-apply origin/claude/vigilant-feynman-x99oem 2>/dev/null \
  || git -C /home/user/auto-apply checkout -q --detach origin/claude/vigilant-feynman-x99oem
cd /home/user/auto-apply/projects/auto-apply
python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt
mkdir -p runs
```
Then fill `runs/` (git-ignored; never commit it):
- `runs/instructions.txt` ← `resumeInstructions` from Tsenta `get-apply-preferences`
- `runs/profile_raw.json` ← `get-resume-profile` (default profile) → `.venv/bin/python -m auto_apply.cli profile runs/profile_raw.json --set diversityEquityInclusion.gender=Male` (Sai, 2026-10-14; the Tsenta tools cannot edit gender)
- `runs/answers.json` ← the JSON code block under **Form Answers** on the memory page
- `runs/never_claim.txt` ← the facts file's "Do not claim" list

## For each row with Submit? = Yes and Status in (Drafted, Approved, empty)
1. **Still open?** Closed or expired → Status Closed, Submit? No, note why. Next row.
2. **Resume.** Row has a Resume → download that exact PDF to `runs/<slug>/resume.pdf`.
   No Resume (e.g. Sai added the row himself) → read the JD (Tsenta `get-job-details` /
   `fetch-job-description`; if unreadable, note "Needs JD" and skip), build it now with the
   `sai-resume-tailor` skill, run `jobagent audit` as in step 5 of the cycle, attach it to the row.
3. **Gate.** `.venv/bin/python -m auto_apply.cli gate runs/<slug>/resume.pdf --url <apply url> --job-id <tsenta id>`
   Exit 2 → fix the resume once and re-gate; still blocked → Notes "Gate: <finding>", leave it.
4. **Route.**
   - **Greenhouse** (hosted `*.greenhouse.io` URL) or **Ashby** (`jobs.ashbyhq.com`) → our filler;
     free, saves a Tsenta credit:
     `.venv/bin/python -m auto_apply.filler.cli fill <url> --pdf runs/<slug>/resume.pdf --submit`
     - exit 3 (required question with no approved answer) → read `runs/<slug>/questions.json`.
       Draft job-specific answers from facts.md only into `runs/<slug>/answers.json` and put the
       drafts in the row's Notes as "Drafted answers — approve?"; standing questions and consents
       go under Open Questions on the memory page. Do not submit with unapproved drafts: set
       Submit? = No until Sai approves, then the next run retries.
     - "NOT SUBMITTED" (captcha or validation) → apply through Tsenta below instead.
     - Ashby "NOT SUBMITTED" → Tsenta always fails on Ashby: Notes "Manual apply: Ashby", leave
       the resume on the row.
   - **Everything else** → Tsenta: `request-resume-upload` → `cli upload <pdf> '<uploadUrl>'`
     → `check-custom-resume` → `apply-with-custom-resume { jobId|url, uploadId, profile: runs/profile.json }`.
     Never `apply-to-job` (it re-tailors and waits for approval).
5. **Record.** Filler sent → Status Applied, Notes "Sent via filler <time>". Tsenta → Status
   Waiting with the application id; step 2 of the next run turns it into Applied.
   Failures follow the two-strike rule and go to the Failure Ledger.

Daily cap and credit reserve from the cycle still apply; filler submissions count toward the
daily cap but cost no Tsenta credit.
