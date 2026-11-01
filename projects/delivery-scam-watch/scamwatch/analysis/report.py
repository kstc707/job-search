"""Produce every result and chart from the database: `python -m scamwatch report`.

Writes outputs/results.json and outputs/*.png. Everything is recomputed from collected data
plus the frozen generator A and the triage review CSV, so anyone can reproduce it.
"""

from __future__ import annotations

import csv
import json
from datetime import UTC, datetime

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from ..config import PROJECT_ROOT  # noqa: E402
from ..defang import defang  # noqa: E402
from . import dataset  # noqa: E402
from . import experiment as ex  # noqa: E402
from .features import FEATURES, frame, is_infrastructure  # noqa: E402
from .model import MODEL_FEATURES, evaluate, make_model, out_of_fold, recall_at_precision  # noqa: E402

OUT = PROJECT_ROOT / "outputs"
REVIEW = PROJECT_ROOT / "data" / "review" / "stream_review_2026-11-01.csv"
MINUTES_PER_TRIAGE = 5  # assumption: a quick look at one domain name and its registration record


def collection_stats(conn) -> dict:
    rows = conn.execute(
        """SELECT s.name, count(DISTINCT r.id), coalesce(sum(r.items_seen), 0), min(r.started_at), max(r.started_at)
           FROM sources s JOIN collector_runs r ON r.source_id = s.id
           WHERE s.name <> 'selftest' GROUP BY s.name ORDER BY s.name"""
    ).fetchall()
    stored = dict(
        conn.execute(
            """SELECT s.name, count(*) FROM observations o JOIN sources s ON s.id = o.source_id GROUP BY s.name"""
        ).fetchall()
    )
    regs = dict(conn.execute("SELECT status, count(*) FROM registrations GROUP BY status").fetchall())
    return {
        "sources": {
            n: {
                "runs": runs,
                "items_scanned_or_matched": int(seen),
                "stored": stored.get(n, 0),
                "first_run": str(a),
                "last_run": str(b),
            }
            for n, runs, seen, a, b in rows
        },
        "rdap_lookups": regs,
    }


def stream_triage(df: pd.DataFrame, scam_model, threshold: float) -> dict:
    """Funnel for new domains: keyword match -> brand-word rule -> infrastructure suppression -> model."""
    stream = df[df.set == "stream"].copy()
    branded = stream[stream.brand.notna()].copy()
    infra = branded.fqdn.map(is_infrastructure).astype(bool) if len(branded) else pd.Series(dtype=bool)
    stage1 = branded[~infra].copy()
    stage1["score"] = scam_model.predict_proba(frame(stage1.fqdn.tolist())[FEATURES])[:, 1] if len(stage1) else []
    stage1["flagged"] = stage1.score >= threshold
    review = {r["fqdn"]: r for r in csv.DictReader(REVIEW.open())} if REVIEW.exists() else {}
    stage1["review"] = stage1.fqdn.map(lambda d: review.get(d, {}).get("label", "not_reviewed"))
    likely = stage1.review == "likely_scam"
    flagged = stage1[stage1.flagged]
    days = max(1, (stream.first_new_signal.max() - stream.first_new_signal.min()).days + 1)
    per_month = 30 / days
    reviewed = stage1[stage1.review != "not_reviewed"]
    return {
        "days_covered": int(days),
        "keyword_domains": len(stream),
        "after_stage1_rule": len(branded),
        "infrastructure_suppressed": int(infra.sum()),
        "infrastructure_examples": [defang(d) for d in branded[infra].fqdn.head(5)],
        "after_infrastructure_filter": len(stage1),
        "after_stage2_model": int(stage1.flagged.sum()),
        "model_threshold": round(float(threshold), 4),
        "model_note": "threshold set for 95% precision on lab data; on the stream it keeps every name the rule passes, "
        "so the rule does the cutting and the score only orders the queue",
        "review_counts": stage1.review.value_counts().to_dict(),
        "likely_scam_share_of_reviewed": round(float(likely.sum() / max(1, len(reviewed))), 3),
        "flagged_that_review_calls_likely_scam": int((stage1.flagged & likely).sum()),
        "likely_scams_missed_by_model": int((~stage1.flagged & likely).sum()),
        "flagged_that_review_calls_legitimate": int((stage1.flagged & (stage1.review == "legitimate")).sum()),
        "on_a_blocklist_now": int(stage1.on_blocklist.sum()),
        "likely_scams_not_on_any_blocklist": int((likely & ~stage1.on_blocklist).sum()),
        "analyst_hours_per_month": {
            "review_every_keyword_domain": round(len(stream) * per_month * MINUTES_PER_TRIAGE / 60, 1),
            "review_after_rule_and_model": round(len(flagged) * per_month * MINUTES_PER_TRIAGE / 60, 1),
            "assumption_minutes_per_review": MINUTES_PER_TRIAGE,
        },
        "flagged_examples": [defang(d) for d in flagged.sort_values("score", ascending=False).fqdn.head(15)],
        "rows": stage1[["fqdn", "brand", "score", "flagged", "review", "on_blocklist"]]
        .assign(
            fqdn=stage1.fqdn.map(defang),
            first_signal=stage1.first_new_signal.dt.strftime("%Y-%m-%d"),
            score=stage1.score.round(3),
        )
        .sort_values("score", ascending=False)
        .to_dict(orient="records"),
    }


def lead_times(df: pd.DataFrame, conn, started: datetime) -> dict:
    """Two real measurements of warning time:
    - stream domains (seen when registered or certified) that later reached a blocklist;
    - domains that newly appeared on OpenPhish after collection started (so their listing time is
      known), against their registration date from RDAP."""
    regs = dict(conn.execute("SELECT registered_domain, created_at FROM registrations WHERE created_at IS NOT NULL"))
    later = df[df.first_new_signal.notna() & df.first_listed.notna() & (df.first_listed > df.first_new_signal)]
    newly_listed = df[
        df.first_listed.notna() & (df.first_listed > started + pd.Timedelta(minutes=10)) & df.brand.notna()
    ]
    ages = [
        (r.fqdn, (r.first_listed - regs[r.registered_domain]).total_seconds() / 86400)
        for r in newly_listed.itertuples()
        if r.registered_domain in regs
    ]
    all_listed = df[df.on_blocklist & df.brand.notna()]
    listed_ages = [
        (r.first_listed - regs[r.registered_domain]).total_seconds() / 86400
        for r in all_listed.itertuples()
        if r.registered_domain in regs
    ]
    return {
        "stream_domains_later_listed": [
            {"fqdn": defang(r.fqdn), "hours": round((r.first_listed - r.first_new_signal).total_seconds() / 3600, 1)}
            for r in later.itertuples()
        ],
        "newly_listed_with_registration_date": [{"fqdn": defang(f), "age_days": round(a, 1)} for f, a in ages],
        "blocklisted_brand_domains_with_registration_date": len(listed_ages),
        "age_when_we_saw_them_listed_days": {
            "median": round(float(np.median(listed_ages)), 1) if listed_ages else None,
            "share_under_30_days": round(float(np.mean(np.array(listed_ages) < 30)), 3) if listed_ages else None,
        },
    }


def registration_summary(df: pd.DataFrame, conn) -> dict:
    """What registry records say about blocklisted brand domains: still registered or already gone,
    and how old the registered ones were when we first saw them listed."""
    regs = pd.DataFrame(
        conn.execute("SELECT registered_domain, created_at, registrar, status FROM registrations").fetchall(),
        columns=["registered_domain", "created_at", "registrar", "status"],
    )
    listed = df[df.on_blocklist & df.brand.notna()].drop_duplicates("registered_domain")
    from .features import HOSTING

    listed = listed[~listed.registered_domain.isin(HOSTING)]
    m = listed.merge(regs, on="registered_domain", how="inner")
    ok = m[m.status == "ok"].dropna(subset=["created_at"])
    age = (ok.first_listed - ok.created_at).dt.total_seconds() / 86400
    stream = (
        df[(df.set == "stream") & df.brand.notna()]
        .drop_duplicates("registered_domain")
        .merge(regs, on="registered_domain", how="inner")
    )
    return {
        "blocklisted_registered_domains": int(len(listed)),
        "looked_up": int(len(m)),
        "still_registered": int((m.status == "ok").sum()),
        "already_gone_not_found": int((m.status == "not_found").sum()),
        "age_days_when_seen_listed": {
            "n": int(len(age)),
            "median": round(float(age.median()), 1) if len(age) else None,
            "share_under_7_days": round(float((age < 7).mean()), 3) if len(age) else None,
            "share_under_30_days": round(float((age < 30).mean()), 3) if len(age) else None,
        },
        "top_registrars_blocklisted": ok.registrar.value_counts().head(5).to_dict(),
        "top_registrars_stream": stream[stream.status == "ok"].registrar.value_counts().head(5).to_dict(),
    }


def run(conn) -> dict:
    OUT.mkdir(exist_ok=True)
    started = conn.execute(
        "SELECT min(started_at) FROM collector_runs WHERE source_id <> (SELECT id FROM sources WHERE name = 'selftest')"
    ).fetchone()[0]
    df = dataset.load(conn)
    a = ex.load_generator_a()
    res = {"generated_at": datetime.now(UTC).isoformat(timespec="seconds"), "collection": collection_stats(conn)}

    # labelled sets
    keyword_scope = df[df.label.notna()].reset_index(drop=True)  # A's scope: all keyword domains
    brand_scope = keyword_scope[keyword_scope.brand.notna()].reset_index(drop=True)
    res["labelled"] = {
        "keyword_scope": keyword_scope.label.value_counts().to_dict(),
        "brand_scope": brand_scope.label.value_counts().to_dict(),
        "scam_by_brand": brand_scope[brand_scope.label == "scam"].brand.value_counts().to_dict(),
    }

    # detector: stage 1 + 2 together (keyword scope), and stage 2 alone (brand scope)
    Xk = frame(keyword_scope.fqdn.tolist())[FEATURES].reset_index(drop=True)
    yk = (keyword_scope.label == "scam").astype(int).values
    res["detector_keyword_scope"] = evaluate(
        Xk, yk, keyword_scope.registered_domain.values, keyword_scope.brand.fillna("none").values
    )
    Xb = frame(brand_scope.fqdn.tolist())[MODEL_FEATURES].reset_index(drop=True)
    yb = (brand_scope.label == "scam").astype(int).values
    res["detector_brand_scope"] = evaluate(Xb, yb, brand_scope.registered_domain.values, brand_scope.brand.values)

    oof = out_of_fold(Xk, yk, keyword_scope.registered_domain.values)
    _, thr = recall_at_precision(yk, oof, 0.95)
    model = make_model().fit(Xk, yk)
    res["stream"] = stream_triage(df, model, thr)
    res["lead_time"] = lead_times(df, conn, started)
    res["registrations"] = registration_summary(df, conn)

    # synthetic vs real
    scams = keyword_scope[keyword_scope.label == "scam"]
    res["experiment"] = {
        "pattern_shares": ex.pattern_shares(scams.fqdn.tolist(), a).to_dict(orient="index"),
        "endings": ex.tld_comparison(scams, a),
        "real_vs_A_auc": ex.distinguishability(scams.fqdn.tolist()[:1500], a[a.label == "scam"].domain.tolist()[:1500]),
    }
    res["experiment"].update(ex.learning_curves(keyword_scope, a))
    res["experiment"]["generator_B_examples"] = [defang(d) for d in res["experiment"]["generator_B_examples"]]
    (OUT / "results.json").write_text(json.dumps(res, indent=2, default=str))
    charts(res)
    return res


def charts(res: dict) -> None:
    ink, accent, grey, warm = "#1d2422", "#1f6f50", "#8a8f98", "#b9741a"
    # 1. pattern shares, real vs generator A
    ps = pd.DataFrame(res["experiment"]["pattern_shares"]).T.sort_values("real_share")
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    y = np.arange(len(ps))
    ax.barh(y + 0.2, ps.real_share * 100, 0.4, color=accent, label="real scam domains")
    ax.barh(y - 0.2, ps.generator_a_share * 100, 0.4, color=warm, label="generator A (assumptions)")
    ax.set_yticks(y, [i.replace("_", " ") for i in ps.index], fontsize=9)
    ax.set_xlabel("% of scam domains")
    ax.legend(frameon=False, fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "pattern_shares.png", dpi=150)
    # 2. learning curves
    curve = res["experiment"]["curve"]
    xs = [c["real_labels"] for c in curve]
    fig, ax = plt.subplots(figsize=(7.5, 4.2))
    for key, color, label in (
        ("real_only", ink, "real labels only"),
        ("real+A", warm, "real + generator A"),
        ("real+B", accent, "real + generator B"),
    ):
        ax.plot(xs, [c[key]["recall_at_95_precision"] * 100 for c in curve], marker="o", color=color, label=label)
    ax.set_xscale("log")
    ax.set_xlabel("real labelled domains used for training")
    ax.set_ylabel("recall at 95% precision (%)")
    ax.legend(frameon=False, fontsize=9)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "learning_curves.png", dpi=150)
    # 3. stream funnel
    s = res["stream"]
    steps = [
        ("keyword matches", s["keyword_domains"]),
        ("brand named as a word", s["after_stage1_rule"]),
        ("minus cloud infrastructure", s["after_infrastructure_filter"]),
        ("flagged by model", s["after_stage2_model"]),
    ]
    fig, ax = plt.subplots(figsize=(7.5, 2.8))
    ax.barh([n for n, _ in steps][::-1], [v for _, v in steps][::-1], color=[accent] + [grey] * (len(steps) - 1))
    for i, (_, v) in enumerate(steps[::-1]):
        ax.text(v, i, f"  {v}", va="center", fontsize=10)
    ax.set_xlabel(f"new domains over {s['days_covered']} days")
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()
    fig.savefig(OUT / "stream_funnel.png", dpi=150)
    plt.close("all")
