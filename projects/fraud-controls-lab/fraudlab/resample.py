"""Fast bootstrap helpers shared by the evaluation and the simulation."""

from __future__ import annotations

import numpy as np
import pandas as pd


class Resampler:
    """Bootstrap by account using index arrays (fast: no DataFrame copies per run)."""

    def __init__(self, test: pd.DataFrame, seed: int) -> None:
        self.rng = np.random.default_rng(seed)
        self.month = test.month.to_numpy()
        codes, self.accounts = pd.factorize(test.account_id)
        order = np.argsort(codes, kind="stable")
        bounds = np.searchsorted(codes[order], np.arange(len(self.accounts) + 1))
        self.rows = [order[bounds[i]:bounds[i + 1]] for i in range(len(self.accounts))]

    def draw(self) -> np.ndarray:
        pick = self.rng.integers(0, len(self.rows), len(self.rows))
        return np.concatenate([self.rows[i] for i in pick])


def top_k_sum(idx: np.ndarray, month: np.ndarray, score: np.ndarray, value: np.ndarray, k: int) -> float:
    """Sum of `value` over the top-k rows by score within each month of the sample."""
    total = 0.0
    m = month[idx]
    for mo in np.unique(m):
        sel = idx[m == mo]
        if len(sel) > k:
            sel = sel[np.argpartition(-score[sel], k)[:k]]
        total += value[sel].sum()
    return total
