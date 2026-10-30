# Delivery Scam Watch

Collects public signals of scams that impersonate delivery companies (FedEx, UPS, USPS, DHL):
lookalike domains, phishing URLs and scam text messages. It stores every sighting with where
and when it came from, then (in later components) scores, clusters and links them into
campaigns, shown on a live dashboard.

**Status:** component 0 (foundation) is built. No scraping yet.

## Languages and where things are saved

| What | Language / tool | Saved in |
|---|---|---|
| Scrapers, analysis, command-line tool | Python 3.12 | `scamwatch/` (this Git repository) |
| Database tables | SQL (PostgreSQL 16) | `db/migrations/` as numbered files |
| Collected data | PostgreSQL | Neon (cloud) in production; a local Postgres for tests |
| Brands and keywords | YAML | `config/brands.yaml` |
| Secrets (database URL, API keys) | environment variables | `.env` on your computer (never committed); GitHub Secrets in scheduled jobs |
| Schedules and tests in the cloud | GitHub Actions (YAML) | `.github/workflows/` |
| Dashboard (component 11) | Next.js | `web/` (added later) |

## Layout

```
scamwatch/            the Python package
  config.py           settings from .env, and the brand list
  db.py               database connection; applies migrations, refuses edited ones
  store.py            saves domains, URLs and sightings without duplicates; 30-day raw purge
  runlog.py           one row per scraper run (success / partial / failed) + JSON logs
  defang.py           makes URLs safe to display: https://x.com -> hxxps://x[.]com
  cli.py              python -m scamwatch migrate | hello | status | purge-raw
config/brands.yaml    brands, keywords and allowlisted (legitimate) domains
db/migrations/        0001_init.sql, then 0002_..., never edit an applied file
tests/                pytest: migrations, run logging, no duplicates, brand matching,
                      retention, defanging, no secrets committed
.github/workflows/    ci.yml: lint and tests on every push
```

## The database (migration 0001)

| Table | One row per |
|---|---|
| `sources` | data source (crt.sh, urlscan, URLhaus, PhishTank, OpenPhish, Reddit, RDAP), with its terms and our politeness limit; all start disabled |
| `collector_runs` | scraper run: start, end, status, items seen, items new, error |
| `domains` | unique domain: full name, registered domain, suffix, first/last seen, brand keyword, allowlisted |
| `urls` | unique URL (raw for analysis, only ever shown defanged) |
| `observations` | sighting from a source (append-only; unique per source and the source's own ID) |
| `reports` | public scam report text (e.g. a Reddit post) and the links in it |
| `labels` | your hand label for a domain: scam, legitimate or unsure |

## Setup

```bash
python3 -m venv .venv
.venv/bin/pip install -e ".[dev]"
cp .env.example .env            # then put your Neon connection strings in .env
.venv/bin/python -m scamwatch migrate
.venv/bin/python -m scamwatch hello
.venv/bin/python -m scamwatch status
.venv/bin/python -m pytest -q   # needs TEST_DATABASE_URL (a separate database: tests drop every table)
```

## Ground rules

Public data only, within each source's terms and robots.txt, with polite rate limits. The
project never submits forms on, or downloads files from, a scam site. URLs are stored raw for
analysis but every display goes through `defang()`. It covers four carriers, uses no company
logos and does not claim to act for any of them.
