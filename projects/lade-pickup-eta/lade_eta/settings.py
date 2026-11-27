"""All configuration in one place.

Values come from environment variables prefixed LADE_ (or a .env file), so the same code runs on a
laptop, in CI and in Docker without edits.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="LADE_", env_file=".env", extra="ignore")

    database_url: str = "postgresql://lade:lade@localhost:5432/lade"
    city: str = "sh"  # LaDe city code: sh, hz, cq, jl, yt
    data_dir: Path = Path("data")
    artifact_dir: Path = Path("artifacts")
    hf_base_url: str = "https://huggingface.co/datasets/Cainiao-AI/LaDe/resolve/main"

    # LaDe timestamps carry month and day but no year. The year is only used to do date arithmetic;
    # no feature depends on it (no day-of-week), because the true year is not published with the data.
    reference_year: int = 2022

    # Time-ordered split on the date the courier accepted the task.
    valid_start: str = "09-01"
    test_start: str = "10-01"

    # Share of tasks the operations team can act on (alerts per day / tasks per day).
    alert_budget: float = 0.05
    random_seed: int = 7
    log_level: str = "INFO"
    api_workers: int = 4  # processes; pandas work holds Python's GIL, so one process uses about one core


@lru_cache
def get_settings() -> Settings:
    return Settings()
