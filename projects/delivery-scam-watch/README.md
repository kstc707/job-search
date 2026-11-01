# Delivery Scam Watch

Fake "your package is on hold" texts were the most reported text scam in the US in 2024, when
reported losses to text scams reached $470M (FTC, April 2025). Those texts link to domains that
impersonate delivery companies. This project watches **new** domains (fresh registrations and
fresh website certificates), spots the ones that impersonate FedEx, UPS, USPS or DHL, and gives
an analyst a short list to review **before** public blocklists catch up.

Everything runs on real, public, keyless data. Dashboard: `dashboard/index.html` (a static
snapshot, open it in a browser).

## Results (data as of 2026-11-01, 8 days of new-domain data)

| Question | Answer |
|---|---|
| How many brand-keyword new domains a week? | 329 in 8 days from WhoisDS registrations and the CT log sample |
| How many reach the analyst? | **41** after the brand-word rule and the model (about **103 → 13 analyst hours a month**, at 5 minutes per review) |
| Are they real? | Name-only review: **35 likely scams**, 4 unsure, 2 legitimate (85% precision). The model missed none of the likely scams |
| Are they already blocked? | **None of the 35** is on any of the blocklists we read |
| Do blocklists act in time? | Of 187 blocklisted brand domains we looked up, **149 (80%) no longer exist** at the registry, so by listing time the campaign has often moved on |
| Campaign signals | Series such as `fedex-vip*.shop` and `dhl+letters.cc`; one registrar (Dominet (HK) Limited) handled 18 of the flagged registrations |

### How good is the detector, honestly?

- **Lab** (2,230 real blocklisted scams vs 66 popular-site names, grouped by registered domain):
  PR-AUC 0.997. Optimistic: popular sites are easy negatives.
- **Unseen brand** (train on three brands, test on the fourth): PR-AUC 0.87 (UPS) to 1.00 (USPS).
  UPS is hardest because "ups" hides inside ordinary words.
- **Live stream:** before the brand-word rule was tightened, the model flagged 108 of 198 names,
  most of them innocent ("groups", "syrups", device names like "ups1"). The fix was the rule,
  not the model. Lesson: lab scores did not predict the stream.

### Does synthetic data help when real labels are scarce?

Before collecting anything I wrote down how I expected scam domains to look and froze it as
**generator A** (`FREEZE.md`, checksums). Then I built **generator B**, which learns templates
from real training labels.

- Reality differed from the guess: 60% of real scams put the brand in a **subdomain**
  (`usps.com-trackdqf.top`), A assumed 16%. A's two favourite tricks, misspellings and lookalike
  characters, appear in **0%** of real scams. 20% of real scams use endings A never used.
- A classifier tells real from A with AUC 0.91 and real from B with AUC 0.45 (cannot tell).
- With 25 real labels, real data alone reaches 0% recall at 95% precision; adding A lifts it to
  87%. From about 200 labels, real data alone is best and A's wrong assumptions start to cost.

Numbers come from `python -m scamwatch report` → `outputs/results.json` and the charts in
`outputs/`.

## How it works

```
 new registrations (WhoisDS)  ─┐
 new certificates (CT log)    ─┼─► stage 1: brand as a word ─► stage 2: model score ─► analyst list
 blocklists, OpenPhish        ─┤        (rule)                     (gradient boosting)
 Tranco top sites             ─┘  labels: blocklisted = scam, top site = legitimate
 RDAP (registries)            ───► registration date, registrar, still alive?
```

| Source | What it gives | Key needed? |
|---|---|---|
| Google Argon CT log | new website certificates (RFC 6962 `get-entries`, sampled) | no |
| WhoisDS | daily newly registered domains (~70k a day) | no |
| Phishing.Database, phishing.army | phishing blocklists (392k and 152k domains) | no |
| OpenPhish community feed | recent phishing URLs | no |
| Tranco top 1M | popular, legitimate sites | no |
| RDAP via the IANA bootstrap | registration date, registrar, whether it still exists | no |

## Layout

```
scamwatch/
  config.py, db.py, store.py, runlog.py, defang.py, http.py   foundation (settings, migrations,
                                                               dedup storage, run log, polite fetcher)
  collectors/lists.py      blocklists, OpenPhish, Tranco, WhoisDS
  collectors/ctlog.py      certificate transparency log reader
  collectors/rdap.py       registration lookups straight from each registry
  synthetic/generator_a.py frozen guess (do not edit; see FREEZE.md)
  synthetic/generator_b.py templates learned from real training labels
  analysis/features.py     name-only signals + the brand-word rule
  analysis/dataset.py      builds labelled and stream sets from the database
  analysis/model.py        detector + grouped / leave-one-brand-out evaluation
  analysis/experiment.py   synthetic vs real experiment
  analysis/report.py       every number and chart in outputs/
  cli.py                   python -m scamwatch ...
db/migrations/             0001_init.sql, 0002_keyless_sources.sql (never edit an applied file)
data/synthetic/            generator A output (frozen)
data/review/               name-only review of the flagged stream domains
dashboard/index.html       static dashboard snapshot
tests/                     pytest, 66 tests
```

## Run it

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev]"
cp .env.example .env                       # DATABASE_URL, TEST_DATABASE_URL
.venv/bin/python -m scamwatch migrate
.venv/bin/python -m scamwatch collect-all  # every collector once
.venv/bin/python -m scamwatch watch --hours 2   # keep collecting (CT sample + lists + RDAP)
.venv/bin/python -m scamwatch report       # recompute outputs/results.json and charts
.venv/bin/python -m pytest -q              # tests drop tables: use a separate TEST_DATABASE_URL
```

## Limits (stated plainly)

- The CT log is **sampled** (one Google log, a few thousand certificates an hour) and the WhoisDS
  free list is a partial daily sample, so counts are a floor, not a census.
- "Likely scam" on new domains comes from a **name-only review**, not a visit to the site and not
  a confirmation. Confirmation is a domain reaching a blocklist later; the lead-time check
  (`report` → `lead_time`) fills in as the collectors keep running.
- Negatives are popular sites, which are easier than real innocent names. The live stream showed
  this.
- The analyst-hours figure assumes 5 minutes per review.

## Scale-up path (needs accounts)

| Account | What it adds |
|---|---|
| urlscan.io (free key) | page screenshots and hosting details, so a review sees the page, not only the name |
| URLhaus, PhishTank | more confirmations, faster lead-time measurement |
| Reddit app | real scam text reports, to link texts to domains and cluster campaigns |
| Neon (Postgres) | hosted database |
| GitHub Actions | scheduled collectors (secrets in GitHub Secrets) |
| Vercel | live Next.js dashboard reading Neon |

## Ground rules

Public data only, within each source's terms, with polite rate limits and a descriptive
User-Agent. The project never visits, submits forms on, or downloads from a suspected scam site.
Every name shown is defanged (`fedex-vip[.]shop`). Not affiliated with FedEx, UPS, USPS or DHL;
no company marks are used.
