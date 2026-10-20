# AI screen

The second filter after the ATS score: the LLM screener many applicant tracking systems now run before a person
reads anything. Run it in a fresh context (a subagent) given only two texts, the posting and the resume's extracted
text (`pdftotext resume.pdf -`), so it judges what the screener would see. In a batch run, one subagent screens
every resume of the run, paired by file name. With no subagent available, reread only those two texts first.

Prompt for the screener:

> You are the AI screening step of an applicant tracking system. A recruiter will only see candidates you
> advance. Read the job posting and the resume text. Score each part:
> - Required qualifications met, with evidence in the experience or projects (0-4)
> - Preferred qualifications met (0-2)
> - Level fit: years, scope and seniority match what the posting asks (0-2)
> - Evidence strength: concrete systems, tools in context and measurable outcomes rather than claims (0-2)
>
> Return JSON: {"score": 0-10, "decision": "advance" | "reject", "missing_required": [...],
> "reasons_to_reject": [three, strongest first], "fix_each": [one concrete edit per reason]}

The resume passes at `"advance"` with a score of 8 or more. For each reason to reject, apply its fix from the
knowledge base (reword toward the posting, move a term into a bullet, swap or add a planned project) and rescreen.
After two rounds, deliver anyway with the remaining reasons in the note.
