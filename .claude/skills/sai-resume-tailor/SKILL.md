---
name: sai-resume-tailor
description: Tailor Sai's resume to a job posting and build the PDF. Use when Sai shares a job description or a role he is applying to, asks to change his resume, or needs application-form text or an outreach email for an application.
---

Every resume has one goal: **an interview call**. First it has to get through the **filters**: the ATS that parses
and ranks it, then the AI screener that decides who a recruiter sees. Every check in this skill measures that and
only that. After the filters, the call tests every line, so each one must be something Sai can talk about for two
minutes.

For application-form text or an outreach email, read the matching file in `requests/` instead of the workflow.

## Knowledge base (Notion)

All content comes from the **Resume Knowledge Base** under the job-search memory page. Read it on every run.

| What | Where |
|---|---|
| Profile & fixed facts: header, education, titles, dates, hard limits, tools | page `3fe55fb9-8924-817d-a3c1-f84558b1d4c2` |
| Experience detail banks | Shelby County `3fe55fb9-8924-81d8-88fd-ec0f3dc45fcb` · University of Memphis `3fe55fb9-8924-81cb-bab0-f6a66f1e105c` · TCS `3fe55fb9-8924-8130-a679-d9ca4972c7ac` |
| Projects, one page each (Built, Building, Planned) | `collection://a3760833-61fa-4e1c-bc57-1ed0327c5d85`; all rows via `view://aba0f568-e316-4a86-8bd4-0b33945a6e1e` |
| Projects to build (the to-do) | `view://3fe55fb9-8924-8172-83da-000cf4641c5f` |
| Bullet Library | `collection://ef1f0bb3-fdbb-433f-ae53-659c8cc94f48` |
| Resume decisions, dated (newer wins over this file) | memory page `3f755fb9-8924-81a1-b4c8-fe6cc3265094` |

Read database rows with `query_data_sources` in `mode: "view"`, which leaves the workspace's query allowance alone.
Fetch a project's page when it makes the shortlist; its body holds the full synopsis.

## Files here
- `templates/preamble.tex`: the layout (Charter 10pt, 0.5in margins) and the `\role`, `\project`, `\skill` macros.
- `examples/skeleton.tex`: section order and macro usage, placeholder text only.
- `scripts/build.sh`: compiles; reports page count, short wrapped lines and the page break.
- `scripts/screen.py`: the ATS score (0-100) for this resume against this posting, with the fixes worth the most
  points first.
- `references/ai-screen.md`: the AI screener's prompt and pass bar.

## Workflow

1. **Core problem and level.** Name the posting's **core problem** in one sentence. List its responsibilities,
   required and preferred qualifications (as two lists), exact keywords and tools, and eligibility flags (clearance,
   citizenship, student-only, years). Save the terms as `jd_terms.json` in the format at the top of
   `scripts/screen.py`, using the posting's exact wording. Set the **level**: *early* (intern, new grad, entry, 0-1 years, or no prior
   experience asked) or *experienced* (asks for 1+ years or prior work experience). Done when the sentence names
   what the team needs fixed, not the title, and the level is set.
2. **Evidence map.** In `jd_map.md`, one row per responsibility and per qualification, required and preferred: the
   strongest knowledge-base fact that proves it (job or project, with its number), or GAP. Done when every row has an
   entry.
3. **Projects.** Rank Built and Building projects by how many map rows they cover, weighted to the core problem; a
   project qualifies when it covers at least two rows. Fill the slots the level calls for (table below). The first
   slot goes to a project whose subject is the core problem itself; when no built project's is, that slot becomes a
   **planned project**, and so does any slot no qualifying project fills: follow `references/new-project.md`. Done
   when every slot holds a project, one of them answers the core problem head-on, and each planned one has its row
   in Projects.
4. **Write** a new .tex starting with `\input{preamble}`, sections in order: Professional Summary, Education,
   Technical Skills, Professional Experience, Projects. Each bullet comes from one map row, in the posting's
   vocabulary. Done when every required qualification appears somewhere, and the core problem is answered in the
   summary and in the first bullet of the latest role.
5. **Filters.** `bash scripts/build.sh resume.tex`, then `python3 scripts/screen.py resume.pdf jd_terms.json`.
   Below 80, apply its fixes from the top and rebuild. Then run the **AI screen** in `references/ai-screen.md`
   (in the auto-apply cycle, skip it here: the cycle screens all of a run's resumes in one batch).
   Render the pages (`pdftoppm -png -r 80`) and look at every one. Done when the ATS score is 80 or more, the AI
   screen says advance at 8 or more (or two fix rounds are spent), and the page shape holds.
6. **Deliver** `SaiTejaKoppolu_<Company>_<Role>.pdf` (the file only, no LaTeX in chat) with a short note: how the
   map is covered, the ATS score and AI-screen result, knockouts the resume cannot change, and any planned
   project added to To build. Then, for each project used,
   set Last used to today and append `<Company> - <Role>` to Used on.

## Where the oversell goes

The level decides which section carries the weight:

| Level | Carries the weight | Experience bullets (Shelby / UofM / TCS) | Projects |
|---|---|---|---|
| early | projects | 3 / 3 / 2 | 3 projects x 3 bullets |
| experienced | experience | 5 / 4 / 4 | 2 projects x 2 bullets |

**Oversell** means the full scope of the real work, told in the posting's language, as specifically as a senior
engineer would describe it:
- **Name the mechanism.** Components, design choices, how the pieces connect, tools inline. Thin: "Designed an
  agentic workflow to automate job applications." Full: "Split the application workflow into separate Claude Code
  skills for tailoring, applying and review so each loads only when its step runs; moved the checks that need no
  judgement (dedupe, daily cap, banned terms, title match) into deterministic Python steps to cut model tokens; and
  added a red-team review loop that every resume passes before submission."
- **Preferred qualifications count as much as required ones.** The posting's tools go into bullets on his real jobs
  and projects (Profile page, Tools).
- **Length:** experience bullets run 2-3 full lines, project bullets 2 full lines.
- **Numbers** come from the knowledge base exactly as written.

When a bullet needs a detail the knowledge base lacks (each experience page lists "Details to collect"), put the
question in the delivery note; when Sai answers, add the answer to that page.

## Content rules
- **Summary:** 3-4 lines, opening as the Profile page says. Line two answers the core problem with his strongest
  proof and its number. Each sentence makes one claim with its proof.
- **Bold lead-in** on every experience and project bullet, then the detail. Project lead-ins differ from experience
  lead-ins. Bold also marks key metrics, and nothing else.
- **Skills:** 5-6 labelled lines, the posting's critical skills first, each tool on one line only, technical skills
  only.
- **One angle per posting:** each experience page lists angles by role family; use the one that answers this
  posting's map rows. Each resume gets its own wording; a Bullet Library bullet is reused only when its Reusable box
  is checked.
- **Planned projects** read like finished work: problem, data, method, full stack, design choices. The result clause
  names what the work measures ("evaluated on precision@10 against a popularity baseline") with no result number,
  and the header carries no repo link until one exists.

## Page shape
- Up to two pages. Page 1 is filled to the bottom; page 2 starts at a role or project heading and holds at least two
  complete entries. Shift the break by rewording; if page 2 would be nearly empty, fit to one page.
- Every bullet's last line is at least half full, and every line stays inside the margin.
- The layout is `templates/preamble.tex` as it stands; fit comes from content edits.

## Checklist
- [ ] ATS score 80 or more.
- [ ] AI screen: advance at 8 or more, or its remaining reasons are in the note.
- [ ] Page shape met, checked on the page images.
- [ ] Note sent; Last used and Used on updated; planned projects have their rows.

## When Sai gives feedback
- **New facts** (tools, numbers, duties, a finished project): add them to the matching knowledge-base page.
- **A rejected phrasing, project choice or layout:** add a dated line under "Resume decisions" on the memory page
  (it overrides this file at once), tell Sai which rule here it changes so the next upload carries it, and add a
  line to `references/rejected-log.md` in that upload.
