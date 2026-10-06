"""Download, validate and prepare the Hillstrom MineThatData email experiment.

The original file was published by Kevin Hillstrom in 2008 for the "MineThatData E-Mail
Analytics and Data Mining Challenge". The minethatdata.com link is often unreachable, so we
download the identical copy that the scikit-uplift library uses and verify it by checksum.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import urllib.request
from pathlib import Path

import pandas as pd

DATA_URL = "https://hillstorm1.s3.us-east-2.amazonaws.com/hillstorm_no_indices.csv.gz"
ORIGINAL_URL = (
    "http://www.minethatdata.com/"
    "Kevin_Hillstrom_MineThatData_E-MailAnalytics_DataMiningChallenge_2008.03.20.csv"
)
# SHA-256 of the uncompressed CSV, so a changed or truncated mirror fails loudly.
DATA_SHA256 = "00a6a868e05a9ffe7382da51629f6d6dce88c5acfc945e79d314ebc78fd3a2c0"
DEFAULT_PATH = Path(__file__).resolve().parent.parent / "data" / "hillstrom.csv"

EXPECTED_ROWS = 64_000
EXPECTED_COLUMNS = [
    "recency", "history_segment", "history", "mens", "womens", "zip_code",
    "newbie", "channel", "segment", "visit", "conversion", "spend",
]

# Raw `segment` label -> short arm name used everywhere else.
ARMS = {"Mens E-Mail": "mens", "Womens E-Mail": "womens", "No E-Mail": "control"}
TREATMENTS = ["mens", "womens"]
CONTROL = "control"
OUTCOMES = ["visit", "conversion", "spend"]


def download(dest: Path = DEFAULT_PATH, url: str = DATA_URL) -> Path:
    """Fetch the gzipped CSV, decompress it to `dest` and verify its checksum."""
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with urllib.request.urlopen(url, timeout=120) as resp:
        raw = gzip.decompress(resp.read())
    digest = hashlib.sha256(raw).hexdigest()
    if digest != DATA_SHA256:
        raise ValueError(f"checksum mismatch for {url}: got {digest}, expected {DATA_SHA256}")
    dest.write_bytes(raw)
    return dest


def validate_raw(df: pd.DataFrame, expected_rows: int | None = EXPECTED_ROWS) -> None:
    """Fail fast if the file is not the dataset we think it is."""
    if list(df.columns) != EXPECTED_COLUMNS:
        raise ValueError(f"unexpected columns: {list(df.columns)}")
    if expected_rows is not None and len(df) != expected_rows:
        raise ValueError(f"expected {expected_rows} rows, got {len(df)}")
    if df.isna().any().any():
        raise ValueError("dataset contains missing values")
    unknown = set(df["segment"]) - set(ARMS)
    if unknown:
        raise ValueError(f"unknown campaign groups: {sorted(unknown)}")
    for col in ["mens", "womens", "newbie", "visit", "conversion"]:
        if not set(df[col].unique()) <= {0, 1}:
            raise ValueError(f"{col} must be 0/1")
    if (df["spend"] < 0).any():
        raise ValueError("negative spend")
    if ((df["spend"] > 0) & (df["conversion"] == 0)).any():
        raise ValueError("spend recorded without a conversion")
    if not df["recency"].between(1, 12).all():
        raise ValueError("recency outside 1-12 months")


def prepare(df: pd.DataFrame) -> pd.DataFrame:
    """Add the analysis columns: arm, readable segment labels for the breakdowns."""
    out = df.copy()
    # The raw file spells "Suburban" as "Surburban"; fix it once here.
    out["zip_code"] = out["zip_code"].replace({"Surburban": "Suburban"})
    out["arm"] = out["segment"].map(ARMS)
    out["recency_band"] = pd.cut(
        out["recency"], bins=[0, 3, 6, 9, 12],
        labels=["1-3 months", "4-6 months", "7-9 months", "10-12 months"],
    ).astype(str)
    # history_segment looks like "2) $100 - $200"; drop the sort prefix for display,
    # and collapse the thin top tiers so every segment has thousands of customers.
    tier = out["history_segment"].str.slice(0, 1).astype(int)
    out["spend_band"] = pd.cut(
        tier, bins=[0, 1, 2, 3, 4, 7],
        labels=["$0-100", "$100-200", "$200-350", "$350-500", "$500+"],
    ).astype(str)
    out["customer_type"] = out["newbie"].map({1: "New (past 12 months)", 0: "Returning"})
    out["past_purchase"] = (
        out["mens"].astype(str) + out["womens"].astype(str)
    ).map({"10": "Men's only", "01": "Women's only", "11": "Both"})
    return out


def load(path: Path = DEFAULT_PATH, expected_rows: int | None = EXPECTED_ROWS) -> pd.DataFrame:
    """Read, validate and prepare the dataset."""
    df = pd.read_csv(path)
    validate_raw(df, expected_rows=expected_rows)
    return prepare(df)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    dl = sub.add_parser("download", help="download and verify the dataset")
    dl.add_argument("--dest", type=Path, default=DEFAULT_PATH)
    args = parser.parse_args()
    if args.cmd == "download":
        path = download(args.dest)
        df = load(path)
        print(f"saved {path} ({len(df):,} rows, {df.shape[1]} columns after preparation)")


if __name__ == "__main__":
    main()
