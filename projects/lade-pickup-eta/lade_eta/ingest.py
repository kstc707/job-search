"""Download LaDe pickup data, clean it, and load it into PostgreSQL.

Flow: Hugging Face CSV -> pandas (parse + quality checks) -> PostgreSQL `pickups` table (COPY).
`read_pickups` reads it back for feature building, from PostgreSQL or straight from the CSV.
"""
from __future__ import annotations

import io
import logging
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from .logs import log
from .settings import Settings

logger = logging.getLogger(__name__)

TIME_COLS = ["accept_time", "time_window_start", "time_window_end", "pickup_time"]
DB_COLS = [
    "order_id", "city", "region_id", "aoi_id", "aoi_type", "courier_id", "lng", "lat",
    *TIME_COLS, "accept_gps_lng", "accept_gps_lat", "ds",
]


def csv_path(settings: Settings) -> Path:
    return settings.data_dir / f"pickup_{settings.city}.csv"


def download(settings: Settings) -> Path:
    """Fetch one city's pickup CSV from Hugging Face (skips if already present)."""
    path = csv_path(settings)
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    url = f"{settings.hf_base_url}/pickup/pickup_{settings.city}.csv"
    log(logger, "downloading", url=url)
    tmp = path.with_suffix(".part")
    urllib.request.urlretrieve(url, tmp)
    tmp.rename(path)
    return path


def parse_times(df: pd.DataFrame, year: int) -> pd.DataFrame:
    """LaDe stores 'MM-DD HH:MM:SS' with no year; attach the reference year so we can subtract times."""
    out = df.copy()
    for col in TIME_COLS:
        out[col] = pd.to_datetime(f"{year}-" + out[col].astype(str), format="%Y-%m-%d %H:%M:%S")
    return out


@dataclass
class QualityReport:
    rows_in: int
    dropped: dict[str, int] = field(default_factory=dict)

    @property
    def rows_out(self) -> int:
        return self.rows_in - sum(self.dropped.values())


def clean(df: pd.DataFrame) -> tuple[pd.DataFrame, QualityReport]:
    """Drop rows that cannot be scored honestly. Every rule is counted in the report.

    - duplicate order ids (keep first)
    - window end before window start
    - pickup before the courier accepted the task (impossible event order)
    - task accepted after its window had already closed: no warning could reach the customer in time,
      so these are not a prediction problem; they are reported separately in the README.
    """
    report = QualityReport(rows_in=len(df))
    rules = {
        "duplicate_order_id": df["order_id"].duplicated(),
        "window_end_before_start": df["time_window_end"] < df["time_window_start"],
        "pickup_before_accept": df["pickup_time"] < df["accept_time"],
        "accepted_after_window_end": df["accept_time"] >= df["time_window_end"],
    }
    keep = pd.Series(True, index=df.index)
    for name, mask in rules.items():
        newly = mask & keep
        report.dropped[name] = int(newly.sum())
        keep &= ~mask
    return df[keep].reset_index(drop=True), report


def load_csv(settings: Settings) -> pd.DataFrame:
    raw = pd.read_csv(csv_path(settings))
    return parse_times(raw, settings.reference_year)


def write_postgres(df: pd.DataFrame, database_url: str, replace: bool = True) -> int:
    """Create the schema and bulk-load rows with COPY (much faster than INSERTs for a million rows)."""
    import psycopg

    schema = (Path(__file__).parent / "schema.sql").read_text()
    with psycopg.connect(database_url) as conn:
        with conn.cursor() as cur:
            cur.execute(schema)
            if replace:
                cur.execute("TRUNCATE pickups")
            buf = io.StringIO()
            df[DB_COLS].to_csv(buf, index=False, header=False, date_format="%Y-%m-%d %H:%M:%S")
            buf.seek(0)
            with cur.copy(f"COPY pickups ({', '.join(DB_COLS)}) FROM STDIN WITH (FORMAT csv)") as copy:
                while chunk := buf.read(1 << 20):
                    copy.write(chunk)
            cur.execute("ANALYZE pickups")
        conn.commit()
    return len(df)


def read_postgres(database_url: str, where: str = "", params: tuple = ()) -> pd.DataFrame:
    import psycopg

    sql = f"SELECT {', '.join(DB_COLS)} FROM pickups {where}"
    with psycopg.connect(database_url) as conn, conn.cursor() as cur:
        cur.execute(sql, params)
        rows = cur.fetchall()
    df = pd.DataFrame(rows, columns=DB_COLS)
    for col in TIME_COLS:
        df[col] = pd.to_datetime(df[col])
    return df


def run(settings: Settings, to_postgres: bool = True) -> QualityReport:
    download(settings)
    df, report = clean(load_csv(settings))
    log(logger, "cleaned", rows_in=report.rows_in, rows_out=report.rows_out, **report.dropped)
    if to_postgres:
        n = write_postgres(df, settings.database_url)
        log(logger, "loaded_postgres", rows=n)
    return report
