"""Interactive dashboard over the precomputed results.

    streamlit run app/streamlit_app.py

Reads reports/results/*.csv written by `python -m email_uplift.report`; it never re-runs the
models, so it starts instantly.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import streamlit as st

RESULTS = Path(__file__).resolve().parent.parent / "reports" / "results"
NAMES = {"mens": "Men's email", "womens": "Women's email", "control": "No email"}
COLORS = {"Men's email": "#2a78d6", "Women's email": "#eb6834"}



def _money(v: float) -> str:
    return f"-${abs(v):,.0f}" if v < 0 else f"${v:,.0f}"


st.set_page_config(page_title="Email campaign lift", layout="wide")

if not (RESULTS / "summary.json").exists():
    st.error("No results yet. Run `python -m email_uplift.report` first.")
    st.stop()

summary = json.loads((RESULTS / "summary.json").read_text())
lift = pd.read_csv(RESULTS / "lift.csv")
seg = pd.read_csv(RESULTS / "segment_lifts.csv")
curves = pd.read_csv(RESULTS / "uplift_curves.csv")
policies = pd.read_csv(RESULTS / "half_budget_policies.csv")
balance = pd.read_csv(RESULTS / "balance.csv")

st.title("Email campaign lift and targeting")
st.caption(f"Hillstrom MineThatData experiment · {summary['rows']:,} customers randomly split "
           "into men's email / women's email / no email · outcomes over the following two weeks")

tab_lift, tab_seg, tab_target, tab_check = st.tabs(
    ["Did it work?", "Segments", "Who to email", "Experiment check"])

with tab_lift:
    cols = st.columns(3)
    for col, metric, label in zip(cols, ["visit", "conversion", "spend"],
                                  ["Visit rate", "Purchase rate", "Spend per customer"]):
        r = summary["lift"][f"mens_vs_control_{metric}"]
        if metric == "spend":
            value, delta = f"${r['treatment_rate']:.2f}", f"+${r['abs_lift']:.2f} vs no email"
        else:
            value = f"{100 * r['treatment_rate']:.2f}%"
            delta = f"+{100 * r['abs_lift']:.2f} pp vs no email"
        col.metric(f"{label}, men's email", value, delta)
    st.markdown("**Every comparison** (95% CIs; Holm-adjusted p-values across the nine tests)")
    show = lift.assign(comparison=lift["treatment"].map(NAMES) + " vs " + lift["baseline"].map(NAMES))
    st.dataframe(
        show[["comparison", "metric", "treatment_rate", "control_rate", "abs_lift", "abs_ci_low",
              "abs_ci_high", "rel_lift", "p_holm"]].style.format({
            "treatment_rate": "{:.4f}", "control_rate": "{:.4f}", "abs_lift": "{:+.4f}",
            "abs_ci_low": "{:.4f}", "abs_ci_high": "{:.4f}", "rel_lift": "{:+.1%}", "p_holm": "{:.2g}"}),
        hide_index=True, use_container_width=True)

with tab_seg:
    c1, c2 = st.columns(2)
    dimension = c1.selectbox("Break down by", sorted(seg["dimension"].unique()))
    metric = c2.selectbox("Outcome", ["conversion", "visit", "spend"])
    part = seg[(seg["dimension"] == dimension) & (seg["metric"] == metric)].copy()
    scale = 1 if metric == "spend" else 100
    unit = "$ per customer" if metric == "spend" else "percentage points"
    part["email"] = part["treatment"].map(NAMES)
    part["lift"] = part["abs_lift"] * scale
    chart = part.pivot(index="level", columns="email", values="lift")
    st.markdown(f"**{metric.title()} lift vs no email by {dimension.lower()}** ({unit})")
    st.bar_chart(chart, color=[COLORS[c] for c in chart.columns], stack=False)
    part["95% CI"] = [f"{lo * scale:.2f} to {hi * scale:.2f}" for lo, hi in
                      zip(part["abs_ci_low"], part["abs_ci_high"])]
    st.dataframe(part[["level", "email", "segment_customers", "lift", "95% CI", "p_holm"]]
                 .rename(columns={"segment_customers": "customers", "p_holm": "p (Holm)"})
                 .style.format({"lift": "{:+.2f}", "p (Holm)": "{:.2g}"}),
                 hide_index=True, use_container_width=True)
    st.caption("A segment whose interval crosses 0 has no detectable effect; that is not proof of "
               "zero effect. See reports/findings.md for interaction tests of whether lifts differ.")

with tab_target:
    email = st.radio("Email", ["mens", "womens"], format_func=NAMES.get, horizontal=True)
    pct = st.slider("Share of customers to email (%)", 5, 100, 50, step=5)
    c = curves[(curves["treatment"] == email) & (curves["outcome"] == "spend")]
    row = c[(c["fraction"] * 100).round().astype(int) == pct].iloc[0]
    full = c["incremental"].iloc[-1]
    m1, m2, m3 = st.columns(3)
    m1.metric("Incremental spend, model-ranked", f"${row['incremental']:,.0f}")
    m2.metric("Incremental spend, random pick", f"${row['incremental_random']:,.0f}",
              f"{row['incremental'] - row['incremental_random']:+,.0f} for the model", delta_color="off")
    m3.metric("Share of full-campaign lift", f"{row['incremental'] / full:.0%}")
    plot = pd.DataFrame({"% emailed": c["fraction"] * 100,
                         "Ranked by uplift model": c["incremental"],
                         "Random selection": c["incremental_random"]}).set_index("% emailed")
    st.line_chart(plot, color=[COLORS[NAMES[email]], "#8f8e89"])
    st.caption("Dollars over two weeks for the 64,000-customer list. Scores are cross-fitted, so "
               "each customer was scored by a model that never saw them.")
    st.markdown("**Every way to spend a half-list budget**")
    st.dataframe(policies[["policy", "total_per_customer", "total_ci_low", "total_ci_high",
                           "total_vs_reference", "total_vs_reference_ci_low",
                           "total_vs_reference_ci_high"]].rename(columns={
        "total_per_customer": "expected spend", "total_ci_low": "CI low", "total_ci_high": "CI high",
        "total_vs_reference": "vs random half (men's)", "total_vs_reference_ci_low": "diff CI low",
        "total_vs_reference_ci_high": "diff CI high"}).style.format(
        {c: _money for c in ["expected spend", "CI low", "CI high", "vs random half (men's)",
                              "diff CI low", "diff CI high"]}),
        hide_index=True, use_container_width=True)

with tab_check:
    st.metric("Sample-ratio test p-value", f"{summary['srm_p_value']:.2f}",
              help="Tests whether the three group sizes match the intended equal split.")
    st.metric("Largest standardized difference", f"{summary['balance_max_abs_smd']:.3f}",
              help="Below 0.1 means the groups looked alike before the emails went out.")
    st.dataframe(balance, hide_index=True, use_container_width=True)
