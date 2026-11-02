"""Which numbers on the resume are not in the knowledge base?

python3 numbers.py resume.pdf kb.txt

kb.txt is the text of the knowledge-base pages read this run (Profile, experience pages, the projects used),
saved from the Notion fetch output. Every number on the resume must appear there.
- Commas, "+", "%", "K" and trailing zeros are ignored, so "1,000+" matches "1000".
- A number with three or more digits or a decimal ("65,752", "17.0%") only has to appear in kb.txt.
- A small whole number ("8 dashboards", "60%") also needs its next word in the knowledge base within a few words
  after the same number, because small numbers appear everywhere by chance ("8 lines of inquiry").
- Skipped: the name and contact lines, years (2024) and date ranges.
Exit 0 when every number is found, 2 otherwise.
"""

import re
import subprocess
import sys

NUM = re.compile(r"(?<![\w.])\$?(\d[\d,]*(?:\.\d+)?)(\+|%|x\b|K\b|M\b)?", re.I)
YEAR = re.compile(r"^(19[5-9]\d|20[0-3]\d)$")
STOP = {"of", "the", "a", "an", "to", "and", "in", "for", "at", "vs", "per", "across", "with", "on", "by", "from",
        "into", "than", "about", "over", "more", "or", "each", "every", "x"}
WORD = re.compile(r"[A-Za-z][A-Za-z-]*")


def norm(n):
    n = n.replace(",", "")
    return n.rstrip("0").rstrip(".") if "." in n else n


def next_word(text, end):
    for w in WORD.findall(text[end:end + 40]):
        if w.lower() not in STOP:
            return w.lower()
    return ""


def kb_index(kb):
    """{number: [following text]} for every number in the knowledge base."""
    idx = {}
    for m in NUM.finditer(kb):
        idx.setdefault(norm(m.group(1)), []).append(kb[m.end():m.end() + 60].lower())
    return idx


def is_date(raw, suffix):
    """A bare year such as 2024; "2,000+" or "2000%" are counts."""
    return not suffix and "," not in raw and bool(YEAR.match(raw))


def check(text, kb):
    idx = kb_index(kb)
    unknown = []
    for line in text.splitlines()[2:]:  # skip name and contact lines
        for m in NUM.finditer(line):
            raw, suffix = m.group(1), m.group(2) or ""
            n = norm(raw)
            if is_date(raw, suffix):
                continue
            hits = idx.get(n)
            ok = bool(hits)
            small = "." not in n and len(n) <= 2
            if ok and small:
                w = next_word(line, m.end())
                ok = not w or any(w[:4] in after for after in hits)
            if not ok:
                unknown.append((raw + suffix, line.strip()[:110]))
    return unknown


def main():
    pdf, kb_path = sys.argv[1], sys.argv[2]
    text = subprocess.run(["pdftotext", "-layout", pdf, "-"], capture_output=True, text=True, check=True).stdout
    unknown = check(text, open(kb_path, encoding="utf-8").read())
    if not unknown:
        print("NUMBERS OK: every number is in the knowledge base")
        sys.exit(0)
    print(f"NUMBERS NOT IN THE KNOWLEDGE BASE: {len(unknown)} (remove each, or use a number the knowledge base holds)")
    for num, line in unknown:
        print(f"  {num:>8}  {line}")
    sys.exit(2)


if __name__ == "__main__":
    main()
