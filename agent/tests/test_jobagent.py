"""Tests for the deterministic job-agent helpers. Fixtures are synthetic: no real resume data."""
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from jobagent import audit, bullets, gaps, texparse  # noqa: E402

FACTS = """# Facts
## Do not claim (list as gaps instead)
- SAS: repo exists but never run.
- PySpark/Spark, GCP (BigQuery, Vertex AI), AWS, Docker, MLOps tooling, Tableau, dbt.

## Application-form notes
- unrelated
"""

RESUME_A = r"""
\section*{Professional Summary}
Data Science graduate who builds \textbf{tested} pipelines.
\section*{Education}
\begin{itemize}
\item Built a pipeline in Python that checks \textbf{8 rules} on every incoming file.
\item Reduced report prep from two days to \textbf{3 hours} with SQL and Excel.
\end{itemize}
"""

RESUME_B = r"""
\begin{itemize}
\item Built a pipeline in Python that checks \textbf{8 rules} on every incoming file.
\item Trained a logistic regression on 50,000 rows and reported AUC 0.81.
\end{itemize}
"""

EXAMPLE = r"""
\begin{itemize}
\item Reduced report prep from two days to 3 hours with SQL and Excel.
\end{itemize}
"""

JD_MAP = """# Job
| JD responsibility | Strongest real fact | Where |
|---|---|---|
| Build pipelines | 8 automated checks | DQ |
| Dashboards | Power BI 32 measures | LD |
| Tableau, Snowflake | — | **GAP** |
| Driver's license | — | **CONFIRM** |
"""


def write(tmp_path, name, text):
    p = tmp_path / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text)
    return str(p)


def test_bullets_are_cleaned():
    items = texparse.bullets(RESUME_A)
    assert items[0] == "Built a pipeline in Python that checks 8 rules on every incoming file."
    assert len(items) == 2


def test_summary_extracted():
    assert texparse.summary(RESUME_A) == "Data Science graduate who builds tested pipelines."


def test_bullet_id_ignores_markup_and_case():
    assert texparse.bullet_id("Built \\textbf{8} checks.") == texparse.bullet_id(
        texparse.clean("built 8 checks"))


def test_do_not_claim_terms():
    terms = audit.do_not_claim_terms(FACTS)
    for t in ["SAS", "PySpark", "Spark", "GCP", "BigQuery", "Vertex AI", "AWS", "Docker",
              "MLOps", "Tableau", "dbt"]:
        assert t in terms
    assert "repo exists but never run" not in terms


def test_find_banned_word_boundaries():
    terms = ["SAS", "dbt", "AWS"]
    assert audit.find_banned("Used SAS for reports", terms) == ["SAS"]
    assert audit.find_banned("Kansas office; sasquatch", terms) == []
    assert audit.find_banned("Old School of Engineering", terms + ["Old School"]) == ["Old School"]
    assert audit.find_banned("scholarship covers 50% of tuition", ["50%"]) == ["50%"]


def test_coverage_counts_gap_and_confirm_rows():
    assert audit.coverage(JD_MAP) == (2, 4)


def test_copy_of_example_flagged():
    copies = audit.copies_of_example(texparse.bullets(RESUME_A), texparse.bullets(EXAMPLE))
    assert len(copies) == 1


def test_near_duplicate_needs_approval():
    a, b = texparse.bullets(RESUME_A), texparse.bullets(RESUME_B)
    dups = audit.near_duplicates(a, b)
    assert len(dups) == 1
    assert audit.near_duplicates(a, b, approved_ids=[dups[0]["id"]]) == []


def test_audit_end_to_end(tmp_path):
    tex = write(tmp_path, "a/a.tex", RESUME_A)
    other = write(tmp_path, "b/b.tex", RESUME_B)
    res = audit.audit(tex, write(tmp_path, "facts.md", FACTS), write(tmp_path, "ex.tex", EXAMPLE),
                      jd_map_path=write(tmp_path, "a/jd_map.md", JD_MAP), other_tex_paths=[other])
    assert res["coverage"] == 0.5
    assert res["pass"] is False
    assert any("copy the example" in p for p in res["problems"])
    assert any("without a success record" in p for p in res["problems"])


def test_gap_counts():
    counts = gaps.count([JD_MAP, JD_MAP.replace("Tableau", "Docker")])
    assert counts["Snowflake"] == 2
    assert counts["Tableau"] == 1
    assert counts["Docker / containers"] == 1


def test_family_for_title():
    assert bullets.family_for_title("AI Engineer - Go To Market") == "ai"
    assert bullets.family_for_title("Researcher, Applied AI and Machine Learning") == "ai"
    assert bullets.family_for_title("Graduate Marketing Scientist") == "ds"
    assert bullets.family_for_title("Pricing Data Analyst") == "da"


PDF_TEXT = """Professional Experience
Data Analyst | Example Org

• Built a pipeline in Python that checks 8 rules on every

incoming file.
• Reduced report prep from two days to 3 hours with SQL and Excel.
Projects
• Trained a logistic regression on 50,000 rows and reported AUC
0.81 on a holdout set.
"""


def test_pdf_bullets_joins_wrapped_lines():
    items = bullets.pdf_bullets(PDF_TEXT)
    assert items == [
        "Built a pipeline in Python that checks 8 rules on every incoming file.",
        "Reduced report prep from two days to 3 hours with SQL and Excel.",
        "Trained a logistic regression on 50,000 rows and reported AUC 0.81 on a holdout set.",
    ]


SHARED = "Built a pipeline in Python that checks 8 rules on every incoming file."
RESUMES = {
    "app1": [SHARED, "Reduced report prep from two days to 3 hours."],
    "app2": [SHARED + " Used by 3 teams.", "Trained a model on 50,000 rows."],
    "app3": ["Wrote SQL for weekly KPIs.", "Trained a model on 50,000 rows."],
    "app4": ["Something else entirely, about dashboards."],
}


def test_scan_counts_similar_wording_as_uses():
    lib = bullets.scan(RESUMES, ["app1"], {"app1": "da"})
    assert lib["baseline"] == 0.25 and lib["applications"] == 4
    shared = next(b for b in lib["bullets"] if b["text"] == SHARED)
    assert shared["uses"] == ["app1", "app2"]       # near-identical wording counts
    assert shared["successes"] == ["app1"]
    assert shared["family"] == "da"
    assert len(lib["bullets"]) == 2                  # only bullets on successful resumes


def test_reuse_requires_success_rate():
    lib = bullets.scan(RESUMES, ["app1"])
    ok = bullets.reusable(lib)
    assert [b["text"] for b in ok] == [SHARED]       # 2 uses, 1 success, 0.5 >= 0.25
    assert bullets.reusable(bullets.scan(RESUMES, [])) == []


def test_single_use_not_enough():
    lib = bullets.scan(RESUMES, ["app4"])
    assert bullets.reusable(lib) == []               # used once only


def test_family_filter():
    lib = bullets.scan(RESUMES, ["app1"], {"app1": "da"})
    assert bullets.reusable(lib, family="ai") == []
    assert len(bullets.reusable(lib, family="da")) == 1
