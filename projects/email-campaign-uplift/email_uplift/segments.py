"""Step 3: break the lift down by customer segment.

The aggregation is SQL (sql/segment_aggregates.sql, run in DuckDB); the statistics are Python.
Two cautions are built in, because segment breakdowns are where A/B analyses usually go wrong:

1. Many segments means many tests. `p_holm` adjusts across every segment test, so a single
   lucky segment does not get reported as a finding.
2. "Significant in segment A but not in B" does not show the email works differently in A and B.
   `heterogeneity_tests` asks that question directly with an interaction model.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

from .data import TREATMENTS
from .stats import compare_means_from_moments, compare_proportions, holm

SQL_PATH = Path(__file__).resolve().parent.parent / "sql" / "segment_aggregates.sql"
DIMENSION_COLUMNS = {
    "Recency": "recency_band",
    "Past-year spend": "spend_band",
    "Channel": "channel",
    "Customer type": "customer_type",
    "Past purchase": "past_purchase",
    "Location": "zip_code",
}


def segment_aggregates(df: pd.DataFrame) -> pd.DataFrame:
    con = duckdb.connect()
    con.register("customers", df)
    out = con.execute(SQL_PATH.read_text()).df()
    con.close()
    return out


def segment_lifts(df: pd.DataFrame, alpha: float = 0.05) -> pd.DataFrame:
    """Lift of each email vs no email, within every segment level, for every outcome."""
    agg = segment_aggregates(df)
    rows = []
    for (dimension, level), g in agg.groupby(["dimension", "level"], sort=False):
        by_arm = g.set_index("arm")
        c = by_arm.loc["control"]
        for arm in TREATMENTS:
            t = by_arm.loc[arm]
            for metric, col in [("visit", "visits"), ("conversion", "conversions")]:
                res = compare_proportions(
                    int(t[col]), int(t["customers"]), int(c[col]), int(c["customers"]), alpha
                )
                rows.append({"dimension": dimension, "level": level, "treatment": arm,
                             "metric": metric, **res})
            res = compare_means_from_moments(
                t["spend_sum"], t["spend_sumsq"], int(t["customers"]),
                c["spend_sum"], c["spend_sumsq"], int(c["customers"]), alpha,
            )
            rows.append({"dimension": dimension, "level": level, "treatment": arm,
                         "metric": "spend", **res})
    out = pd.DataFrame(rows)
    out["p_holm"] = holm(out["p_value"])
    out["segment_customers"] = out["n_treatment"] + out["n_control"]
    return out


def heterogeneity_tests(df: pd.DataFrame) -> pd.DataFrame:
    """Does the lift differ across the levels of a dimension?

    Fits outcome ~ treated * C(segment) as a linear probability model (OLS on a 0/1 or dollar
    outcome) with heteroskedasticity-robust (HC1) standard errors, separately for each email
    vs control, and jointly tests the interaction terms. A small p-value means the lift is
    not the same in every level. The linear model is used on purpose: it measures lift in
    the same additive units (percentage points, dollars) as the rest of the report.
    """
    rows = []
    for arm in TREATMENTS:
        sub = df[df["arm"].isin([arm, "control"])].assign(
            treated=lambda d: (d["arm"] == arm).astype(int)
        )
        for dimension, col in DIMENSION_COLUMNS.items():
            for metric in ["visit", "conversion", "spend"]:
                fit = smf.ols(f"{metric} ~ treated * C({col})", data=sub).fit(cov_type="HC1")
                names = [n for n in fit.params.index if n.startswith("treated:")]
                restriction = np.zeros((len(names), len(fit.params)))
                for i, n in enumerate(names):
                    restriction[i, fit.params.index.get_loc(n)] = 1
                test = fit.wald_test(restriction, scalar=True)
                rows.append({"treatment": arm, "dimension": dimension, "metric": metric,
                             "statistic": float(test.statistic), "df": len(names),
                             "p_value": float(test.pvalue)})
    out = pd.DataFrame(rows)
    out["p_holm"] = holm(out["p_value"])
    return out
