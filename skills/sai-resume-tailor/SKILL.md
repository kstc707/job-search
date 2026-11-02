---
name: sai-resume-tailor
description: Tailor Sai's resume to a job posting and build the PDF. Use when Sai shares a job description or a role he is applying to, asks to change his resume, or needs application-form text or an outreach email for an application.
---

## Hard rules first (from the Knight Transportation rejection, 2026-11-02)

The Knight resume scored ATS 100 and was rejected in five days. It named the wrong job ("Operations Analyst"
for a "Dedicated Support Specialist" posting whose title was not shown), kept the posting's freight KPIs in Skills
only, led with an off-domain project, and carried numbers that are not in the knowledge base. A friend's resume
for the same posting, which Sai supplied as passing the ATS, used four techniques worth copying (rules 1-3); never
copy his invented metrics. These rules
override anything below them.

1. **Exact title or stop.** Copy the posting's job title word for word into `jd_terms.json` `title`, and open the
   summary with it ("Dedicated Support Specialist with 4+ years ..."). If the posting does not show a title, find
   it (the application page, the acknowledgement email, the req id) or stop and ask Sai. Never guess a title.
   `screen.py` now scores an empty title as 0.
2. **Mirror the posting's phrases verbatim.** List every responsibility and qualification phrase exactly as the
   posting writes it ("weekly, monthly, quarterly, and annual performance reports", "queue monitoring", "invoice
   validation") in `jd_terms.json` `phrases`. Each one goes, word for word, into an experience or project bullet
   about real work. `screen.py` scores phrases found in bullets (Skills does not count).
3. **Domain terms live in bullets.** The posting's industry terms (cost per mile, dock productivity, trailer dwell,
   claims, prior authorization, ...) go in `jd_terms.json` `domain` and must appear in a bullet, not only in Skills.
   When the core problem belongs to an industry and no built project is in that industry, project slot 1 is a
   **planned project** in that industry (`references/new-project.md`); that is where those terms are true.
4. **Every number from the knowledge base.** Save the knowledge-base pages read this run to `kb.txt` (fetch output
   as text), then `python3 scripts/numbers.py resume.pdf kb.txt`. Any number it lists is removed or replaced by
   one the knowledge base holds. No estimates, no "about 60%", no counts a page lists under "Details to collect".
5. **Hard-requirement gaps are said before sending.** A required qualification mapped to GAP that a screener can
   reject on (industry experience, years, degree, license, clearance) goes in `jd_terms.json` `knockouts` and opens
   the delivery note and the tracker Notes as `LOW ODDS: <requirement>`. Sai decides whether it is sent.
6. **One consistent person.** Years in the summary as the Profile page says (4+); Education as the Profile page says
   (no bachelor's line); each role's title fits the work its bullets describe.
7. **Projects are exactly the posting's subject (Sai, 2026-11-02).** Every project on the resume is about the
   posting's core problem in the posting's domain: a support role for a freight carrier gets freight-operations
   reporting projects, a claims analyst role gets claims projects. Covering two map rows is not enough. A built
   project qualifies only when a recruiter would read its title and say "that is our work"; every slot no built
   project fills that way becomes a planned project designed from this posting (`references/new-project.md`).
8. **Every preferred qualification is mirrored (Sai, 2026-11-02).** When the posting lists preferred
   qualifications, each one appears in the posting's own words in the summary or Skills AND in at least one bullet.
   Put them all in `jd_terms.json` `preferred`; `screen.py` counts a preferred term as fully met only when it is
   also in a bullet. A preferred qualification with no fact behind it in the knowledge base goes to a planned
   project, never to an invented number.
9. **Shelby County title (Sai, 2026-11-02).** The role heading reads `Data Analyst`, with `Internship` on the line
   under it: `\role{Data Analyst}{Shelby County District Attorney General}{Memphis, TN}{2026 - Present}` then
   `\roletype{Internship}`. Never "Data Analyst Intern" in the heading, summary or Skills. Its bullets are written
   like any analyst job (mechanism, tools, result), not like coursework.
10. **Projects go straight onto the resume; both screens run on every resume (Sai, 2026-11-02).** Write the
   projects and the experience bullets that match the posting's skills directly into the resume. Sai builds and
   completes the projects himself (or with another assistant), so do NOT create Notion Projects rows, build plans,
   talking points or "To build" entries, and do not update Last used / Used on. A project the knowledge base does
   not hold as Built is written from `references/new-project.md` (finished-work voice, real public dataset, the
   posting's stack, a metric with no result number) and listed in the delivery note under "Projects to build".
   Every resume passes the **ATS check** (`screen.py` 80+) and the **AI check** (`references/ai-screen.md`, advance
   at 8+) before it is sent; neither is ever skipped.

What not to copy from any reference resume: numbers with no source (99.2% accuracy, 3.1x throughput), and domain
claims on jobs that had no such work (cost per mile at a university desk). They pass a filter and fail the call.

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
- `scripts/numbers.py`: lists every number on the resume that the knowledge-base text does not contain.
- `references/ai-screen.md`: the AI screener's prompt and pass bar.

## Workflow

1. **Core problem and level.** Name the posting's **core problem** in one sentence. List its responsibilities,
   required and preferred qualifications (as two lists), exact keywords and tools, and eligibility flags (clearance,
   citizenship, student-only, years). Save the terms as `jd_terms.json` in the format at the top of
   `scripts/screen.py`, using the posting's exact wording: `title` verbatim (rule 1), `phrases` (rule 2), `domain`
   (rule 3), `knockouts` (rule 5). Set the **level**: *early* (intern, new grad, entry, 0-1 years, or no prior
   experience asked) or *experienced* (asks for 1+ years or prior work experience). Done when the sentence names
   what the team needs fixed, not the title, and the level is set.
2. **Evidence map.** In `jd_map.md`, one row per responsibility and per qualification, required and preferred: the
   strongest knowledge-base fact that proves it (job or project, with its number), or GAP. Done when every row has an
   entry.
3. **Projects.** A project qualifies only when its subject is the posting's core problem in the posting's domain
   (rule 7); among those, rank by how many map rows they cover, preferred rows counting as much as required ones.
   Fill the slots the level calls for (table below). Every slot no qualifying built project fills becomes a
   **planned project** designed from this posting: follow `references/new-project.md`. Done when every project
   title reads as this team's own work.
4. **Write** a new .tex starting with `\input{preamble}`, sections in order: Professional Summary, Education,
   Technical Skills, Professional Experience, Projects. Each bullet comes from one map row, in the posting's
   vocabulary. Done when every required qualification appears somewhere, and the core problem is answered in the
   summary and in the first bullet of the latest role.
5. **Filters.** `bash scripts/build.sh resume.tex`, then `python3 scripts/numbers.py resume.pdf kb.txt` (must list
   nothing) and `python3 scripts/screen.py resume.pdf jd_terms.json`. Below 80, apply its fixes from the top and
   rebuild. Then run the **AI screen** in `references/ai-screen.md` (in a batch run one fresh-context screener may
   screen all of the run's resumes together, but every resume is screened before it is sent).
   Render the pages (`pdftoppm -png -r 80`) and look at every one. Done when the ATS score is 80 or more, the AI
   screen says advance at 8 or more (or two fix rounds are spent), and the page shape holds.
6. **Deliver** `SaiTejaKoppolu_<Company>_<Role>.pdf` (the file only, no LaTeX in chat) with a short note: how the
   map is covered, the ATS score and AI-screen result, knockouts the resume cannot change, and "Projects to
   build": each project on the resume that is not Built yet, with its dataset link and the exact resume lines.

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
- [ ] Summary opens with the posting's exact title (never a guessed one).
- [ ] `numbers.py` lists nothing: every number is in the knowledge base.
- [ ] Every posting phrase, preferred qualification and domain term is in a bullet, not only in Skills.
- [ ] Every project title reads as the posting team's own work (rule 7).
- [ ] Shelby County heading reads "Data Analyst" with "Internship" under it.
- [ ] Hard-requirement gaps written as `LOW ODDS:` in the note and tracker Notes.
- [ ] ATS score 80 or more.
- [ ] AI screen: advance at 8 or more, or its remaining reasons are in the note.
- [ ] Page shape met, checked on the page images.
- [ ] AI screen run: advance at 8+, or its remaining reasons are in the note.
- [ ] Note sent, with "Projects to build" listing every project that is not Built yet.

## When Sai gives feedback
- **New facts** (tools, numbers, duties, a finished project): add them to the matching knowledge-base page.
- **A rejected phrasing, project choice or layout:** add a dated line under "Resume decisions" on the memory page
  (it overrides this file at once), tell Sai which rule here it changes so the next upload carries it, and add a
  line to `references/rejected-log.md` in that upload.
