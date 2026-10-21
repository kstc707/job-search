"""Score each job's fit without an LLM and sort it into a tier, so model spend goes where it pays.

Every job that passes gets a tailored resume; the tier decides what else it gets:

    A  strong fit   tailored resume + red-team review + outreach to a person, built first
    B  decent fit   tailored resume, built in large batches, no red-team, no outreach
    C  weak fit     not built; its missing skills go to the Gap Ledger

Score (0-100) = skills 45 + title 20 + location 15 + freshness 10 + experience 10.
    skills       covered skill terms / max(terms the posting names, 5), so a posting that names
                 only one or two tools gives little evidence of fit
                 (covered = in runs/kb_terms.json: verified tools + Built projects' stacks)
    title        20 when the title names data work (data, analytics, BI, reporting, insights,
                 ML/AI, scientist), 10 for another analyst title in a core family, else 0
    location     target.py tier: Memphis 15, Remote 12, Atlanta 9, Alabama 6, rest 3;
                 0 when the location is outside the US
    freshness    10 within 72 h, 6 within a week, 2 older or unknown
    experience   10 when the posting asks for at most 4 years (or says nothing), 0 above
Knockouts (citizenship-only, clearance, student-only) force tier C whatever the score.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

from auto_apply.v2.target import age_hours, location_tier
from auto_apply.v2.titles import family

TIER_A, TIER_B = 70, 45
DATA_TITLE = re.compile(r"\b(data|analytics|business intelligence|bi|reporting|insights?|machine learning|"
                        r"ml|ai|scientist|quantitative|statistic\w*)\b", re.I)
NON_US = re.compile(r"\b(uk|united kingdom|london|canada|toronto|vancouver|luxembourg|ireland|dublin|germany|"
                    r"berlin|france|paris|netherlands|amsterdam|spain|india|bangalore|bengaluru|hyderabad|"
                    r"singapore|australia|sydney|mexico|brazil|poland|portugal|emea|apac|europe)\b", re.I)
CORE_FAMILIES = {"data_analyst", "bi", "reporting", "business_analyst", "product", "data_science", "ml_ai"}
ADJACENT_FAMILIES = {"data_engineering"}
LOCATION_POINTS = [15, 12, 9, 6, 3]

# Skill vocabulary the scorer looks for in postings (lower case; aliases map to one term).
SKILLS = {
    "python": ["python"], "sql": ["sql"], "r": [r"\br\b(?! ?&)"], "excel": ["excel"],
    "power bi": ["power ?bi"], "tableau": ["tableau"], "looker": ["looker"], "dax": [r"\bdax\b"],
    "pandas": ["pandas"], "numpy": ["numpy"], "scikit-learn": ["scikit-?learn", "sklearn"],
    "statsmodels": ["statsmodels"], "spark": [r"\bspark\b", "pyspark"], "databricks": ["databricks"],
    "snowflake": ["snowflake"], "bigquery": ["bigquery"], "redshift": ["redshift"], "dbt": [r"\bdbt\b"],
    "airflow": ["airflow"], "aws": [r"\baws\b", "amazon web services"], "azure": ["azure"], "gcp": [r"\bgcp\b", "google cloud"],
    "postgresql": ["postgres"], "mysql": ["mysql"], "sql server": ["sql server", "ssms", r"\bssrs\b", r"\bssis\b"],
    "duckdb": ["duckdb"], "etl": [r"\betl\b", r"\belt\b"], "data quality": ["data quality", "data validation"],
    "a/b testing": ["a/b test", "ab test", "experiment(ation|s)?\\b"], "statistics": ["statistic"],
    "machine learning": ["machine learning", r"\bml\b"], "forecasting": ["forecast"],
    "regression": ["regression"], "classification": ["classification"], "nlp": [r"\bnlp\b", "natural language"],
    "llm": [r"\bllms?\b", "large language model", "generative ai", r"\bgenai\b"], "rag": [r"\brag\b", "retrieval"],
    "pytorch": ["pytorch"], "tensorflow": ["tensorflow"], "lightgbm": ["lightgbm"], "xgboost": ["xgboost"],
    "mlflow": ["mlflow"], "docker": ["docker"], "kubernetes": ["kubernetes", r"\bk8s\b"], "fastapi": ["fastapi"],
    "javascript": ["javascript"], "typescript": ["typescript"], "react": [r"\breact\b"], "git": [r"\bgit\b", "github"],
    "streamlit": ["streamlit"], "jira": [r"\bjira\b"], "sas": [r"\bsas\b"], "spss": [r"\bspss\b"],
    "salesforce": ["salesforce"], "sap": [r"\bsap\b"], "power automate": ["power automate"], "vba": [r"\bvba\b"],
    "dashboards": ["dashboard"], "reporting": ["reporting"], "kpis": [r"\bkpis?\b"],
}
_SKILL_RX = {k: re.compile("|".join(v), re.I) for k, v in SKILLS.items()}
_YEARS = re.compile(r"(\d{1,2})\+?\s*(?:-\s*\d{1,2}\s*)?(?:years|yrs)", re.I)
_KNOCKOUTS = [
    ("citizenship required", re.compile(r"\bU\.?S\.? citizen(ship)? (is )?required|must be a U\.?S\.? citizen|US citizens only", re.I)),
    ("clearance required", re.compile(r"(active|current|secret|top secret|ts/sci)\b[^.]{0,40}\bclearance|clearance (is )?required", re.I)),
    ("students only", re.compile(r"currently (enrolled|pursuing)|must be a (current )?student|graduating in 202[7-9]", re.I)),
]


def posting_skills(text: str) -> set[str]:
    return {k for k, rx in _SKILL_RX.items() if rx.search(text or "")}


def years_asked(text: str) -> int | None:
    found = [int(m.group(1)) for m in _YEARS.finditer(text or "") if int(m.group(1)) <= 20]
    return min(found) if found else None


@dataclass
class Fit:
    score: int
    tier: str
    parts: dict = field(default_factory=dict)
    covered: list = field(default_factory=list)
    missing: list = field(default_factory=list)
    knockout: str = ""


def score(job: dict, kb_terms: set[str], *, now: datetime) -> Fit:
    text = f"{job.get('title', '')}\n{job.get('description', '')}"
    for name, rx in _KNOCKOUTS:
        if rx.search(text):
            return Fit(0, "C", knockout=name)
    wanted = posting_skills(text)
    covered = sorted(wanted & kb_terms)
    missing = sorted(wanted - kb_terms)
    skills = round(45 * len(covered) / max(len(wanted), 5))
    fam = family(job.get("title", ""))
    data_title = bool(DATA_TITLE.search(job.get("title", "")))
    title = 20 if data_title and fam in CORE_FAMILIES | ADJACENT_FAMILIES else 10 if fam in CORE_FAMILIES else 0
    loc = job.get("location", "")
    tier_idx, _ = location_tier(loc)
    location = 0 if NON_US.search(loc) else LOCATION_POINTS[min(tier_idx, len(LOCATION_POINTS) - 1)]
    age = age_hours(job.get("posted"), now)
    fresh = 10 if age is not None and age <= 72 else 6 if age is not None and age <= 168 else 2
    yrs = years_asked(job.get("description", ""))
    experience = 10 if yrs is None or yrs <= 4 else 0
    total = skills + title + location + fresh + experience
    tier = "A" if total >= TIER_A else "B" if total >= TIER_B else "C"
    parts = {"skills": skills, "title": title, "location": location, "freshness": fresh,
             "experience": experience, "family": fam, "years_asked": yrs}
    return Fit(total, tier, parts, covered, missing)


def tier_jobs(jobs: list[dict], kb_terms: set[str], *, now: datetime) -> list[dict]:
    """Jobs with a `fit` block, best first."""
    kb = {t.lower() for t in kb_terms}
    out = [{**j, "fit": asdict(score(j, kb, now=now))} for j in jobs]
    out.sort(key=lambda j: ("ABC".index(j["fit"]["tier"]), -j["fit"]["score"]))
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse
    p = argparse.ArgumentParser(prog="auto_apply.v2.fit")
    p.add_argument("jobs", help="JSON list of jobs with title, location, posted, description")
    p.add_argument("--kb-terms", required=True, help='JSON {"terms": [...]} of skills the Knowledge Base covers')
    p.add_argument("--out")
    a = p.parse_args(argv)
    kb = set(t.lower() for t in json.load(open(a.kb_terms))["terms"])
    unknown = sorted(kb - set(SKILLS))
    jobs = json.load(open(a.jobs))
    if isinstance(jobs, dict):
        jobs = jobs.get("jobs", [])
    rows = tier_jobs(jobs, kb, now=datetime.now(timezone.utc))
    for j in rows:
        f = j["fit"]
        why = f["knockout"] or f"missing: {', '.join(f['missing'][:5]) or '-'}"
        print(f"{f['tier']} {f['score']:3}  {(j.get('company') or '')[:22]:22} {(j.get('title') or '')[:42]:42} {why}")
    counts = {t: sum(j['fit']['tier'] == t for j in rows) for t in "ABC"}
    print(f"A {counts['A']} · B {counts['B']} · C {counts['C']}"
          + (f"  (kb terms not in the scorer's vocabulary, ignored: {', '.join(unknown)})" if unknown else ""))
    if a.out:
        json.dump(rows, open(a.out, "w"), indent=1)
    return 0


if __name__ == "__main__":
    sys.exit(main())
