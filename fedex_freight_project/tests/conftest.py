import pathlib

import pandas as pd
import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.fixture(scope="session")
def root():
    return ROOT


@pytest.fixture(scope="session")
def kpis():
    return pd.read_csv(ROOT / "data/processed/fedex_freight_segment_quarterly_kpis.csv", parse_dates=["period_end"])


@pytest.fixture(scope="session")
def recast():
    return pd.read_csv(ROOT / "data/processed/fdxf_calendar_quarterly_kpis_recast.csv")
