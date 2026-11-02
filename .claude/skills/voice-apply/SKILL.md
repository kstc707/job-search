---
name: voice-apply
description: Hands-free job search and apply. Use when Sai says he is hands-free, driving, can't touch the phone, asks for voice mode, or his messages read like dictation ("find me analyst jobs in Dallas", "apply to number two", "apply to the link I emailed myself", "read it back", "submit Acme"). Same pipeline as tsenta-apply; replies are written to be heard, the screenshot review becomes a spoken read-back, and a submit needs Sai to say "submit <company>".
---

# Voice apply: the whole pipeline by voice

**Read `permissions/POLICY.md` first**, then `.claude/skills/tsenta-apply/SKILL.md`: this skill changes how
you talk to Sai and how he approves; every step, gate and limit there still applies. Give every agent you
launch the instruction "Read permissions/POLICY.md first."

Sai cannot look at or touch the phone. Everything you write may be read aloud by a speech engine, and
everything he says reaches you through dictation, so it may be misheard.

## How to reply
- Two or three short sentences. No tables, markdown, code, file paths, ids or URLs in what you say
  (put details in files; say "it's on your hands-on list").
- Lists: at most five items, numbered, one line each: "2. Acme, data analyst, Dallas, posted yesterday, match 82."
- End every reply with what he can say next: "Say apply to one, details on two, or more."
- Work silently: don't narrate tool calls. Say one short line before anything slow ("Building the resume
  for Acme, about two minutes.") and the result after.
- Unsure what he said? Ask once, offering your best guess: "Did you mean Acme Labs?" Never act on a guess
  that would send something.

## What Sai says → what you do

| He says (any wording) | You do |
|---|---|
| "find / search … jobs [in place] [remote] [this week]" | tsenta-apply step 1 with those filters (Indeed `search_jobs` as a second source). Save the full list to `runs/voice/last_list.json`; speak the top five. |
| "more", "next five" | The next five from `last_list.json`. |
| "details on two", "tell me about the Acme one" | Two sentences: what the job is, and the one or two requirements most likely to rule him out. |
| "apply to two", "apply to the Acme one" | The apply flow below for that job. |
| "apply to this link: jobs dot lever dot co slash …" | `.venv/bin/python -m auto_apply.voice url "<his words>"` → URL, then `fetch-job-description`. Exit 2: ask him to say it again, slower. |
| "apply to the link I sent / emailed myself" | Gmail `search_threads` (`from:me newer_than:3d`, then `newer_than:7d`) for the newest message with a job link; say which job it is and ask "That one?" before going on. |
| "apply to the Stripe data analyst job" (no link) | Tsenta `search-companies` / recommendations to find it; read back the match and ask "That one?" |
| "read it back", "what will you send" | The read-back again (it also renews the 30-minute window). |
| "submit <company>" | The submit step below. |
| "skip", "not this one", "next" | Drop the job; offer the next one. |
| "what did I apply to today", "status" | `cli list` plus Tsenta `get-application-status` for today's; speak counts and any failures. |
| "what needs my hands" | `.venv/bin/python -m auto_apply.voice later list` → speak it. |
| "stop", "pause" | Stop at once. Nothing pending is sent; a pending read-back simply expires. |

## The apply flow
1. **Check fit** (tsenta-apply step 1 rules). A `LOW ODDS` mark or a failed rule: say why in one sentence
   and ask "Apply anyway?" (POLICY: that is Sai's call).
2. **Resume.** Tailor with `sai-resume-tailor` in `runs/<yyyy-mm-dd>-<company>-<role>/`, then `cli gate`.
   A gate block: fix the resume (never the rules) and re-gate; still blocked → tell him and move on.
3. **Route** as in tsenta-apply step 4.
4. **Questions.** `filler.cli plan <url> --pdf <pdf> --speak` prints a `SPOKEN:` block; say it as written.
   - A question it can't answer: read the question and its options, take his answer, ask "Just this job,
     or always?" and save it to `runs/<job>/answers.json` (this job) or `runs/answers.json` (always).
     His answer must be his own words or one of the options; never fill one in for him.
   - An essay question: draft it from facts.md only, read the draft aloud in full, and save it only after
     he says "approve" (or dictates changes; read the new version back too).
   - Consents (recording, AI use, arbitration): read what it asks in one or two sentences, offer the full
     text, and record his answer for this job only.
   - Re-run `plan --speak` after every change: only the latest read-back can be approved.
5. **Read-back.** Our filler: the `plan --speak` text above. Tsenta: `.venv/bin/python -m auto_apply.voice
   readback-tsenta --pdf <pdf> --company "<company>" --title "<title>" --url <url>`. Say any gate WARNING
   (e.g. a different email on the form) before the last line.
6. **Submit** only when he says "submit <company>" after that read-back. Pass his words exactly:
   - our filler: `filler.cli fill <url> --pdf <pdf> --submit --voice-confirm "<his exact words>"`
   - Tsenta: `.venv/bin/python -m auto_apply.voice confirm --url <url> "<his exact words>"`; only on exit 0,
     tsenta-apply step 5b (upload → `check-custom-resume` → `apply-with-custom-resume`).
   Exit 4 (filler) or 2 (voice confirm) means nothing was sent: say the `REFUSED:` reason as written.
   "yes", "do it" or "go ahead" are not a go-ahead for a submit; ask for "submit <company>".
   One go-ahead covers one job. "Submit all" is not accepted by voice.
7. **Record** (tsenta-apply step 6). In the Notion tracker, Notes: "Approved by voice <time>: '<his words>'".
   Never set `Submit?` or `Approved at` (POLICY).
8. **Say the result:** "Sent to Acme." / "Tsenta has it; I'll tell you when it's through." / the failure in
   one sentence.

## Accounts, captchas and other things a voice can't do
- Login ATSes (Workday, iCIMS, Taleo, SuccessFactors…) go through Tsenta, which signs in or creates the
  account itself. Our filler only fills public, login-free forms and never creates accounts.
- Never ask for, repeat or store a password, and never take one by voice: it would sit in the transcript.
  If Tsenta needs one (e.g. `set-workday-password`, a Tsenta settings change POLICY reserves for Sai),
  add it to the hands-on list.
- A captcha, an email-verification link, a file only on his phone, a payment: `.venv/bin/python -m
  auto_apply.voice later add "<what, in a few words>" --url <url>`, tell him in one sentence, move on.
- Ashby "NOT SUBMITTED" or a captcha on our filler: hands-on list (tsenta-apply step 5a), or Tsenta for
  Greenhouse; read back again before that new submit.
