"""Command line: python -m jobagent <audit|gaps|bullets> ...

  audit   TEX --facts F --example E [--pdf P] [--jd-map M] [--others DIR] [--approved LIB.json] [--ban PHRASE ...]
  gaps    JD_MAP [JD_MAP ...]
  bullets use     LIB.json TEX --app ID --title "Job title"
  bullets outcome LIB.json --app ID
  bullets reusable LIB.json [--family ai|ds|da]
"""
import argparse
import glob
import json
import os
import sys

from . import audit, bullets, gaps


def _load(path):
    return json.load(open(path)) if os.path.exists(path) else []


def main(argv=None):
    p = argparse.ArgumentParser(prog="jobagent")
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("audit")
    a.add_argument("tex")
    a.add_argument("--facts", required=True)
    a.add_argument("--example", required=True)
    a.add_argument("--pdf")
    a.add_argument("--jd-map")
    a.add_argument("--others", help="folder holding other resumes (*/*.tex)")
    a.add_argument("--approved", help="bullet library JSON; reusable bullets are allowed")
    a.add_argument("--pages", type=int, default=2)
    a.add_argument("--ban", action="append", default=[], help="extra banned phrase (repeatable)")

    g = sub.add_parser("gaps")
    g.add_argument("maps", nargs="+")

    b = sub.add_parser("bullets")
    b.add_argument("action", choices=["use", "outcome", "reusable"])
    b.add_argument("library")
    b.add_argument("tex", nargs="?")
    b.add_argument("--app")
    b.add_argument("--title", default="")
    b.add_argument("--family")

    args = p.parse_args(argv)

    if args.cmd == "audit":
        others = glob.glob(os.path.join(args.others, "*", "*.tex")) if args.others else []
        others = [o for o in others if not o.endswith("preamble.tex")]
        approved = [x["id"] for x in bullets.reusable(_load(args.approved))] if args.approved else []
        res = audit.audit(args.tex, args.facts, args.example, args.pdf, args.jd_map,
                          others, approved, args.pages, args.ban)
        print(json.dumps(res, indent=2))
        return 0 if res["pass"] else 1

    if args.cmd == "gaps":
        texts = [open(m).read() for m in args.maps]
        print(gaps.table(gaps.count(texts), len(texts)))
        return 0

    lib = _load(args.library)
    if args.action == "use":
        fam = args.family or bullets.family_for_title(args.title)
        bullets.record_use(lib, open(args.tex).read(), args.app, fam)
    elif args.action == "outcome":
        bullets.record_outcome(lib, args.app)
    else:
        print(json.dumps(bullets.reusable(lib, args.family), indent=2))
        return 0
    json.dump(lib, open(args.library, "w"), indent=1)
    print(f"library: {len(lib)} bullets")
    return 0


if __name__ == "__main__":
    sys.exit(main())
