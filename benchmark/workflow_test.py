#!/usr/bin/env python3
"""Fixed-step resume workflow, for comparing against the agentic pipeline.

Two API calls per job, no agent loop, no tools:
  1. extract the posting's requirements (JSON)
  2. write the tailored resume (.tex) and its requirement map from those requirements,
     following the same skill rules, facts and template the agentic builders use

The current pipeline writes no cover letters, so this script writes none either.

After the API calls the script compiles each resume and runs the pipeline's own
`jobagent audit` and `jobagent score` (read-only), so both versions are graded the same way.
It never applies to a job and never writes to Notion or Tsenta.

Usage:
  export ANTHROPIC_API_KEY=...            # or any credential the SDK resolves
  python benchmark/workflow_test.py --random 5 --jd-dir <folder of jds/*.md>
  python benchmark/workflow_test.py jds/a.md jds/b.md ...
"""
import argparse
import glob
import json
import os
import random
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

import urllib.request

import anthropic

MODEL = "claude-opus-5-5"  # same model the agentic session and its builders run on
HERE = Path(__file__).resolve().parent
AGENT_DIR = HERE.parent / "agent"
DEFAULT_SKILL = Path(os.environ.get(
    "RESUME_SKILL_DIR",
    "/root/.claude/skills/synced/01f06a7f-3eda-4415-97be-1f77db0d4702_db9e79e0-6d97-43d5-b8c2-910b7efeec84/sai-resume-tailor",
))
BANS = ["JB Institute", "50%", "linkedin", "memphis.edu"]

REQUIREMENTS_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["core_problem", "responsibilities", "required_skills", "preferred_skills",
                 "keywords", "eligibility", "location_terms"],
    "properties": {
        "core_problem": {"type": "string"},
        "responsibilities": {"type": "array", "items": {"type": "string"}},
        "required_skills": {"type": "array", "items": {"type": "string"}},
        "preferred_skills": {"type": "array", "items": {"type": "string"}},
        "keywords": {"type": "array", "items": {"type": "string"}},
        "eligibility": {"type": "array", "items": {"type": "string"}},
        "location_terms": {"type": "string"},
    },
}


def call(client, log, job, step, system, user, max_tokens, effort, extra=None):
    """One streamed API call; records tokens and wall-clock time."""
    t0 = time.perf_counter()
    with client.messages.stream(
        model=MODEL,
        max_tokens=max_tokens,
        thinking={"type": "adaptive"},
        output_config={"effort": effort, **(extra or {})},
        system=system,
        messages=[{"role": "user", "content": user}],
    ) as stream:
        msg = stream.get_final_message()
    secs = time.perf_counter() - t0
    u = msg.usage
    rec = {
        "job": job, "step": step, "model": msg.model, "stop_reason": msg.stop_reason,
        "input_tokens": u.input_tokens, "output_tokens": u.output_tokens,
        "cache_read": getattr(u, "cache_read_input_tokens", 0) or 0,
        "cache_write": getattr(u, "cache_creation_input_tokens", 0) or 0,
        "seconds": round(secs, 2),
    }
    log.append(rec)
    print(f"  {step:<13} in={rec['input_tokens']:>7} out={rec['output_tokens']:>6} "
          f"cache_r={rec['cache_read']:>6} {secs:6.1f}s  stop={msg.stop_reason}")
    if msg.stop_reason == "refusal":
        raise RuntimeError(f"{job} {step}: model declined ({msg.stop_details})")
    if msg.stop_reason == "max_tokens":
        raise RuntimeError(f"{job} {step}: hit max_tokens; raise --max-tokens")
    return "".join(b.text for b in msg.content if b.type == "text")


def call_ollama(args, log, job, step, system, user, max_tokens, schema=None):
    """Same call through a local Ollama model (e.g. qwen3:4b); records the same fields."""
    sys_text = "\n\n".join(b["text"] for b in system)
    body = {
        "model": args.ollama_model, "stream": False, "think": args.think,
        "messages": [{"role": "system", "content": sys_text}, {"role": "user", "content": user}],
        "options": {"num_ctx": args.num_ctx, "num_predict": min(max_tokens, args.num_predict)},
    }
    if schema:
        body["format"] = schema
    t0 = time.perf_counter()
    req = urllib.request.Request(args.ollama_url.rstrip("/") + "/api/chat",
                                 data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=7200) as r:
        out = json.loads(r.read())
    secs = time.perf_counter() - t0
    rec = {
        "job": job, "step": step, "model": out.get("model"), "stop_reason": out.get("done_reason"),
        "input_tokens": out.get("prompt_eval_count", 0), "output_tokens": out.get("eval_count", 0),
        "cache_read": 0, "cache_write": 0, "seconds": round(secs, 2),
    }
    log.append(rec)
    print(f"  {step:<13} in={rec['input_tokens']:>7} out={rec['output_tokens']:>6} "
          f"{secs:6.1f}s  stop={rec['stop_reason']}")
    if rec["input_tokens"] >= args.num_ctx:
        print(f"  WARNING: prompt filled the {args.num_ctx}-token context; raise --num-ctx")
    if out.get("done_reason") == "length":
        raise RuntimeError(f"{job} {step}: hit num_predict; raise --num-predict")
    return out["message"]["content"]


def _gemini_schema(s):
    """Gemini's responseSchema takes an OpenAPI subset: drop additionalProperties."""
    if isinstance(s, dict):
        return {k: _gemini_schema(v) for k, v in s.items() if k != "additionalProperties"}
    if isinstance(s, list):
        return [_gemini_schema(v) for v in s]
    return s


def call_gemini(args, log, job, step, system, user, max_tokens, schema=None):
    """Same call through the Gemini API (free tier works); records the same fields."""
    key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    gen = {"maxOutputTokens": min(max_tokens, args.gemini_max_output)}
    if schema:
        gen.update(responseMimeType="application/json", responseSchema=_gemini_schema(schema))
    body = {
        "systemInstruction": {"parts": [{"text": "\n\n".join(b["text"] for b in system)}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": gen,
    }
    url = (f"https://generativelanguage.googleapis.com/v1beta/models/{args.gemini_model}"
           ":generateContent")
    req = urllib.request.Request(url, data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "x-goog-api-key": key})
    t0 = time.perf_counter()
    with urllib.request.urlopen(req, timeout=1800) as r:
        out = json.loads(r.read())
    secs = time.perf_counter() - t0
    um = out.get("usageMetadata", {})
    cand = (out.get("candidates") or [{}])[0]
    rec = {
        "job": job, "step": step, "model": out.get("modelVersion", args.gemini_model),
        "stop_reason": cand.get("finishReason"),
        "input_tokens": um.get("promptTokenCount", 0),
        # thinking tokens are billed as output, so count them with the visible output
        "output_tokens": um.get("candidatesTokenCount", 0) + um.get("thoughtsTokenCount", 0),
        "cache_read": um.get("cachedContentTokenCount", 0), "cache_write": 0,
        "seconds": round(secs, 2),
    }
    log.append(rec)
    print(f"  {step:<13} in={rec['input_tokens']:>7} out={rec['output_tokens']:>6} "
          f"{secs:6.1f}s  stop={rec['stop_reason']}")
    if rec["stop_reason"] == "MAX_TOKENS":
        raise RuntimeError(f"{job} {step}: hit maxOutputTokens; raise --gemini-max-output")
    if rec["stop_reason"] not in ("STOP", None):
        raise RuntimeError(f"{job} {step}: finishReason {rec['stop_reason']}")
    return "".join(p.get("text", "") for p in cand.get("content", {}).get("parts", [])
                   if not p.get("thought"))


def load_jd(path):
    text = Path(path).read_text()
    header, _, body = text.partition("\n}\n")
    try:
        meta = json.loads(header + "\n}")
    except json.JSONDecodeError:
        meta, body = {}, text
    return meta, body.strip(), text


def slug_of(path):
    return Path(path).stem


def run_cmd(args, cwd=None):
    t0 = time.perf_counter()
    p = subprocess.run(args, cwd=cwd, capture_output=True, text=True)
    return p, time.perf_counter() - t0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jobs", nargs="*", help="job description files (jds/<slug>.md)")
    ap.add_argument("--random", type=int, default=0, help="pick N random files from --jd-dir")
    ap.add_argument("--jd-dir", default="", help="folder(s) of jd .md files, comma-separated")
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--skill-dir", default=str(DEFAULT_SKILL))
    ap.add_argument("--builder-rules", default="", help="extra rules file (the agentic builder prompt)")
    ap.add_argument("--config", default=str(AGENT_DIR / "work" / "config.json"))
    ap.add_argument("--out", default=str(HERE / "test_outputs" / "workflow"))
    ap.add_argument("--effort", default="high", choices=["low", "medium", "high", "xhigh", "max"])
    ap.add_argument("--max-tokens", type=int, default=64000)
    ap.add_argument("--provider", default="anthropic", choices=["anthropic", "ollama", "gemini"])
    ap.add_argument("--ollama-model", default="qwen3:4b")
    ap.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    ap.add_argument("--num-ctx", type=int, default=32768, help="Ollama context window")
    ap.add_argument("--num-predict", type=int, default=12000, help="Ollama max output tokens")
    ap.add_argument("--think", action="store_true", help="let qwen3 think before answering (slower)")
    ap.add_argument("--gemini-model", default=os.environ.get("GEMINI_MODEL", "gemini-2.5-flash"),
                    help="any Gemini model your key can use; check AI Studio for the current free ones")
    ap.add_argument("--gemini-max-output", type=int, default=32000)
    args = ap.parse_args()

    jobs = list(args.jobs)
    if args.random:
        pool = sorted({p for d in args.jd_dir.split(",") if d for p in glob.glob(os.path.join(d, "*.md"))})
        if len(pool) < args.random:
            sys.exit(f"only {len(pool)} jd files found in {args.jd_dir}")
        seed = args.seed if args.seed is not None else random.randrange(10**6)
        jobs += random.Random(seed).sample(pool, args.random)
        print(f"random pick (seed {seed}): " + ", ".join(slug_of(j) for j in jobs))
    if not jobs:
        sys.exit("give job files or --random N --jd-dir DIR")

    skill = Path(args.skill_dir)
    skill_md = (skill / "SKILL.md").read_text()
    facts = (skill / "references" / "facts.md").read_text()
    preamble = skill / "templates" / "preamble.tex"
    example = skill / "examples" / "fedex_pricing_intern.tex"
    rules = Path(args.builder_rules).read_text() if args.builder_rules else ""

    # Identical across jobs and steps, so it is cached after the first call.
    shared_system = [{
        "type": "text",
        "text": ("You tailor resumes for Sai Teja Koppolu. Follow the skill below exactly; "
                 "it reflects his standing decisions.\n\n<skill>\n" + skill_md + "\n</skill>\n\n"
                 + (f"<builder_rules>\n{rules}\n</builder_rules>\n\n" if rules else "")
                 + "<facts>\n" + facts + "\n</facts>\n\n<preamble_tex>\n"
                 + preamble.read_text() + "\n</preamble_tex>"),
        "cache_control": {"type": "ephemeral"},
    }]

    if args.provider == "anthropic":
        try:
            client = anthropic.Anthropic()
            client._validate_headers(client.default_headers, {})  # fail fast if no credential resolves
        except TypeError:
            sys.exit("No Anthropic credential found. Set ANTHROPIC_API_KEY (or ANTHROPIC_AUTH_TOKEN) "
                     "and run again. Nothing was sent.")

        def step_call(job, step, user, max_tokens, schema=None):
            extra = {"format": {"type": "json_schema", "schema": schema}} if schema else None
            return call(client, log, job, step, shared_system, user, max_tokens, args.effort, extra)
    elif args.provider == "gemini":
        if not (os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")):
            sys.exit("Set GEMINI_API_KEY (free from Google AI Studio) and run again. Nothing was sent.")

        def step_call(job, step, user, max_tokens, schema=None):
            return call_gemini(args, log, job, step, shared_system, user, max_tokens, schema)
    else:
        def step_call(job, step, user, max_tokens, schema=None):
            return call_ollama(args, log, job, step, shared_system, user, max_tokens, schema)
    out_root = Path(args.out)
    out_root.mkdir(parents=True, exist_ok=True)
    log, results = [], []
    run_t0 = time.perf_counter()

    for jd_path in jobs:
        slug = slug_of(jd_path)
        print(f"\n== {slug}")
        meta, body, raw = load_jd(jd_path)
        job_dir = out_root / slug
        job_dir.mkdir(parents=True, exist_ok=True)
        (job_dir / "jd.md").write_text(raw)
        job_t0 = time.perf_counter()
        res = {"job": slug, "title": meta.get("title", ""), "company": meta.get("companyName", "")}
        try:
            # Step 1: requirements
            req_text = step_call(
                slug, "requirements",
                "Step 1 of the skill workflow only: decode this job description. Return the "
                "core problem, responsibilities, required vs preferred skills, exact ATS keywords, "
                "eligibility conditions to flag, and the location/onsite terms.\n\n<job>\n"
                + raw + "\n</job>",
                max_tokens=16000, schema=REQUIREMENTS_SCHEMA,
            )
            reqs = json.loads(req_text)
            (job_dir / "requirements.json").write_text(json.dumps(reqs, indent=2))

            # Step 2: resume
            company = re.sub(r"[^A-Za-z0-9]", "", meta.get("companyName", slug))[:24] or slug
            role = re.sub(r"[^A-Za-z0-9]", "", meta.get("title", "Role"))[:40] or "Role"
            name = f"SaiTejaKoppolu_{company}_{role}"
            resume_text = step_call(
                slug, "resume",
                "Steps 2-4 of the skill workflow, in one pass, from these extracted requirements "
                "and the job description. Output exactly two fenced blocks and nothing else:\n"
                "1. ```markdown``` holding jd_map.md (one row per responsibility -> fact or GAP)\n"
                "2. ```latex``` holding the complete resume .tex: it must start with "
                "\\input{preamble}, use only the preamble's macros, and follow every content, "
                "layout and bullet-count rule in the skill.\n\n<requirements>\n"
                + json.dumps(reqs, indent=2) + "\n</requirements>\n\n<job>\n" + raw + "\n</job>",
                max_tokens=args.max_tokens,
            )
            md = re.search(r"```markdown\n(.*?)```", resume_text, re.S)
            tex = re.search(r"```latex\n(.*?)```", resume_text, re.S)
            if not tex:
                raise RuntimeError("no ```latex block in the resume response")
            (job_dir / "jd_map.md").write_text(md.group(1) if md else "")
            tex_path = job_dir / f"{name}.tex"
            tex_path.write_text(tex.group(1))
            shutil.copy(preamble, job_dir / "preamble.tex")
            res["api_seconds"] = round(sum(r["seconds"] for r in log if r["job"] == slug), 2)

            # Local checks (no tokens): compile, audit, score
            p, _ = run_cmd(["pdflatex", "-interaction=nonstopmode", tex_path.name], cwd=job_dir)
            pdf = tex_path.with_suffix(".pdf")
            res["compiled"] = pdf.exists()
            if pdf.exists():
                info, _ = run_cmd(["pdfinfo", str(pdf)])
                m = re.search(r"Pages:\s+(\d+)", info.stdout)
                res["pages"] = int(m.group(1)) if m else None
                aud_args = [sys.executable, "-m", "jobagent", "audit", str(tex_path),
                            "--facts", str(skill / "references" / "facts.md"),
                            "--example", str(example), "--pdf", str(pdf),
                            "--jd-map", str(job_dir / "jd_map.md"), "--others", str(out_root)]
                for b in BANS:
                    aud_args += ["--ban", b]
                a, _ = run_cmd(aud_args, cwd=AGENT_DIR)
                try:
                    aud = json.loads(a.stdout)
                    res.update(audit_pass=aud.get("pass"), coverage=aud.get("coverage"),
                               audit_problems=aud.get("problems"))
                except json.JSONDecodeError:
                    res["audit_error"] = (a.stderr or a.stdout)[-400:]
                if Path(args.config).exists():
                    s, _ = run_cmd([sys.executable, "-m", "jobagent", "score", str(Path(jd_path).resolve()),
                                    "--config", args.config,
                                    "--facts", str(skill / "references" / "facts.md"),
                                    "--jd-map", str(job_dir / "jd_map.md"),
                                    "--tex", str(tex_path), "--pdf", str(pdf)], cwd=AGENT_DIR)
                    try:
                        sc = json.loads(s.stdout)
                        res.update(score=sc.get("score"), decision=sc.get("decision"))
                    except json.JSONDecodeError:
                        res["score_error"] = (s.stderr or s.stdout)[-400:]
        except (anthropic.APIStatusError, anthropic.APIConnectionError, RuntimeError,
                json.JSONDecodeError, OSError) as e:
            res["error"] = f"{type(e).__name__}: {e}"
            print(f"  ERROR {res['error']}")
        calls = [r for r in log if r["job"] == slug]
        res.update(
            calls=len(calls),
            input_tokens=sum(r["input_tokens"] for r in calls),
            output_tokens=sum(r["output_tokens"] for r in calls),
            cache_read=sum(r["cache_read"] for r in calls),
            cache_write=sum(r["cache_write"] for r in calls),
            total_seconds=round(time.perf_counter() - job_t0, 2),
        )
        print(f"  job total: {res['calls']} calls, in={res['input_tokens']} out={res['output_tokens']} "
              f"cache_r={res['cache_read']} cache_w={res['cache_write']}, {res['total_seconds']}s")
        results.append(res)
        # write after every job so a stopped run keeps what finished
        (out_root / "calls.json").write_text(json.dumps(log, indent=2))
        (out_root / "results.json").write_text(json.dumps(results, indent=2))

    (out_root / "calls.json").write_text(json.dumps(log, indent=2))
    (out_root / "results.json").write_text(json.dumps(results, indent=2))

    cols = ["job", "calls", "input_tokens", "cache_read", "cache_write", "output_tokens",
            "api_seconds", "total_seconds", "pages", "audit_pass", "coverage", "score"]
    print("\n" + " | ".join(cols))
    print(" | ".join("---" for _ in cols))
    for r in results:
        print(" | ".join(str(r.get(c, "")) for c in cols))
    tot = {c: sum((r.get(c) or 0) for r in results) for c in cols[1:8]}
    print(" | ".join(["TOTAL"] + [str(round(tot[c], 2)) for c in cols[1:8]] + ["", "", "", ""]))
    print(f"\nrun wall-clock: {time.perf_counter() - run_t0:.1f}s; outputs in {out_root}")


if __name__ == "__main__":
    main()
