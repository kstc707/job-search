"""Gap ledger: count what job postings ask for that the resume can't honestly claim.

Reads the GAP rows from every jd_map.md and maps the free text onto canonical gap names,
so "Docker, Kubernetes" and "containers" both count as one "Docker / containers" gap.
"""
import re

# canonical name -> regex over the gap text (case-insensitive)
CANON = {
    "Healthcare / claims domain": r"healthcare|clinical|claims|pharmacy|behavioral health|medicaid",
    "Tableau": r"tableau",
    "SAS": r"\bsas\b",
    "Docker / containers": r"docker|kubernetes|\bk8s\b|container",
    "AWS": r"\baws\b|bedrock|sagemaker",
    "CI/CD": r"ci/cd",
    "FastAPI / REST APIs": r"fastapi|rest api",
    "LangChain / LangGraph / LlamaIndex": r"langchain|langgraph|llamaindex",
    "Fine-tuning": r"fine-tun|lora",
    "Spark / Hadoop": r"spark|hadoop",
    "SharePoint / Power Automate": r"sharepoint|power automate",
    "Snowflake": r"snowflake",
    "dbt": r"\bdbt\b",
    "React / Node": r"react|node\.js",
}


def gap_texts(jd_map_text):
    """Free text of every row marked GAP, plus the row's first cell."""
    out = []
    for r in jd_map_text.splitlines():
        if not r.strip().startswith("|") or "GAP" not in r.upper():
            continue
        cells = [c.strip() for c in r.strip().strip("|").split("|")]
        out.append(" ".join(cells))
    return out


def count(jd_map_texts):
    """{canonical gap: number of job maps that mention it in a GAP row}."""
    counts = {k: 0 for k in CANON}
    for text in jd_map_texts:
        joined = " ".join(gap_texts(text))
        for name, pattern in CANON.items():
            if re.search(pattern, joined, re.I):
                counts[name] += 1
    return {k: v for k, v in sorted(counts.items(), key=lambda kv: -kv[1]) if v}


def table(counts, total):
    lines = ["| Gap | Jobs | Share |", "|---|---:|---:|"]
    for name, n in counts.items():
        lines.append(f"| {name} | {n} | {round(100 * n / total)}% |")
    return "\n".join(lines)
