"""Mechanical checks for a skill folder: python3 lint_skill.py <skill-dir> [<skill-dir> ...]

Catches what a reader misses: broken file pointers, oversized descriptions,
near-duplicate lines, and how much of the body steers by prohibition.
Judgement calls (no-ops, leading words, completion criteria) stay with the reviewer.
Exit code 1 if any ERROR is found.
"""

import difflib
import re
import sys
from pathlib import Path

DESC_WORDS_MODEL = 60   # model-invoked: always loaded, every word costs every turn
DESC_WORDS_USER = 15    # user-invoked: a one-line human summary
BODY_LINES = 150        # past this, look for reference to disclose into sibling files
NEGATION = re.compile(r"\b(never|don't|do not|must not|no longer|avoid)\b", re.I)
PATH_LIKE = re.compile(r"`([^`\s]+\.(?:md|py|sh|tex|json|txt|yaml|yml|js|ts))`|\]\(([^)\s]+)\)")


def parse(skill_md):
    text = skill_md.read_text(encoding="utf-8")
    m = re.match(r"---\n(.*?)\n---\n(.*)", text, re.S)
    if not m:
        return None, text, 0
    meta = {}
    for line in m.group(1).splitlines():
        if ":" in line and not line.startswith(" "):
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip().strip('"').strip("'")
    return meta, m.group(2), m.group(1).count("\n") + 3


def norm(line):
    line = re.sub(r"^\s*([-*]|\d+\.|- \[ \])\s*", "", line.lower())
    return re.sub(r"[^a-z0-9 ]", "", line).strip()


def lint(skill_dir):
    errors, warnings, notes = [], [], []
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return [f"no SKILL.md in {skill_dir}"], [], []
    meta, body, offset = parse(skill_md)
    if meta is None:
        return ["missing YAML frontmatter (--- name/description ---)"], [], []

    name = meta.get("name", "")
    if not name:
        errors.append("frontmatter has no name")
    elif name != skill_dir.name:
        warnings.append(f"name '{name}' differs from folder '{skill_dir.name}'")
    if name and not re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", name):
        errors.append(f"name '{name}' is not lowercase-hyphenated")

    desc = meta.get("description", "")
    user_invoked = meta.get("disable-model-invocation", "").lower() == "true"
    words = len(desc.split())
    if not desc:
        errors.append("frontmatter has no description")
    elif user_invoked:
        if words > DESC_WORDS_USER:
            warnings.append(f"user-invoked description is {words} words; a human summary fits in {DESC_WORDS_USER}")
        if re.search(r"\buse (this )?(when|whenever)\b", desc, re.I):
            warnings.append("user-invoked description carries trigger phrasing the model never reads")
    elif words > DESC_WORDS_MODEL:
        warnings.append(f"description is {words} words (always loaded); aim for <= {DESC_WORDS_MODEL}: "
                        "leading word first, one trigger per branch, no how-it-works")

    lines, fenced = [], False
    for line in body.splitlines():  # blank out code fences: templates repeat on purpose
        fenced ^= line.lstrip().startswith("```")
        lines.append("" if fenced or line.lstrip().startswith("```") else line)
    if len(lines) > BODY_LINES:
        warnings.append(f"body is {len(lines)} lines; disclose branch-only reference into sibling files")

    # Pointers into the skill's own folder must resolve; other paths are listed for a human look.
    # A bare filename is fine if it exists anywhere in the folder (or is a file the run creates).
    own_dirs = {p.name for p in skill_dir.iterdir() if p.is_dir()}
    own_files = {p.name for p in skill_dir.rglob("*") if p.is_file()}
    seen = set()
    for m in PATH_LIKE.finditer(body):
        ref = (m.group(1) or m.group(2)).split("#")[0]
        if not ref or ref in seen or ref.startswith(("http", "mailto")) or any(c in ref for c in "<>*…"):
            continue
        seen.add(ref)
        if ref.split("/")[0] in own_dirs or (m.group(2) and not ref.startswith("..")):
            if not (skill_dir / ref).exists():
                errors.append(f"pointer to missing file: {ref}")
        elif "/" not in ref and ref.split("/")[-1] in own_files:
            continue
        else:
            notes.append(f"path outside the skill folder (exists, or an output the run creates?): {ref}")

    neg = [l.strip() for l in lines if NEGATION.search(l)]
    if lines and neg:
        share = len(neg) / max(1, sum(1 for l in lines if l.strip()))
        (warnings if share > 0.2 and len(neg) >= 5 else notes).append(
            f"{len(neg)} lines steer by prohibition ({share:.0%} of non-blank lines); "
            "keep hard guardrails, rewrite the rest as the positive target")

    content = [(i + offset, norm(l)) for i, l in enumerate(lines) if len(norm(l).split()) >= 4]
    for a in range(len(content)):
        for b in range(a + 1, len(content)):
            ratio = difflib.SequenceMatcher(None, content[a][1], content[b][1]).ratio()
            if ratio >= 0.75:
                warnings.append(f"near-duplicate lines {content[a][0]} and {content[b][0]} "
                                f"({ratio:.0%}): keep one source of truth")
    return errors, warnings, notes


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    failed = False
    for arg in sys.argv[1:]:
        errors, warnings, notes = lint(Path(arg).resolve())
        print(f"== {arg}")
        for label, items in (("ERROR", errors), ("WARN", warnings), ("note", notes)):
            for item in items:
                print(f"  {label}: {item}")
        if not (errors or warnings or notes):
            print("  clean")
        failed |= bool(errors)
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
