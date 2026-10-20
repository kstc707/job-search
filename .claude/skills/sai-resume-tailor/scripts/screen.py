"""How likely is this resume to pass an automated filter (ATS) for this posting?

python3 screen.py resume.pdf jd_terms.json [--min 80]

Reads the PDF's text layer the way an ATS does and scores it 0-100:
  parse       15  text extracts cleanly; email, phone, standard section headings, plain-hyphen dates, <= 2 pages
  required    40  share of the posting's required terms found (exact term or a listed variant)
  preferred   15  share of preferred terms found
  in context  10  share of found required terms that also appear outside the Skills section
  title       10  the posting's job title near the top
  knockouts   10  stated years of experience and degree meet the posting's minimums

jd_terms.json (written in workflow step 1):
  {"title": "Data Analyst", "required": ["SQL", "Power BI|PowerBI"], "preferred": ["Tableau"],
   "years_required": 2, "degree": "bachelor", "knockouts": ["US citizenship required"]}
A "|" separates variants of one term. Exit 0 when the score reaches --min, 2 otherwise.
"""

import argparse
import json
import re
import subprocess
import sys

HEADINGS = {
    "summary": r"(professional )?summary|profile|objective",
    "education": r"education",
    "skills": r"(technical )?skills",
    "experience": r"(professional |work )?experience",
    "projects": r"projects",
}
DASHES = "‐‑‒–—―−"
DASH_DATE = re.compile(rf"\d{{4}}\s*[{DASHES}]\s*(?:[A-Z][a-z]+\.? )?(?:\d{{4}}|Present|Current)")
DEGREE_RANK = {"bachelor": 1, "master": 2, "phd": 3}


def pdf_text(path):
    text = subprocess.run(["pdftotext", path, "-"], capture_output=True, text=True, check=True).stdout
    pages = int(re.search(r"Pages:\s+(\d+)", subprocess.run(
        ["pdfinfo", path], capture_output=True, text=True, check=True).stdout).group(1))
    return text, pages


def pattern(variant):
    """Whole-term match that also crosses a line wrap (an ATS reads the text as one stream)."""
    words = [re.escape(w) for w in variant.split()]
    return rf"(?<![\w+#]){r'(?:-?\s+|-)'.join(words) if len(words) > 1 else words[0]}(?![\w+#])"


def found(term, text):
    return any(re.search(pattern(v.strip()), text, re.I) for v in term.split("|"))


def sections(text):
    """{heading: section text} from lines that are exactly a standard heading."""
    marks = []
    for m in re.finditer(r"^[ \t\f]*([A-Za-z ]{4,40})[ \t]*$", text, re.M):
        for name, pat in HEADINGS.items():
            if re.fullmatch(pat, m.group(1).strip(), re.I):
                marks.append((m.start(), name))
    marks.sort()
    return {name: text[s:(marks[i + 1][0] if i + 1 < len(marks) else len(text))]
            for i, (s, name) in enumerate(marks)}


def score(text, pages, jd):
    fixes, notes = [], []  # fixes: (points lost, what to change)
    parts = sections(text)

    parse = 15
    if len(text.strip()) < 200 or "(cid:" in text or "�" in text:
        parse = 0
        fixes.append((15, "the text layer is empty or garbled: an ATS would read nothing"))
    else:
        if not re.search(r"[\w.+-]+@[\w-]+\.[\w.]+", text):
            parse -= 3; fixes.append((3, "no email in the text layer"))
        if not re.search(r"\+?\d[\d\s().-]{8,}\d", text):
            parse -= 3; fixes.append((3, "no phone number in the text layer"))
        missing = [h for h in HEADINGS if h not in parts]
        if missing:
            lost = min(6, 2 * len(missing)); parse -= lost
            fixes.append((lost, f"standard headings not found: {', '.join(missing)}"))
        if DASH_DATE.search(text):
            parse -= 3; fixes.append((3, "a date range uses an en-dash; write 'Jun 2022 - Jul 2024'"))
        if pages > 2:
            parse -= 3; fixes.append((3, f"{pages} pages; keep to two"))
    parse = max(parse, 0)

    req, pref = jd.get("required", []), jd.get("preferred", [])
    hit_req = [t for t in req if found(t, text)]
    miss_req = [t for t in req if t not in hit_req]
    required = 40 * len(hit_req) / len(req) if req else 40
    if miss_req:
        fixes.append((40 - required, "required terms missing: " + ", ".join(t.split("|")[0] for t in miss_req)))
    miss_pref = [t for t in pref if not found(t, text)]
    preferred = 15 * (len(pref) - len(miss_pref)) / len(pref) if pref else 15
    if miss_pref:
        fixes.append((15 - preferred, "preferred terms missing: " + ", ".join(t.split("|")[0] for t in miss_pref)))

    skills = parts.get("skills", "")
    rest = text.replace(skills, " ") if skills else text
    only_listed = [t for t in hit_req if not found(t, rest)]
    context = 10 * (len(hit_req) - len(only_listed)) / len(hit_req) if hit_req else 0
    if only_listed:
        fixes.append((10 - context, "required terms only in Skills, put them in a bullet too: "
                      + ", ".join(t.split("|")[0] for t in only_listed)))

    title, top = jd.get("title", ""), text[: max(400, len(text) // 4)]
    if not title or found(title, top):
        title_pts = 10
    elif all(found(w, top) for w in re.findall(r"[A-Za-z+#]{3,}", title)):
        title_pts = 5; fixes.append((5, f"use the exact title '{title}' in the summary's first line"))
    else:
        title_pts = 0; fixes.append((10, f"the posting's title '{title}' is not near the top"))

    knock = 10
    need_years = jd.get("years_required") or 0
    stated = [int(n) for n in re.findall(r"(\d+)\+?\s+years", text, re.I)]
    if need_years and max(stated, default=0) < need_years:
        knock -= 6; fixes.append((6, f"posting asks for {need_years}+ years; state years of experience in the summary"))
    need_deg = DEGREE_RANK.get((jd.get("degree") or "").lower(), 0)
    have_deg = max([r for k, r in [("bachelor|b\\.s|b\\.tech", 1), ("master|\\bms\\b|m\\.s", 2),
                                   ("ph\\.?d", 3)] if re.search(k, text, re.I)], default=0)
    if need_deg and have_deg < need_deg:
        knock -= 4; fixes.append((4, f"posting asks for a {jd['degree']} degree; it is not visible"))
    for k in jd.get("knockouts", []):
        notes.append(f"knockout the resume cannot change: {k}")

    for t in hit_req:
        n = sum(len(re.findall(pattern(v.strip()), text, re.I)) for v in t.split("|"))
        if n > 8:
            notes.append(f"'{t.split('|')[0]}' appears {n} times; AI screeners read that as stuffing")

    parts_pts = {"parse": parse, "required": required, "preferred": preferred,
                 "in context": context, "title": title_pts, "knockouts": knock}
    return round(sum(parts_pts.values())), parts_pts, sorted(fixes, reverse=True), notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("pdf")
    ap.add_argument("terms")
    ap.add_argument("--min", type=int, default=80)
    a = ap.parse_args()
    text, pages = pdf_text(a.pdf)
    with open(a.terms, encoding="utf-8") as f:
        jd = json.load(f)
    total, parts, fixes, notes = score(text, pages, jd)
    print(f"ATS SCORE {total}/100 ({'PASS' if total >= a.min else 'BELOW ' + str(a.min)})")
    print("  " + " · ".join(f"{k} {v:.0f}" for k, v in parts.items()))
    for lost, what in fixes:
        print(f"  -{lost:.0f}  {what}")
    for n in notes:
        print(f"  note: {n}")
    sys.exit(0 if total >= a.min else 2)


if __name__ == "__main__":
    main()
