"""Operations page: where late pickups happen, what the alerts caught, and what to change.

    streamlit run dashboard/app.py
"""
import json
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lade_eta.hotspots import courier_concentration, hotspots  # noqa: E402
from lade_eta.settings import get_settings  # noqa: E402

art = get_settings().artifact_dir
st.set_page_config(page_title="Pickup late-risk", layout="wide")
st.title("Pickup late-risk: test month")

scored = pd.read_parquet(art / "test_scored.parquet")
metrics = json.loads((art / "metrics.json").read_text())
alerts = metrics["late_risk"]["fixed_threshold_from_valid"]
eta = metrics["eta"]

c1, c2, c3, c4 = st.columns(4)
c1.metric("Pickups", f"{len(scored):,}")
c2.metric("Late (after window end)", f"{scored['late'].mean():.1%}")
c3.metric("Late pickups warned in advance", f"{alerts['recall']:.0%}", help="Alerts on about 5% of tasks")
c4.metric("ETA error (MAE)", f"{eta['lightgbm']['mae_min']:.0f} min",
          delta=f"{eta['lightgbm']['mae_min'] - eta['baseline_window_midpoint']['mae_min']:.0f} vs window-midpoint rule",
          delta_color="inverse")

conc = courier_concentration(scored)
st.info(f"The least reliable 5% of couriers ({round(conc['couriers'] * 0.05)} of {conc['couriers']:,}) hold "
        f"{conc['top_5pct_share']:.0%} of all late pickups; the top 1% hold {conc['top_1pct_share']:.0%}.")

st.subheader("Hotspots by region, with one recommendation each")
table = hotspots(scored).reset_index().rename(columns={"region_id": "region"})
shown = table.drop(columns="recommendation").assign(
    late_rate=lambda d: (100 * d["late_rate"]).round(1),
    late_caught_by_alerts=lambda d: (100 * d["late_caught_by_alerts"]).round(0),
)
st.dataframe(
    shown,
    column_config={
        "late_rate": st.column_config.NumberColumn("late rate", format="%.1f%%"),
        "late_caught_by_alerts": st.column_config.NumberColumn("late caught by alerts", format="%.0f%%"),
    },
    hide_index=True, use_container_width=True,
)
for row in table.itertuples():
    st.markdown(f"**Region {row.region}** ({row.late:,} late of {row.tasks:,}): {row.recommendation}")

st.subheader("Late rate by courier workload at accept time")
buckets = pd.cut(scored["courier_open_tasks"], [-1, 5, 10, 20, 30, 50, 10_000],
                 labels=["0-5", "6-10", "11-20", "21-30", "31-50", "51+"])
by_load = scored.groupby(buckets, observed=True)["late"].agg(late_rate="mean", pickups="size")
st.bar_chart(by_load["late_rate"], x_label="open tasks", y_label="late rate")
st.caption("Pickups per bucket: " + ", ".join(f"{k}: {v:,}" for k, v in by_load["pickups"].items()))

st.subheader("Open flagged tasks right now (replay)")
day = st.date_input("Day", pd.Timestamp(scored["accept_time"].min()).date())
hour = st.slider("Hour", 8, 20, 10)
t = pd.Timestamp(day) + pd.Timedelta(hours=hour)
open_flagged = scored[(scored["accept_time"] <= t) & (scored["pickup_time"] > t)
                      & (scored["time_window_end"] > t) & scored["flagged"]]
st.write(f"{len(open_flagged)} flagged tasks open at {t:%m-%d %H:%M}")
st.dataframe(open_flagged.sort_values(["time_window_end", "risk"], ascending=[True, False])
             [["order_id", "courier_id", "region_id", "time_window_end", "risk", "eta_minutes", "late"]]
             .round({"risk": 3, "eta_minutes": 0}).head(200),
             hide_index=True, use_container_width=True)
