"""Command line: python -m jobagent <audit|gaps|bullets> ...

  audit   TEX --facts F --example E [--pdf P] [--jd-map M] [--others DIR] [--approved LIB.json] [--ban PHRASE ...]
  gaps    JD_MAP [JD_MAP ...]
  bullets scan DIR --success APP[,APP...] [--families APP=ai,APP=da ...] [--out LIB.json]
               DIR holds one PDF per sent application, named <application id>.pdf
  bullets reusable LIB.json [--family ai|ds|da]
  screen  JD [JD ...] --config C
  score   JD --config C --facts F [--jd-map M] [--tex T] [--pdf P] [--signal 0-1]
  rank    JD [JD ...] --config C --facts F [--cap N]   (pre-build gate: today's jobs, best first)
          JD files: optional JSON header from the job feed, then the posting text
"""
import argparse
import glob
import json
import os
import sys

from . import audit, bullets, gaps, jd, score, screen, texparse


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

    sc = sub.add_parser("screen")
    sc.add_argument("jds", nargs="+")
    sc.add_argument("--config", required=True)

    for name in ("score", "rank"):
        x = sub.add_parser(name)
        x.add_argument("jds", nargs="+" if name == "rank" else 1)
        x.add_argument("--config", required=True)
        x.add_argument("--facts", required=True)
        if name == "score":
            x.add_argument("--jd-map")
            x.add_argument("--tex")
            x.add_argument("--pdf")
            x.add_argument("--signal", type=float)
        else:
            x.add_argument("--cap", type=int)

    args = p.parse_args(argv)

    if args.cmd in ("screen", "score", "rank"):
        cfg = json.load(open(args.config))
    if args.cmd == "screen":
        out = {}
        for path in args.jds:
            meta, text = jd.load(path)
            out[path] = screen.screen(meta, text, cfg)
        print(json.dumps(out, indent=2))
        return 0
    if args.cmd in ("score", "rank"):
        facts = open(args.facts).read()
    if args.cmd == "score":
        meta, text = jd.load(args.jds[0])
        res = score.score(
            meta, text, cfg, facts,
            jd_map_text=open(args.jd_map).read() if args.jd_map else None,
            resume_text=texparse.clean(open(args.tex).read()) if args.tex else None,
            pdf_text=score.pdf_text_or_none(args.pdf), signal=args.signal)
        print(json.dumps(res, indent=2))
        return 0
    if args.cmd == "rank":
        results = []
        for path in args.jds:
            meta, text = jd.load(path)
            r = score.score(meta, text, cfg, facts)
            r["file"] = path
            results.append(r)
        cap = args.cap or cfg.get("daily_cap", 15)
        print(json.dumps({"act": score.rank(results, cap),
                          "skipped": [{"file": r["file"], "score": r["score"],
                                       "knockouts": r["knockouts"]}
                                      for r in results if r["decision"] == "skip"]}, indent=2))
        return 0

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
