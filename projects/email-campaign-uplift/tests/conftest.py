import numpy as np
import pandas as pd
import pytest

from email_uplift.data import prepare


def make_raw(n=6000, seed=0, mens_effect=0.02, womens_effect_by_womens=0.04, base=0.02):
    """Synthetic data in the raw Hillstrom schema with known treatment effects.

    Men's email lifts conversion by `mens_effect` for everyone; the women's email lifts it by
    `womens_effect_by_womens` only for customers who bought women's items before.
    """
    rng = np.random.default_rng(seed)
    tiers = ["1) $0 - $100", "2) $100 - $200", "3) $200 - $350", "4) $350 - $500",
             "5) $500 - $750", "6) $750 - $1,000", "7) $1,000 +"]
    tier = rng.integers(0, 7, n)
    mens = rng.integers(0, 2, n)
    womens = np.where(mens == 0, 1, rng.integers(0, 2, n))
    segment = rng.choice(["Mens E-Mail", "Womens E-Mail", "No E-Mail"], n)
    p = np.full(n, base)
    p += np.where(segment == "Mens E-Mail", mens_effect, 0)
    p += np.where((segment == "Womens E-Mail") & (womens == 1), womens_effect_by_womens, 0)
    conversion = (rng.random(n) < p).astype(int)
    visit = np.maximum(conversion, (rng.random(n) < 0.1).astype(int))
    return pd.DataFrame({
        "recency": rng.integers(1, 13, n),
        "history_segment": [tiers[t] for t in tier],
        "history": np.round(rng.uniform(30, 100, n) * (tier + 1), 2),
        "mens": mens, "womens": womens,
        "zip_code": rng.choice(["Surburban", "Urban", "Rural"], n),
        "newbie": rng.integers(0, 2, n),
        "channel": rng.choice(["Phone", "Web", "Multichannel"], n),
        "segment": segment, "visit": visit, "conversion": conversion,
        "spend": np.where(conversion == 1, np.round(rng.uniform(30, 300, n), 2), 0.0),
    })


@pytest.fixture
def raw():
    return make_raw()


@pytest.fixture
def df(raw):
    return prepare(raw)
