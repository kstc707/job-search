"""Run the whole analysis and write every result the README, dashboard and slides use.

    python -m email_uplift.report            # full run (about a minute)
    python -m email_uplift.report --quick    # fewer bootstrap draws, for a fast check

Outputs (all regenerated on each run, so numbers never drift from the code):
    reports/results/*.csv      tables
    reports/results/summary.json   headline numbers
    reports/figures/*.png      charts
    reports/findings.md        generated findings with every table
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from . import charts
from .data import DEFAULT_PATH, TREATMENTS, load
from .experiment import balance_table, lift_table, sample_ratio_check
from .segments import heterogeneity_tests, segment_lifts
from .stats import mde_proportion
from .uplift import (
    MODEL_SPECS, auuc, cross_fit_uplift, evaluate_policies, heuristic_scores,
    targeted_assignment, targeting_summary, uplift_curve,
)

ROOT = Path(__file__).resolve().parent.parent
PRIMARY_MODEL = MODEL_SPECS[0].name  # chosen before evaluation: it answers the brief literally
BUDGET_FRACTION = 0.5


def run(data_path: Path, out_dir: Path, n_boot: int = 1000) -> dict:
    results, figures = out_dir / "results", out_dir / "figures"
    results.mkdir(parents=True, exist_ok=True)
    figures.mkdir(parents=True, exist_ok=True)
    df = load(data_path)
    population = len(df)

    # 1. Randomization check
    srm = sample_ratio_check(df)
    balance = balance_table(df)
    balance.to_csv(results / "balance.csv", index=False)

    # 2. Overall lift
    lift = lift_table(df)
    lift.to_csv(results / "lift.csv", index=False)
    charts.lift_overview(lift, figures / "lift_overview.png")

    # 3. Segments
    seg = segment_lifts(df)
    seg.to_csv(results / "segment_lifts.csv", index=False)
    het = heterogeneity_tests(df)
    het.to_csv(results / "heterogeneity_tests.csv", index=False)
    charts.segment_forest(seg, "conversion", figures / "segment_conversion_lift.png")
    charts.segment_forest(seg, "visit", figures / "segment_visit_lift.png")

    # 4. Uplift models (cross-fitted scores), plus rule-of-thumb baselines
    all_scores = {spec.name: cross_fit_uplift(spec, df) for spec in MODEL_SPECS}
    for name, s in heuristic_scores(df).items():
        all_scores[name] = pd.DataFrame({arm: s for arm in TREATMENTS})
    scores = all_scores[PRIMARY_MODEL]
    scores.add_prefix("uplift_").to_csv(results / "customer_scores.csv", index_label="customer")

    comparison, curves = [], []
    for name, s in all_scores.items():
        for arm in TREATMENTS:
            ts = targeting_summary(df, s[arm], arm, BUDGET_FRACTION, "spend", n_boot=n_boot)
            conv = targeting_summary(df, s[arm], arm, BUDGET_FRACTION, "conversion", n_boot=n_boot)
            curve = uplift_curve(df, s[arm], arm, "spend")
            comparison.append({
                "ranking": name, "treatment": arm, "auuc_spend": auuc(curve),
                "auuc_conversions": auuc(uplift_curve(df, s[arm], arm, "conversion")),
                **{f"spend_{k}": v for k, v in ts.items() if k not in ("treatment", "outcome")},
                "conversions_extra_vs_random": conv["extra_vs_random"],
                "conversions_extra_ci_low": conv["extra_vs_random_ci_low"],
                "conversions_extra_ci_high": conv["extra_vs_random_ci_high"],
                "conversions_share_of_full_campaign": conv["share_of_full_campaign"],
            })
            if name == PRIMARY_MODEL:
                curves.append(curve.assign(treatment=arm, outcome="spend"))
                curves.append(uplift_curve(df, s[arm], arm, "conversion").assign(
                    treatment=arm, outcome="conversion"))
    comparison = pd.DataFrame(comparison)
    comparison.to_csv(results / "model_comparison.csv", index=False)
    curves = pd.concat(curves, ignore_index=True)
    curves.to_csv(results / "uplift_curves.csv", index=False)
    charts.uplift_curves(curves[curves["outcome"] == "spend"], figures / "uplift_curves.png",
                         BUDGET_FRACTION)

    # 5. Half-budget recommendation: every candidate plan on the same scale
    f = BUDGET_FRACTION
    policy_defs = {
        "No email": ({"control": 1.0}, "baseline"),
        "Random half, women's email": ({"womens": f, "control": 1 - f}, "baseline"),
        "Random half, men's email": ({"mens": f, "control": 1 - f}, "baseline"),
        "Model half, women's email": (targeted_assignment(scores, f, "womens"), "womens"),
        "Model half, men's email": (targeted_assignment(scores, f, "mens"), "mens"),
        "Model half, best email per customer": (targeted_assignment(scores, f), "mixed"),
        "Top past spenders half, men's email": (
            targeted_assignment(all_scores["Rule: biggest past spenders first"], f, "mens"), "mens"),
        "Everyone, men's email (full budget)": ({"mens": 1.0}, "mens"),
    }
    policies = evaluate_policies(
        df, {k: v[0] for k, v in policy_defs.items()}, "spend",
        reference="Random half, men's email", n_boot=n_boot,
    )
    policies["color_key"] = [v[1] for v in policy_defs.values()]
    for col in ["per_customer", "ci_low", "ci_high", "vs_reference", "vs_reference_ci_low",
                "vs_reference_ci_high"]:
        policies[f"total_{col}"] = policies[col] * population
    policies.to_csv(results / "half_budget_policies.csv", index=False)
    charts.policy_bars(policies, figures / "half_budget_policies.png", population)

    summary = build_summary(df, srm, balance, lift, seg, het, comparison, policies)
    (results / "summary.json").write_text(json.dumps(summary, indent=2))
    (out_dir / "findings.md").write_text(findings_markdown(summary, balance, lift, seg, het,
                                                           comparison, policies))
    return summary


def _row(table, **filters):
    mask = np.ones(len(table), bool)
    for k, v in filters.items():
        mask &= (table[k] == v).to_numpy()
    rows = table[mask]
    assert len(rows) == 1, filters
    return rows.iloc[0]


def build_summary(df, srm, balance, lift, seg, het, comparison, policies) -> dict:
    population = len(df)
    s = {
        "rows": population, "columns_raw": 12,
        "group_sizes": srm["counts"], "srm_p_value": srm["p_value"],
        "balance_max_abs_smd": float(balance["max_abs_smd"].max()),
        "balance_min_p_value": float(balance["p_value"].min()),
        "lift": {}, "segments": {}, "targeting": {}, "policies": {},
    }
    for t, c in [("mens", "control"), ("womens", "control"), ("mens", "womens")]:
        for m in ["visit", "conversion", "spend"]:
            r = _row(lift, treatment=t, baseline=c, metric=m)
            s["lift"][f"{t}_vs_{c}_{m}"] = {
                k: float(r[k]) for k in ["treatment_rate", "control_rate", "abs_lift", "abs_ci_low",
                                         "abs_ci_high", "rel_lift", "rel_ci_low", "rel_ci_high",
                                         "p_value", "p_holm"]}
    ctrl_conv = s["lift"]["mens_vs_control_conversion"]["control_rate"]
    s["conversion_mde_pp"] = 100 * mde_proportion(ctrl_conv, population // 3, population // 3)

    conv = seg[seg["metric"] == "conversion"]
    s["segments"]["significant_after_holm"] = {
        arm: conv[(conv["treatment"] == arm) & (conv["p_holm"] < 0.05)][["dimension", "level"]]
        .apply(lambda r: f"{r.dimension}: {r.level}", axis=1).tolist() for arm in TREATMENTS}
    s["segments"]["no_detectable_effect"] = {
        arm: conv[(conv["treatment"] == arm) & (conv["abs_ci_low"] <= 0)][["dimension", "level"]]
        .apply(lambda r: f"{r.dimension}: {r.level}", axis=1).tolist() for arm in TREATMENTS}
    s["segments"]["heterogeneity_significant_after_holm"] = het[het["p_holm"] < 0.05][
        ["treatment", "dimension", "metric", "p_value", "p_holm"]].to_dict("records")
    s["segments"]["heterogeneity_raw_p_below_005"] = het[het["p_value"] < 0.05][
        ["treatment", "dimension", "metric", "p_value", "p_holm"]].to_dict("records")

    for arm in TREATMENTS:
        r = _row(comparison, ranking=PRIMARY_MODEL, treatment=arm)
        s["targeting"][arm] = {k: float(r[k]) for k in r.index if k not in ("ranking", "treatment")}
    s["targeting"]["primary_model"] = PRIMARY_MODEL
    s["targeting"]["budget_fraction"] = BUDGET_FRACTION
    s["policies"] = policies.drop(columns=["color_key"]).set_index("policy").to_dict("index")
    return s


def _pct(x, d=1):
    return f"{100 * x:.{d}f}%"


def _md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    lines = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        lines.append("| " + " | ".join(str(r[c]) for c in cols) + " |")
    return "\n".join(lines)


def _fmt_lift(metric, r):
    if metric == "spend":
        return (f"${r.treatment_rate:.3f} vs ${r.control_rate:.3f}", f"+${r.abs_lift:.3f}",
                f"${r.abs_ci_low:.3f} to ${r.abs_ci_high:.3f}")
    return (f"{_pct(r.treatment_rate, 2)} vs {_pct(r.control_rate, 2)}",
            f"{100 * r.abs_lift:+.2f} pp", f"{100 * r.abs_ci_low:.2f} to {100 * r.abs_ci_high:.2f} pp")


def findings_markdown(summary, balance, lift, seg, het, comparison, policies) -> str:
    names = {"mens": "Men's email", "womens": "Women's email", "control": "No email"}
    out = ["# Findings (generated by `python -m email_uplift.report`)", "",
           "Every number below is produced by the code in this repo; re-running the report "
           "regenerates this file.", ""]

    out += ["## 1. Was the experiment fair?", "",
            f"- Group sizes: {summary['group_sizes']} — sample-ratio test p = "
            f"{summary['srm_p_value']:.2f} (no sign the split was broken).",
            f"- Largest standardized difference between an email group and no-email on any "
            f"pre-campaign attribute: {summary['balance_max_abs_smd']:.3f} (balanced if < 0.1). "
            f"Smallest balance-test p-value: {summary['balance_min_p_value']:.2f}.", ""]
    b = balance.copy()
    for c in ["mens", "womens", "control", "max_abs_smd", "p_value"]:
        b[c] = b[c].map(lambda v: f"{v:.3f}")
    out += [_md_table(b), ""]

    out += ["## 2. Did the emails work?", "",
            "Holm-adjusted p-values cover all nine comparisons below.", ""]
    rows = []
    for _, r in lift.iterrows():
        rates, d, ci = _fmt_lift(r.metric, r)
        rows.append({"comparison": f"{names[r.treatment]} vs {names[r.baseline]}",
                     "metric": r.metric, "rates": rates, "lift": d, "95% CI": ci,
                     "relative lift": _pct(r.rel_lift), "p (Holm)": f"{r.p_holm:.2g}"})
    out += [_md_table(pd.DataFrame(rows)), "",
            f"Minimum detectable conversion lift at 80% power for one email vs no email: "
            f"{summary['conversion_mde_pp']:.2f} pp.", ""]

    out += ["## 3. Which segments responded?", "",
            "Conversion-rate lift vs no email by segment. `p (Holm)` adjusts across all "
            f"{len(seg)} segment tests.", ""]
    c = seg[seg["metric"] == "conversion"].copy()
    c = c.assign(**{
        "email": c["treatment"].map(names),
        "customers": c["segment_customers"],
        "no-email rate": c["control_rate"].map(lambda v: _pct(v, 2)),
        "lift (pp)": (100 * c["abs_lift"]).map(lambda v: f"{v:+.2f}"),
        "95% CI (pp)": [f"{100 * a:.2f} to {100 * b_:.2f}" for a, b_ in zip(c.abs_ci_low, c.abs_ci_high)],
        "p (Holm)": c["p_holm"].map(lambda v: f"{v:.2g}"),
    })[["dimension", "level", "email", "customers", "no-email rate", "lift (pp)", "95% CI (pp)", "p (Holm)"]]
    out += [_md_table(c), ""]
    out += ["### Does the lift actually differ between segments?", "",
            "Interaction test (outcome ~ email × segment, robust SEs). A small p means the "
            "lift is not the same across the segment's levels.", ""]
    h = het.assign(email=het["treatment"].map(names),
                   p=het["p_value"].map(lambda v: f"{v:.3g}"),
                   **{"p (Holm)": het["p_holm"].map(lambda v: f"{v:.3g}")})
    out += [_md_table(h[["email", "dimension", "metric", "p", "p (Holm)"]]), ""]

    out += ["## 4–5. Targeting: who to email with half the budget", "",
            f"Primary model: **{PRIMARY_MODEL}** (pre-specified). Scores are 5-fold cross-fitted. "
            "Each ranking is evaluated on how much incremental spend the top 50% delivers versus "
            "a random 50%, for the same email. Dollars are for the 64,000-customer list over the "
            "two-week window; intervals are bootstrap 95%.", ""]
    cm = comparison.assign(**{
        "email": comparison["treatment"].map(names),
        "top-50% incremental spend": comparison["spend_incremental_model"].map(lambda v: f"${v:,.0f}"),
        "random-50%": comparison["spend_incremental_random"].map(lambda v: f"${v:,.0f}"),
        "extra vs random (95% CI)": [f"${a:,.0f} ({lo:,.0f} to {hi:,.0f})" for a, lo, hi in zip(
            comparison.spend_extra_vs_random, comparison.spend_extra_vs_random_ci_low,
            comparison.spend_extra_vs_random_ci_high)],
        "share of full-campaign spend lift": comparison["spend_share_of_full_campaign"].map(_pct),
        "share of full-campaign extra purchases": comparison["conversions_share_of_full_campaign"].map(_pct),
    })[["ranking", "email", "top-50% incremental spend", "random-50%", "extra vs random (95% CI)",
        "share of full-campaign spend lift", "share of full-campaign extra purchases"]]
    out += [_md_table(cm), ""]
    out += ["### Every way to spend a half-list budget", "",
            "Expected two-week spend for the whole 64,000-customer list under each plan, "
            "estimated from the experiment (random plans: exact group averages; ranked plans: "
            "inverse propensity weighting).", ""]
    pt = policies.assign(**{
        "total spend": policies["total_per_customer"].map(lambda v: f"${v:,.0f}"),
        "95% CI": [f"${a:,.0f} to ${b_:,.0f}" for a, b_ in zip(policies.total_ci_low, policies.total_ci_high)],
        "vs random half, men's (95% CI)": [f"{a:+,.0f} ({lo:,.0f} to {hi:,.0f})" for a, lo, hi in zip(
            policies.total_vs_reference, policies.total_vs_reference_ci_low, policies.total_vs_reference_ci_high)],
    })[["policy", "total spend", "95% CI", "vs random half, men's (95% CI)"]]
    out += [_md_table(pt), ""]
    return "\n".join(out)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the full email campaign analysis.")
    parser.add_argument("--data", type=Path, default=DEFAULT_PATH)
    parser.add_argument("--out", type=Path, default=ROOT / "reports")
    parser.add_argument("--quick", action="store_true", help="200 bootstrap draws instead of 1000")
    args = parser.parse_args()
    summary = run(args.data, args.out, n_boot=200 if args.quick else 1000)
    print(json.dumps({k: summary[k] for k in ["rows", "group_sizes", "srm_p_value"]}, indent=2))
    print(f"wrote results to {args.out}")


if __name__ == "__main__":
    main()
