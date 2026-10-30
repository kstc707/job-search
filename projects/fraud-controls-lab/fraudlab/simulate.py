"""Monte Carlo capacity planning: how many cases a month should analysts review?

For each capacity k, resample the test accounts 2,000 times (bootstrap) and scale fraud
dollars by a random factor (fraud volume next quarter is uncertain), then compute the
dollars the queue would stop minus the cost of the reviews. The answer is a range, not a
single number, which is what a budget conversation needs.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .detect import TEST_MONTHS
from .resample import Resampler, top_k_sum

MINUTES_PER_REVIEW = 45
ANALYST_COST_PER_HOUR = 45.0


def capacity_curve(scored: pd.DataFrame, score: str, capacities=(10, 25, 50, 75, 100, 150, 200, 300),
                   n_runs: int = 2000, seed: int = 7) -> pd.DataFrame:
    test = scored[scored.month.isin(TEST_MONTHS)].reset_index(drop=True)
    rs = Resampler(test, seed)
    s = test[score].to_numpy()
    caught_value = (test.dollars_at_risk * test.fraud).to_numpy()
    review_cost = MINUTES_PER_REVIEW / 60 * ANALYST_COST_PER_HOUR
    n_months = len(TEST_MONTHS)
    rows = []
    for run in range(n_runs):
        idx = rs.draw()
        shock = rs.rng.lognormal(0, 0.3)                    # fraud dollars next period: +/- ~30%
        for k in capacities:
            stopped = top_k_sum(idx, rs.month, s, caught_value, k) * shock / n_months
            cost = k * review_cost
            rows.append((run, k, stopped, cost, stopped - cost))
    sims = pd.DataFrame(rows, columns=["run", "capacity", "dollars_stopped", "review_cost", "net"])
    return (sims.groupby("capacity")
            .agg(stopped_mean=("dollars_stopped", "mean"), net_mean=("net", "mean"),
                 net_p05=("net", lambda x: np.percentile(x, 5)), net_p95=("net", lambda x: np.percentile(x, 95)),
                 review_cost=("review_cost", "first"))
            .round(0).reset_index())
