"""Late-pickup hotspots and one written recommendation per hotspot.

Input: the scored test month (artifacts/test_scored.parquet). Recommendations are rules over measured
numbers, so every sentence can be traced to a count in the same table.
"""
from __future__ import annotations

import pandas as pd

OPEN_TASK_CAP = 30          # above this, late rate in Shanghai rises from about 2% to 10%
CONCENTRATION_SHARE = 0.5   # "a few couriers" = top 3 couriers hold at least half of the region's late pickups


def region_table(scored: pd.DataFrame) -> pd.DataFrame:
    g = scored.groupby("region_id")
    out = pd.DataFrame({
        "tasks": g.size(),
        "late": g["late"].sum(),
        "late_rate": g["late"].mean(),
        "flagged": g["flagged"].sum(),
        "late_caught_by_alerts": scored[scored["late"] == 1].groupby("region_id")["flagged"].mean(),
    }).fillna({"late_caught_by_alerts": 0.0})
    return out.sort_values("late", ascending=False)


def courier_concentration(scored: pd.DataFrame) -> dict:
    """Share of all late pickups held by the least reliable 1% and 5% of couriers."""
    per = scored.groupby("courier_id")["late"].sum().sort_values(ascending=False)
    total = per.sum() or 1
    n = len(per)

    def share(frac: float) -> float:
        return float(per.iloc[: max(1, int(round(n * frac)))].sum() / total)

    return {"couriers": n, "top_1pct_share": share(0.01), "top_5pct_share": share(0.05)}


def recommend(region: pd.DataFrame) -> str:
    """One recommendation for one region's tasks, choosing the strongest measured pattern."""
    late_total = int(region["late"].sum())
    if late_total == 0:
        return "No late pickups this month; no action."
    by_courier = region.groupby("courier_id")["late"].agg(["sum", "size"]).sort_values("sum", ascending=False)
    top3 = by_courier.head(3)
    top3_share = top3["sum"].sum() / late_total
    if top3_share >= CONCENTRATION_SHARE:
        names = ", ".join(str(c) for c in top3.index)
        rates = ", ".join(f"{s / n:.0%}" for s, n in zip(top3["sum"], top3["size"]))
        return (f"Couriers {names} hold {top3_share:.0%} of this region's {late_total} late pickups "
                f"(late rates {rates}). Review their routes and shift part of their windows to other couriers.")

    heavy = region["courier_open_tasks"] > OPEN_TASK_CAP
    if heavy.sum() >= 50 and region.loc[heavy, "late"].mean() >= 2 * region.loc[~heavy, "late"].mean():
        return (f"{int(heavy.sum())} pickups were accepted while the courier already had over {OPEN_TASK_CAP} open "
                f"tasks; those ran late {region.loc[heavy, 'late'].mean():.0%} of the time vs "
                f"{region.loc[~heavy, 'late'].mean():.0%} otherwise. Cap open tasks per courier at {OPEN_TASK_CAP}.")

    hours = region.groupby(region["time_window_end"].dt.hour)["late"].agg(["sum", "mean", "size"])
    hours = hours[hours["size"] >= 100]
    if not hours.empty:
        worst = hours["sum"].idxmax()
        row = hours.loc[worst]
        return (f"Windows ending at {worst:02d}:00 produce {int(row['sum'])} late pickups ({row['mean']:.0%} late). "
                f"Add courier capacity before {worst:02d}:00 or offer customers a later window.")
    return f"{late_total} late pickups spread across couriers and hours; keep alerts on and review weekly."


def hotspots(scored: pd.DataFrame, top: int = 8) -> pd.DataFrame:
    regions = region_table(scored).head(top).copy()
    regions["recommendation"] = [recommend(scored[scored["region_id"] == r]) for r in regions.index]
    return regions
