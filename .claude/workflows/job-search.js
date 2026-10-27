export const meta = {
  name: 'job-search',
  description: 'One job-agent v2 run: outcome sync, apply approved rows, find, screen, build resumes, batched red-team, Notion rows for Sai',
  whenToUse: 'Run the daily job search. args: {date: "YYYY-MM-DD", mode: "dry"|"live", maxJobs?, sources?, tsenta?}. Dry (default) builds up to 3 resumes and sends nothing.',
  phases: [
    { title: 'Sync', detail: 'setup runs/, Tsenta inbox -> tracker outcomes (v2 steps 0-1)' },
    { title: 'Apply', detail: 'live only: send rows Sai approved on the review page (v2 step 6)' },
    { title: 'Find', detail: 'career-page watcher + Jobright via Apify (v2 step 2)' },
    { title: 'Screen', detail: 'dedupe, target.py, employer apply URL, read full postings (v2 step 3)' },
    { title: 'Build', detail: 'one sai-resume-tailor agent per job + ats_check (v2 step 4.1-4.2)' },
    { title: 'Review', detail: 'ONE batched red-team reviewer for all resumes (v2 step 4.3)' },
    { title: 'File', detail: 'apply fixes, filler plan, Notion rows for Sai (v2 steps 4.4-5)' },
    { title: 'Report', detail: 'append the run report to the memory page Run Log (v2 step 7)' },
  ],
}

// The rules live in projects/auto-apply/prompts/v2-cycle.md; this script only fixes the order
// of the steps, which ones run in parallel, and what each stage hands to the next.

const a = args || {}
if (!/^\d{4}-\d{2}-\d{2}$/.test(a.date || '')) {
  throw new Error('Pass args.date as "YYYY-MM-DD" (scripts cannot read the clock).')
}
const DATE = a.date
const LIVE = a.mode === 'live'
const MAX_JOBS = a.maxJobs || (LIVE ? 8 : 3)
// Where jobs come from. Default: employers' own boards and Jobright. Tsenta and Indeed are opt-in.
const SOURCES = a.sources || ['boards', 'jobright']
// Tsenta submits only when asked: otherwise jobs outside the filler's ATSes go to Sai to send by hand.
const TSENTA = a.tsenta === true

const BASE = `You are one stage of a job-agent v2 run for Sai (date ${DATE}, mode ${LIVE ? 'LIVE' : 'DRY_RUN'}).
Work from the job-search repo root; CLI commands run from projects/auto-apply with .venv/bin/python.
Read the "Hard rules" in projects/auto-apply/prompts/v2-cycle.md and obey them. Sai's decisions in
projects/auto-apply/runs/v2/memory.md override that file. Do ONLY the step named below; other stages
do the rest. Everything personal stays in projects/auto-apply/runs/ (git-ignored); never commit it.
Tsenta submits are ${TSENTA ? 'ON: apply-with-custom-resume only, never apply-to-job (it rewrites the resume)' : 'OFF: never submit through Tsenta; a job the filler cannot send is route "manual"'}.`

const stage = {}
const mark = (name, from) => { stage[name] = budget.spent() - from; return budget.spent() }

const STR = { type: 'string' }
const STRS = { type: 'array', items: STR }
const INT = { type: 'integer' }
const NEEDS_SAI = {
  type: 'array',
  items: { type: 'object', properties: { company: STR, title: STR, why: STR }, required: ['company', 'title', 'why'] },
}

// ---- Sync ---------------------------------------------------------------------------------
phase('Sync')
let t = budget.spent()
const sync = await agent(`${BASE}

Step: v2-cycle step 0 (setup) and step 1 (outcome sync).
- Step 0: skip the git commands (use the current checkout); do the venv and the runs/ files.
- Fetch the Notion memory page once and save the parts later stages need to
  projects/auto-apply/runs/v2/memory.md: Resume decisions, Form Answers v2 (also into runs/answers.json),
  the Workflow step 5 attachment steps, and any other standing decisions. Later stages read only this file.
- Step 1 exactly as written, ending with projects/auto-apply/runs/v2/tracker.json up to date
  (re-read the tracker after your updates so it includes the new rows).
Set ok=false with the reason if setup fails (missing profile fields, a connector not available).`, {
  label: 'setup + outcome sync', phase: 'Sync',
  schema: {
    type: 'object',
    properties: { ok: { type: 'boolean' }, problem: STR, updates: INT, newRows: INT, unmatched: STRS, needsSai: NEEDS_SAI },
    required: ['ok', 'updates', 'newRows', 'unmatched', 'needsSai'],
  },
})
t = mark('sync', t)
if (!sync || !sync.ok) {
  return { stopped: 'sync', problem: sync ? sync.problem : 'sync agent died', tokens: stage }
}

// ---- Apply (live only) ----------------------------------------------------------------------
// Approved rows come from earlier runs; doing them first keeps today's credits and cap honest.
let applied = null
if (LIVE) {
  phase('Apply')
  applied = await agent(`${BASE}

Step: v2-cycle step 6 (apply approved rows), every sub-step, for review-queue rows with Submit? = Yes
AND Approved at set AND Status Drafted. Never set or change Submit? or Approved at. Two failures on the
same job -> leave it with the LEFT note.${TSENTA ? ' Report Tsenta credits left (get-application-balance).' : `
Tsenta is off: rows that need Tsenta get "NEEDS SAI: send by hand" with the apply URL in Notes; creditsLeft null.`}`, {
    label: 'apply approved rows', phase: 'Apply',
    schema: {
      type: 'object',
      properties: {
        sent: { type: 'array', items: { type: 'object', properties: { company: STR, title: STR, route: STR, status: STR }, required: ['company', 'title', 'route', 'status'] } },
        skipped: STRS, needsSai: NEEDS_SAI, creditsLeft: { type: ['integer', 'null'] },
      },
      required: ['sent', 'skipped', 'needsSai', 'creditsLeft'],
    },
  })
  t = mark('apply', t)
}

// ---- Find ---------------------------------------------------------------------------------
phase('Find')
const JOB_FILE = { type: 'object', properties: { file: STR, count: INT, problem: STR }, required: ['file', 'count'] }
const FINDERS = {
  boards: `Run the career-page watcher from projects/auto-apply:
.venv/bin/python -m auto_apply.v2.boards scan --watchlist watchlist.json --seen runs/v2/boards_seen.json --out runs/v2/jobs-boards.json
Report boards that errored in "problem". Do not edit watchlist.json.`,
  jobright: `Jobright through Apify, from projects/auto-apply:
.venv/bin/python -m auto_apply.v2.apify --out runs/v2/jobs-jobright.json --max-per-search 15 --budget-usd 1 \\
  --search "data analyst@Memphis, TN" --search "business analyst@Memphis, TN" --search "reporting analyst@Memphis, TN" \\
  --search "data analyst@remote" --search "business intelligence analyst@remote" --search "reporting analyst@remote" \\
  --search "data analyst@Atlanta, GA" --search "data analyst@Birmingham, AL"
Exit 2 (no APIFY_API_TOKEN in the repo-root .env, or JOBRIGHT_ENABLED=false): instead read Jobright alert emails from the last 3 days in Gmail
(from:noreply@jobright.ai newer_than:3d) and write their jobs (title, company, location, posted, url = the
jobright.ai link, source "jobright", ats "jobright") to the same file; say which you used in "problem".`,
  tsenta: `Only the Tsenta part of v2-cycle step 2 (get-job-recommendations with the filters listed there).
Write the jobs to projects/auto-apply/runs/v2/jobs-tsenta.json.`,
  indeed: `Only the Indeed part of v2-cycle step 2 (every query x location listed there; do not call
get_job_details yet). Write the jobs to projects/auto-apply/runs/v2/jobs-indeed.json.`,
}
const unknown = SOURCES.filter(k => !FINDERS[k])
if (unknown.length) throw new Error(`Unknown sources: ${unknown.join(', ')} (use ${Object.keys(FINDERS).join(', ')})`)
const found = (await parallel(SOURCES.map(k => () =>
  agent(`${BASE}\n\nStep: find jobs, source "${k}" only. ${FINDERS[k]}\nUse the job object shape from v2-cycle step 2. Return the file and the job count.`,
    { label: `find: ${k}`, phase: 'Find', schema: JOB_FILE, effort: 'low' })
    .then(r => r && { ...r, source: k })))).filter(Boolean)
t = mark('find', t)
log(`Found ${found.map(f => `${f.source} ${f.count}`).join(', ')}`)
found.filter(f => f.problem).forEach(f => log(`find ${f.source}: ${f.problem}`))

// ---- Screen ---------------------------------------------------------------------------------
phase('Screen')
const JOB = {
  type: 'object',
  properties: {
    dir: STR, company: STR, title: STR, location: STR, tier: STR, applyUrl: STR, sourceUrl: STR,
    source: STR, ats: STR, score: { type: ['number', 'null'] }, route: { type: 'string', enum: ['filler', 'tsenta', 'manual'] },
  },
  required: ['dir', 'company', 'title', 'location', 'tier', 'applyUrl', 'source', 'ats', 'route'],
}
const screen = await agent(`${BASE}

Step: v2-cycle step 3 (dedupe and target).
- Merge ${found.map(f => f.file).join(' and ')} into projects/auto-apply/runs/v2/jobs.json.
- Dedupe against projects/auto-apply/runs/v2/tracker.json (all statuses), run target.py, read each
  kept job's full description and apply the skip rules.
- Jobs whose url is not the employer's (ats "jobright", Indeed links): find the same posting on the employer's
  own board first: .venv/bin/python -m auto_apply.v2.boards find --company "<company>" --title "<key words>",
  else the company's careers page (WebSearch). Use that URL as applyUrl and its ATS as ats. Not found or
  closed -> drop it with the reason. Never scrape LinkedIn or Indeed pages.
- Keep the top ${MAX_JOBS}. For each, make projects/auto-apply/runs/${DATE}-<company>-<role>/ (lowercase,
  hyphens) and save the full posting text there as jd.md (with the apply URL at the top).
- route: "filler" for Greenhouse/Lever/Ashby forms; ${TSENTA ? '"tsenta" for other ATSes Tsenta supports; ' : ''}"manual" otherwise
  (Sai sends it by hand with the built PDF).
Return every kept job (dir = that folder) and every screened-out job with its reason.`, {
  label: 'dedupe + target + screen', phase: 'Screen',
  schema: {
    type: 'object',
    properties: { candidates: INT, kept: INT, jobs: { type: 'array', items: JOB }, dropped: STRS },
    required: ['candidates', 'kept', 'jobs', 'dropped'],
  },
})
t = mark('screen', t)
const jobs = screen ? screen.jobs.slice(0, MAX_JOBS) : []
if (screen && screen.kept > jobs.length) log(`Building ${jobs.length} of ${screen.kept} kept jobs (cap ${MAX_JOBS}); the rest wait for the next run`)

// ---- Build ----------------------------------------------------------------------------------
phase('Build')
const builds = (await parallel(jobs.map(j => () => agent(`${BASE}

Step: v2-cycle steps 4.1-4.2 for ONE job: ${j.company} - ${j.title} (${j.location}).
Folder: ${j.dir} (the posting is jd.md there).
- Build the resume with the sai-resume-tailor skill in that folder (the skill's own steps, including its
  visual check). Follow runs/v2/memory.md "Resume decisions".
- Run ats_check on the PDF exactly as step 4.2 says; it must PASS. Fix the LaTeX and rebuild on FAIL;
  two failures -> ok=false with the reason.
Do not red-team your own resume; a separate reviewer does that.`, {
  label: `build: ${j.company}`, phase: 'Build',
  schema: {
    type: 'object',
    properties: { dir: STR, pdf: STR, ok: { type: 'boolean' }, problem: STR, gaps: STRS },
    required: ['dir', 'pdf', 'ok', 'gaps'],
  },
}).then(r => r && { ...r, job: j })))).filter(Boolean)
const built = builds.filter(b => b.ok)
t = mark('build', t)
builds.filter(b => !b.ok).forEach(b => log(`Build failed: ${b.job.company} - ${b.problem}`))

// ---- Review (one batched reviewer, by design) -------------------------------------------------
let reviews = []
if (built.length) {
  phase('Review')
  const review = await agent(`You are a recruiter with 200 applicants for each of these roles, and you want reasons to reject.
For each pair below, read ONLY the posting (jd.md) and the resume text (run: pdftotext -layout <pdf> -).
Do not read any other file. For each resume name the 3 strongest reasons to say no, each with the
change that would answer it, or "none possible" if only new facts could fix it.

${built.map(b => `- ${b.dir}: posting ${b.dir}/jd.md, resume ${b.pdf}`).join('\n')}`, {
    label: `red-team ${built.length} resumes`, phase: 'Review',
    schema: {
      type: 'object',
      properties: {
        reviews: { type: 'array', items: { type: 'object', properties: { dir: STR, reasons: { type: 'array', items: { type: 'object', properties: { reason: STR, fix: STR }, required: ['reason', 'fix'] } } }, required: ['dir', 'reasons'] } },
      },
      required: ['reviews'],
    },
  })
  reviews = review ? review.reviews : []
  t = mark('review', t)
}

// ---- File: fixes + filler plan + Notion rows, one agent for all ------------------------------
let filed = null
if (built.length) {
  phase('File')
  const byDir = Object.fromEntries(reviews.map(r => [r.dir, r.reasons]))
  filed = await agent(`${BASE}

Step: finish v2-cycle step 4.3 (apply review fixes, in one pass), then steps 4.4 and 5, for these resumes.
For each reason: fix it in resume.tex and rebuild, or accept it and list it under "Gaps" in Notes.
Never invent anything to answer a reason. Re-run ats_check after any rebuild (must PASS).

${built.map(b => `## ${b.job.company} - ${b.job.title}
folder ${b.dir}, pdf ${b.pdf}, route ${b.job.route}, tier ${b.job.tier}, ats ${b.job.ats}
apply ${b.job.applyUrl}${b.job.sourceUrl ? `, source ${b.job.sourceUrl}` : ''}, score ${b.job.score ?? 'n/a'}
tailoring gaps: ${b.gaps.join('; ') || 'none'}
red-team: ${(byDir[b.dir] || []).map((r, i) => `${i + 1}. ${r.reason} -> ${r.fix}`).join(' | ') || 'no review'}`).join('\n\n')}

Then: filler plan + drafted answers (step 4.4) for route "filler", and one tracker row per job with the
resume attached (step 5): Status Drafted, Submit? No.`, {
    label: `fix + file ${built.length} rows`, phase: 'File',
    schema: {
      type: 'object',
      properties: {
        rows: { type: 'array', items: { type: 'object', properties: { company: STR, title: STR, notionUrl: STR, route: STR, gapsAccepted: INT, draftedAnswers: INT }, required: ['company', 'title', 'notionUrl', 'route'] } },
        problems: STRS,
      },
      required: ['rows', 'problems'],
    },
  })
  t = mark('file', t)
}

// ---- Report ---------------------------------------------------------------------------------
phase('Report')
const needsSai = [...sync.needsSai, ...(applied ? applied.needsSai : [])]
const sent = applied ? applied.sent : []
const routes = sent.reduce((m, s) => ({ ...m, [s.route]: (m[s.route] || 0) + 1 }), {})
const failed = [
  ...builds.filter(b => !b.ok).map(b => `build ${b.job.company}: ${b.problem}`),
  ...(filed ? filed.problems : []),
  ...(applied ? applied.skipped : []),
]
const lines = [
  ...needsSai.map(n => `NEEDS SAI: ${n.company} - ${n.title}: ${n.why}`),
  `Outcomes synced: ${sync.updates} updates, ${sync.newRows} new rows, ${sync.unmatched.length} unmatched`,
  `Jobs: ${found.reduce((s, f) => s + f.count, 0)} found -> ${screen ? screen.kept : 0} kept -> ${built.length} built -> ${filed ? filed.rows.length : 0} rows for review`,
  LIVE ? `Applications sent: ${sent.length} (${Object.entries(routes).map(([k, v]) => `${k} ${v}`).join(', ') || 'none'}); Tsenta credits left ${applied ? applied.creditsLeft : 'unknown'}`
       : 'DRY_RUN: nothing sent',
  ...(failed.length ? [`Failed/left: ${failed.join(' | ')}`] : []),
]
const total = Object.values(stage).reduce((s, n) => s + n, 0)
lines.push(`Tokens (workflow output tokens by stage): ${Object.entries(stage).map(([k, v]) => `${k} ${v}`).join(' · ')} · total ${total} · per resume ${built.length ? Math.round(total / built.length) : 0} · workflow run`)

await agent(`${BASE}

Step: v2-cycle step 7. Append this report, unchanged, as a new dated entry (${DATE}) to the Run Log on the
Notion memory page. Change nothing else on the page.

${lines.join('\n')}`, { label: 'append run log', phase: 'Report' })

return { report: lines, rows: filed ? filed.rows : [], dropped: screen ? screen.dropped : [], unmatched: sync.unmatched }
