"""Command line: python -m jobagent <audit|gaps|bullets> ...

  audit   TEX --facts F --example E [--pdf P] [--jd-map M] [--others DIR] [--approved LIB.json] [--ban PHRASE ...]
  gaps    JD_MAP [JD_MAP ...]
  bullets scan DIR --success APP[,APP...] [--families APP=ai,APP=da ...] [--out LIB.json]
               DIR holds one PDF per sent application, named <application id>.pdf
  bullets reusable LIB.json [--family ai|ds|da]
"""
import argparse
import glob
import json
import os
import sys

from . import audit, bullets, gaps


def _load(path):
    return json.load(open(path)) if os.path.exists(path) else {}


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
    b.add_argument("action", choices=["scan", "reusable"])
    b.add_argument("path", help="scan: folder of <app>.pdf files; reusable: library JSON")
    b.add_argument("--success", default="", help="comma-separated application ids")
    b.add_argument("--families", default="", help="comma-separated APP=family pairs")
    b.add_argument("--family")
    b.add_argument("--out")

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

    if args.action == "scan":
        resumes = {}
        for pdf in sorted(glob.glob(os.path.join(args.path, "*.pdf"))):
            app = os.path.splitext(os.path.basename(pdf))[0]
            resumes[app] = bullets.pdf_bullets(audit.pdf_text(pdf))
        fams = dict(x.split("=", 1) for x in args.families.split(",") if "=" in x)
        lib = bullets.scan(resumes, [x for x in args.success.split(",") if x], fams)
        text = json.dumps(lib, indent=1)
        if args.out:
            open(args.out, "w").write(text)
            print(f"{len(lib['bullets'])} bullets from {lib['applications']} applications -> {args.out}")
        else:
            print(text)
        return 0
    print(json.dumps(bullets.reusable(_load(args.path), args.family), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
