"""Fit score, 0-100: how well the candidate matches a posting (50) and how likely the
application is to get past the employer's automatic screening and be worth sending (50).

Match (50)
- required: share of required job-map rows backed by a real fact (30)
- keywords: share of the posting's technical terms that appear in the resume (15)
- preferred: share of preferred job-map rows backed by a real fact (5)
Hireability (50)
- knockouts: any failed hard requirement (see screen.py) makes the whole score 0
- level: role family is a target family (8); years asked are within reach (7)
- parse: the PDF text comes out in the right order with the name and email (10)
- freshness: days since the job was posted (10)
- signal: active-hiring signal from the research agent, 0-1 (15)

Before a resume is built there is no job map, resume or PDF yet. The score then uses the
facts file in their place, marks those parts as estimates, and only decides "build" or
"skip" (thresholds.build). After the build, the full score decides: "auto" (thresholds.auto,
applied without waiting), "review" (thresholds.review, waits for the person's Yes) or "skip".
Unknown freshness and hiring signal score in the middle, so "auto" needs positive evidence.
"""
import datetime as dt
import re

from . import audit, bullets, screen

# Technical terms looked for in postings. Matching is case-insensitive on word boundaries.
TERMS = [
    "SQL", "Python", "R", "Excel", "Power BI", "Tableau", "Looker", "DAX", "Power Query",
    "pandas", "NumPy", "scikit-learn", "PyTorch", "TensorFlow", "Spark", "PySpark", "Databricks",
    "Snowflake", "dbt", "Airflow", "AWS", "Azure", "GCP", "BigQuery", "Docker", "Kubernetes",
    "PostgreSQL", "MySQL", "Oracle", "SAS", "SPSS", "Stata", "Git", "TypeScript", "JavaScript",
    "React", "Next.js", "Node.js", "Java", "C++", "REST", "API", "ETL", "A/B testing",
    "statistics", "regression", "machine learning", "deep learning", "NLP", "LLM", "RAG",
    "LangChain", "LangGraph", "prompt engineering", "AI agents", "embeddings", "vector database",
    "forecasting", "dashboards", "data modeling", "data quality", "data visualization",
    "Streamlit", "Plotly", "Jupyter", "SharePoint", "Power Automate", "Visio", "Microsoft Access",
]
_PREFERRED = re.compile(r"prefer|nice to have|nice-to-have|bonus|a plus|desired", re.I)
_UNCOVERED = re.compile(r"\bGAP\b|\bCONFIRM\b|\bFLAG\b|^\s*[—-]?\s*$", re.I)


def terms_in(text, extra=()):
    found = []
    for t in list(TERMS) + list(extra):
        if t.islower():  # plain words: match any ending ("dashboards" finds "dashboard")
            pat = r"(?<![\w+#])" + re.escape(t.rstrip("s")) + r"\w*"
        else:
            pat = r"(?<![\w+#])" + re.escape(t) + r"(?![\w+#])"
        if re.search(pat, text, 0 if t.isupper() or len(t) <= 2 else re.I):
            found.append(t)
    return found


_STOP = set("""about above after again against also among and any are because been before being
below between both but can could did does doing down during each few for from further had has
have having her here hers him his how into its itself just more most must not now off once only
other our ours out over own same she should some such than that the their theirs them then there
these they this those through too under until very was were what when where which while who whom
why will with within would you your yours able ability work working job role team teams position
candidate candidates including include includes strong excellent experience years year required
preferred skills skill knowledge related relevant equivalent degree minimum qualifications duties
responsibilities perform performs provide provides support supports ensure ensures may per well
across various other new using use used etc city state county university company""".split())


def content_words(text, top=40):
    """The posting's most frequent content words (lowercased, 4+ letters, no stopwords)."""
    counts = {}
    for w in re.findall(r"[a-z][a-z-]{3,}", text.lower()):
        w = w.rstrip("s") if len(w) > 4 else w
        if w not in _STOP and w.rstrip("s") not in _STOP:
            counts[w] = counts.get(w, 0) + 1
    return [w for w, _ in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[:top]]


def word_share(jd_text, evidence_text):
    words = content_words(jd_text)
    if not words:
        return 0.5
    have = evidence_text.lower()
    return sum(1 for w in words if re.search(r"\b" + re.escape(w), have)) / len(words)


def map_rows(jd_map_text):
    """[(requirement, evidence, preferred?)] from the job map's table rows."""
    rows = []
    for line in jd_map_text.splitlines():
        s = line.strip()
        if not s.startswith("|") or re.match(r"^\|\s*:?-{3}", s):
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if len(cells) < 2 or cells[0].lower().startswith(("jd ", "responsibility", "requirement")):
            continue
        rows.append((cells[0], " ".join(cells[1:]), bool(_PREFERRED.search(cells[0]))))
    return rows


def _covered(evidence):
    return not _UNCOVERED.search(evidence)


def freshness_points(posted, today):
    if not posted:
        return 5, "unknown"
    try:
        day = dt.date.fromisoformat(str(posted)[:10])
    except ValueError:
        return 5, "unknown"
    age = (today - day).days
    for limit, pts in ((3, 10), (7, 7), (14, 4), (30, 2)):
        if age <= limit:
            return pts, f"{age} days"
    return 0, f"{age} days"


def parse_points(pdf_text, cfg):
    """10 * share of checks passed on the PDF text, as an applicant-tracking system reads it."""
    lines = [l.strip() for l in pdf_text.splitlines() if l.strip()]
    checks = []
    name = cfg.get("name", "")
    checks.append(bool(lines) and bool(name) and name.lower() in " ".join(lines[:3]).lower())
    checks.append(bool(cfg.get("email")) and cfg["email"].lower() in pdf_text.lower())
    order = cfg.get("section_order", [])
    pos = [pdf_text.find(s) for s in order]
    checks.append(bool(order) and all(p >= 0 for p in pos) and pos == sorted(pos))
    letters = sum(c.isalpha() for c in pdf_text)
    checks.append(len(pdf_text) > 0 and letters / len(pdf_text) > 0.6)
    return round(10 * sum(checks) / len(checks), 1)


def score(meta, text, cfg, facts_text, jd_map_text=None, resume_text=None, pdf_text=None,
          signal=None, today=None):
    today = today or dt.date.today()
    parts, estimated = {}, []

    knockouts = screen.screen(meta, text, cfg)

    # Match
    if jd_map_text:
        rows = map_rows(jd_map_text)
        req = [r for r in rows if not r[2]]
        pref = [r for r in rows if r[2]]
        parts["required"] = round(30 * sum(_covered(r[1]) for r in req) / len(req), 1) if req else 15.0
        parts["preferred"] = round(5 * sum(_covered(r[1]) for r in pref) / len(pref), 1) if pref else 2.5
    jd_terms = terms_in(text, cfg.get("extra_terms", []))
    evidence = resume_text or facts_text
    have_terms = set(terms_in(evidence, cfg.get("extra_terms", [])))
    term_share = len([t for t in jd_terms if t in have_terms]) / len(jd_terms) if jd_terms else 0.0
    # Postings that name few tools (government, operations roles) are judged mostly on their
    # domain words: the tool share counts fully only once the posting names 5+ tools.
    weight = min(1.0, len(jd_terms) / 5)
    domain = word_share(text, evidence)
    parts["keywords"] = round(15 * (weight * term_share + (1 - weight) * domain), 1)
    if not jd_map_text:  # pre-build: tools and domain words in the facts file stand in
        parts["required"] = round(30 * (0.5 * (weight * term_share + (1 - weight) * domain)
                                        + 0.5 * domain), 1)
        parts["preferred"] = 2.5
        estimated += ["required", "preferred"]
    if not resume_text:
        estimated.append("keywords")

    # Hireability
    fam = bullets.family_for_title(meta.get("title", ""))
    level = 8 if fam in cfg.get("target_families", ["ai", "ds", "da"]) else 0
    years = screen.required_years(meta, text)
    have = cfg.get("years_experience", 0)
    if years is None or years <= have:
        level += 7
    elif years <= cfg.get("max_required_years", have):
        level += 3
    parts["level"] = level
    if pdf_text is not None:
        parts["parse"] = parse_points(pdf_text, cfg)
    else:
        parts["parse"] = 10.0
        estimated.append("parse")
    parts["freshness"], age = freshness_points(meta.get("datePosted"), today)
    if signal is None:
        parts["signal"] = 7.0
        estimated.append("signal")
    else:
        parts["signal"] = round(15 * max(0.0, min(1.0, float(signal))), 1)

    total = 0.0 if knockouts else round(sum(parts.values()), 1)
    th = {"auto": 80, "review": 65, "build": 50, **cfg.get("thresholds", {})}
    gate = th["build"] if not jd_map_text else th["review"]
    if knockouts or total < gate:
        decision = "skip"
    elif not jd_map_text:
        decision = "build"
    elif total >= th["auto"]:
        decision = "auto"
    else:
        decision = "review"
    return {
        "title": meta.get("title"), "company": meta.get("companyName"),
        "score": total, "decision": decision, "knockouts": knockouts, "parts": parts,
        "estimated": estimated, "family": fam, "years_asked": years, "posted": age,
        "missing_terms": [t for t in jd_terms if t not in have_terms],
    }


def rank(results, cap):
    """Jobs to act on today: non-skipped, best first, at most `cap`."""
    keep = [r for r in results if r["decision"] != "skip"]
    return sorted(keep, key=lambda r: -r["score"])[:cap]


def pdf_text_or_none(path):
    return audit.pdf_text(path) if path else None
