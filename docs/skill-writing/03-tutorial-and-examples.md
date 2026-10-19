# 3. Tutorial and examples

Part A writes a skill from scratch, step by step. Part B rewrites real lines from your skills. Part C is practice.
The `writing-skills` skill in `.claude/skills/writing-skills/` runs this same process for you.

## Part A: write a skill from scratch

Worked example: a **cover-letter** skill, because your chat preferences already ask for "optional cover letter
draft" and there is no skill for it.

### Step 1: write down the job in one sentence and list the branches
> Draft a one-page cover letter for a specific posting from verified facts.

Branches (cases that make different runs go different ways):
- a posting is given → letter for that posting
- a resume was already tailored for it → reuse that run's `jd_map.md`
- you ask to shorten or change tone → edit an existing letter

**Done when** you can name every branch and each one leads somewhere different. Synonyms ("cover letter",
"application letter", "motivation letter") are *one* branch.

### Step 2: decide who starts it
Could the model usefully start it on its own? Yes: when you paste a JD and say "and a cover letter", it should.
So **model-invoked**: no `disable-model-invocation`, description written for the model.

### Step 3: write the first draft fast, then expect it to be bad
This is what a model typically produces when asked to "write a skill for cover letters":

```markdown
---
name: cover-letter
description: This skill helps create professional, compelling, and tailored cover letters for job
  applications. It should be used whenever the user wants a cover letter, application letter, motivation letter,
  or letter of interest, or mentions applying to a job, or pastes a job description. It uses Sai's verified
  facts and produces ATS-friendly output.
---

# Cover Letter Skill

## Overview
A cover letter is an important part of a job application. It introduces the candidate to the hiring manager and
explains why they are a good fit. This skill will help write excellent cover letters.

## Guidelines
- Be professional and clear.
- Use a confident but not arrogant tone.
- Don't use clichés like "I am writing to apply".
- Don't invent experience.
- Don't make it longer than one page.
- Make sure to tailor it to the job.
- Never use the same letter twice.
- Proofread carefully.
```

### Step 4: prune it, line by line, with the no-op test
Ask of each sentence: **if I delete it, does the model behave differently?**

| Line | Verdict |
|---|---|
| "## Overview / A cover letter is an important part..." | No-op. The model knows what a cover letter is. Delete. |
| "Be professional and clear." "Proofread carefully." | No-op. Default behaviour. Delete. |
| "confident but not arrogant" | Weak. Replace with the real standard: your "always oversell, I can deliver it". |
| "Don't use clichés like 'I am writing to apply'" | Negation that *names* the cliché. Replace with the target: how the letter opens. |
| "Don't invent experience." | Hard guardrail, but say it positively and point at the source: facts come from `facts.md`. |
| "Don't make it longer than one page." | Say the target: "one page, 3–4 paragraphs". |
| "Make sure to tailor it" / "Never use the same letter twice" | Same branch twice. Make it a checkable criterion instead. |
| description: "professional, compelling, and tailored", "application letter, motivation letter, letter of interest" | Adjectives that trigger nothing, synonyms of one branch. Cut. "mentions applying to a job" is too broad (it would fire on every resume request). |

### Step 5: add the parts that actually change behaviour
- A **leading word**: reuse **core problem** and **evidence map** from `sai-resume-tailor`, so the two skills think
  the same way.
- **Steps with completion criteria.**
- A **pointer** to the facts file rather than copying facts in.

### Step 6: the result

```markdown
---
name: cover-letter
description: Draft a cover letter for a specific job posting. Use when Sai asks for a cover letter, or asks to
  shorten or retone one.
---

Facts come only from `sai-resume-tailor`'s `references/facts.md` (call the Skill tool with "sai-resume-tailor"
to load it). If a resume was tailored for this posting, reuse its `jd_map.md`.

1. Name the posting's **core problem** in one sentence. Done when it names what the team needs fixed, not the job title.
2. Pick the 2–3 **evidence map** rows that answer it best. Done when each row has a real number or deliverable.
3. Write one page, 3–4 paragraphs: open with the core problem and his strongest proof of solving it; one paragraph
   per chosen row; close with the specific team or product he wants to join. Write with full confidence: he can
   deliver everything he claims.
4. Check: every number appears in `facts.md`; the company name and role title match the posting exactly.

Deliver as `SaiTejaKoppolu_<Company>_CoverLetter.pdf` with a one-line note of any gap the letter avoided.
```

It is shorter, every line changes behaviour, and step 4 is a criterion the model can check.

### Step 7: test it by running it
Matt: "settle it by running the document, not by debate." Run the skill on two real postings. Wherever the output is
wrong, name the failure first (no-op? vague criterion? missing pointer? negation?) then fix that one thing.
Then run `python3 .claude/skills/writing-skills/scripts/lint_skill.py .claude/skills/cover-letter`.

## Part B: before and after, from your own skills

### 1. Description (sai-resume-tailor), 82 words → 41
Before:
> Tailor Sai Teja Koppolu's resume to a job description and deliver a polished PDF in his own Charter-font layout.
> Use whenever Sai pastes a job description, names a role or company he is applying to, asks for a resume, CV, or an
> updated/tailored version, asks to change bullets, projects, skills, or the layout of his resume, or needs
> application-form text (employment history, responsibilities) or a reference/outreach email for an application.
> Contains his verified facts, the LaTeX template, and his standing style rules.

After:
> Tailor Sai's resume to a job posting and build the PDF. Use when Sai shares a job description or a role he is
> applying to, asks to change his resume, or needs application-form text or an outreach email for an application.

Kept: all four distinct branches (new posting, edit resume, form text, outreach email). Cut: synonyms (resume / CV
/ updated / tailored version; bullets / projects / skills / layout), the font, and "Contains...", which the body
already shows.

### 2. Description (tsenta-apply), two options
Model-invoked, 35 words:
> Apply to jobs end to end with a tailored resume. Use when Sai asks to find and apply to jobs, apply to a specific
> posting or Tsenta job id, or test the auto-apply pipeline.

User-invoked (it spends credits, so you may want only `/tsenta-apply` to start it):
```yaml
description: Find jobs, tailor resumes and submit applications.
disable-model-invocation: true
```

### 3. Negation → positive target
| Before | After |
|---|---|
| Rejected: `Invented "realistic estimate" metrics or invented projects` | Every number and project comes from `facts.md`; a bullet without a number ends on the deliverable or the decision it fed. |
| `No line that holds only one or two words at the end of a bullet` | End every bullet on a line that is at least half full. |
| `Do not string the posting's responsibilities together into a list of verbs` | Each summary sentence makes one claim and gives its proof. |
| Keep as is (hard guardrail): `Never call apply-with-custom-resume without Sai's go-ahead for that job` | Already paired with what to do: get the go-ahead. |

### 4. Duplication → one home
Before: page rules in *Layout rules*, plus checklist items "Two pages: page 1 full; page 2 starts at a heading..."
and "Page 1 full; any overflow starts at a heading on page 2...".
After: one heading **Page shape** holding every page rule; the checklist says `- [ ] Page shape met`.

Before: three contact emails across three files.
After: the email lives only in `facts.md`; `v2-cycle.md` and your preferences say "email: as in facts.md".

### 5. Disclose a branch only some runs need
Before: *Related requests* (form history, outreach email) sits in the main body of every resume run.
After: move each to `requests/form-history.md` and `requests/outreach-email.md`, and leave one pointer:
> For application-form text or an outreach email, read the matching file in `requests/` instead of the workflow.

### 6. Sharpen a completion criterion
Before: `2. Build the evidence map in a scratch file jd_map.md: one row per responsibility → ...`
After: add the done line: `Done when every responsibility from step 1 has a row, each holding a fact from facts.md or GAP.`

### 7. Call skills by the tool
Before: `follow the sai-resume-tailor skill there`
After: `Call the Skill tool with "sai-resume-tailor", working in that folder.`

### 8. Fix stale pointers
- `scripts/originality.py`: add the script, or delete step 5's call and the checklist line. Today every run is
  told to pass a check it cannot run.
- `jobagent audit` / "cycle step 5 command": point at the real command, or remove step 5a.1.

### 9. A no-op from your chat preferences
`Strong action verbs`, `Concise bullets`, `Consistent formatting`, `Maintain a professional, modern tone` are what
the model does anyway when writing a resume. Your *specific* rules ("tools inline", "bold only deliverable lead-ins
and key metrics", "at most 2 lines") are the ones that change behaviour. Keep those.

## Part C: practice

Rewrite each line, then compare with the answer.

1. `Don't forget to check the page count.`
2. `Use this skill when the user wants a resume, a CV, a résumé, or an updated resume.`
3. `Be thorough when reading the job description.`
4. `Make sure the output is good before sending.`
5. In a skill used by every run: a 30-line section explaining the Greenhouse API, used only when the job is on Greenhouse.

<details><summary>Answers</summary>

1. Positive and checkable: `Run build.sh; it must report 2 pages.`
2. One branch, written four times. `Use when Sai asks for a resume.`
3. Weak leading word (no-op). Make the demand concrete: `List every responsibility in the posting; done when none
   is left out.`
4. No-op with no criterion. Replace with the real checks: `Every number appears in facts.md; build.sh reports 2 pages.`
5. Disclose it: move to `GREENHOUSE.md`, leave `For Greenhouse jobs, read GREENHOUSE.md.`
</details>

## Cheat sheet

1. One sentence for the job; list the **branches**.
2. Choose **model-invoked** or **user-invoked**.
3. Description: leading word first, one trigger per branch, nothing about internals.
4. Body: steps that each end in a **done when**; reference grouped by topic.
5. Move anything only some runs need into a sibling file behind a pointer.
6. Say what to do; keep "never" for real guardrails.
7. Each rule in one place; point at files instead of copying them.
8. Delete every sentence that fails the no-op test.
9. Run it on real tasks; name the failure, then fix it.
10. Run `lint_skill.py`.
