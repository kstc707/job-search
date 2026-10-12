"""Resume auditor: deterministic checks that run after every build (no model tokens).

Checks
- pages: PDF page count matches the expected count
- banned: no do-not-claim term (read from facts.md) and no extra phrase passed with --ban
- copies: no bullet copies the layout example (similarity >= 0.6)
- near_duplicates: bullets that repeat wording from other resumes (>= 0.8); allowed only
  when the bullet ID is in the approved reuse set (bullets with a proven success rate)
- coverage: share of job-map rows backed by real evidence (not GAP / CONFIRM / blank)
"""
import difflib
import os
import re
import subprocess

from . import texparse

_GAP_MARK = re.compile(r"\bGAP\b|\bCONFIRM\b|^\s*[—-]?\s*$", re.I)


def do_not_claim_terms(facts_text):
    """Terms from the '## Do not claim' section of facts.md."""
    m = re.search(r"## Do not claim[^\n]*\n(.*?)(?=\n## |\Z)", facts_text, re.S)
    if not m:
        return []
    terms = []
    for line in m.group(1).splitlines():
        line = line.strip().lstrip("-").strip()
        if not line:
            continue
        if ":" in line:  # "SAS: explanation" -> just the term
            line = line.split(":", 1)[0]
        line = line.rstrip(".")
        for part in re.split(r"[,()/]", line):
            part = re.sub(r"\b(tooling|statements)\b", "", part).strip()
            if len(part) >= 2:
                terms.append(part)
    return sorted(set(terms), key=str.lower)


def find_banned(text, terms):
    hits = []
    for term in terms:
        pattern = re.escape(term) if not term[0].isalnum() else r"\b" + re.escape(term) + r"\b"
        if term.endswith("%"):
            pattern = re.escape(term)
        if re.search(pattern, text, re.I):
            hits.append(term)
    return sorted(set(hits))


def similarity(a, b):
    return difflib.SequenceMatcher(None, texparse.normalize(a), texparse.normalize(b)).ratio()


def best_match(text, candidates, threshold, norm=texparse.normalize):
    """Highest similarity to any candidate, skipping pairs that can't reach the threshold."""
    # Order matters: difflib's ratio is not symmetric for strings over 200 characters
    # (autojunk). Use (text, candidate) like the skill's originality.py.
    sm = difflib.SequenceMatcher(None)
    sm.set_seq1(norm(text))
    best = 0.0
    for c in candidates:
        sm.set_seq2(norm(c))
        if sm.real_quick_ratio() < threshold or sm.quick_ratio() < threshold:
            continue
        best = max(best, sm.ratio())
    return best


def copies_of_example(items, example_items, threshold=0.6):
    """Same rule as the skill's originality.py: plain lowercase text, ratio >= 0.6."""
    out = []
    for b in items:
        best = best_match(b, example_items, threshold, norm=str.lower)
        if best >= threshold:
            out.append({"bullet": b, "score": round(best, 2)})
    return out


def near_duplicates(items, other_items, approved_ids=(), threshold=0.8):
    """Bullets that repeat wording found in other resumes, minus approved reuse."""
    approved = set(approved_ids)
    out = []
    for b in items:
        if texparse.bullet_id(b) in approved:
            continue
        best = best_match(b, other_items, threshold)
        if best >= threshold:
            out.append({"bullet": b, "id": texparse.bullet_id(b), "score": round(best, 2)})
    return out


def coverage(jd_map_text):
    """(covered rows, total rows) from the evidence table in jd_map.md."""
    rows = [r for r in jd_map_text.splitlines() if r.strip().startswith("|")]
    rows = [r for r in rows if not re.match(r"^\|\s*-", r.strip())][1:]  # drop header + rule
    total = covered = 0
    for r in rows:
        cells = [c.strip() for c in r.strip().strip("|").split("|")]
        if len(cells) < 2:
            continue
        total += 1
        if not _GAP_MARK.search(cells[1]):
            covered += 1
    return covered, total


def pdf_pages(pdf_path):
    out = subprocess.run(["pdfinfo", pdf_path], capture_output=True, text=True).stdout
    m = re.search(r"^Pages:\s+(\d+)", out, re.M)
    return int(m.group(1)) if m else None


def pdf_text(pdf_path):
    return subprocess.run(["pdftotext", pdf_path, "-"], capture_output=True, text=True).stdout


def audit(tex_path, facts_path, example_path, pdf_path=None, jd_map_path=None,
          other_tex_paths=(), approved_ids=(), expected_pages=2, extra_banned=()):
    tex = open(tex_path).read()
    items = texparse.bullets(tex)
    text = pdf_text(pdf_path) if pdf_path and os.path.exists(pdf_path) else texparse.clean(tex)
    terms = do_not_claim_terms(open(facts_path).read()) + list(extra_banned)
    example_items = texparse.bullets(open(example_path).read())
    others = []
    for p in other_tex_paths:
        if os.path.abspath(p) != os.path.abspath(tex_path):
            others += texparse.bullets(open(p).read())

    result = {
        "file": os.path.basename(tex_path),
        "pages": pdf_pages(pdf_path) if pdf_path and os.path.exists(pdf_path) else None,
        "banned": find_banned(text, terms),
        "copies": copies_of_example(items, example_items),
        "near_duplicates": near_duplicates(items, others, approved_ids),
        "bullets": len(items),
    }
    if jd_map_path and os.path.exists(jd_map_path):
        c, t = coverage(open(jd_map_path).read())
        result["coverage"] = round(c / t, 2) if t else None
        result["coverage_rows"] = f"{c}/{t}"
    problems = []
    if result["pages"] is not None and result["pages"] != expected_pages:
        problems.append(f"pages={result['pages']} (expected {expected_pages})")
    if result["banned"]:
        problems.append("banned terms: " + ", ".join(result["banned"]))
    if result["copies"]:
        problems.append(f"{len(result['copies'])} bullet(s) copy the example")
    if result["near_duplicates"]:
        problems.append(f"{len(result['near_duplicates'])} reused bullet(s) without a success record")
    result["problems"] = problems
    result["pass"] = not problems
    return result
