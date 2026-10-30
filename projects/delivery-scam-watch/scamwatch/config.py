"""Settings and brand configuration.

Secrets come only from the environment: a local, untracked `.env` file on your computer and
GitHub Secrets in the scheduled jobs. Nothing secret is ever written in code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BRANDS_FILE = PROJECT_ROOT / "config" / "brands.yaml"
MIGRATIONS_DIR = PROJECT_ROOT / "db" / "migrations"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=PROJECT_ROOT / ".env", extra="ignore")

    database_url: str = ""  # Neon main branch (production data)
    test_database_url: str = ""  # Neon test branch, or a local Postgres, for tests only
    user_agent: str = "delivery-scam-watch/0.1 (+https://github.com/kstc707/delivery-scam-watch)"


@dataclass(frozen=True)
class Brand:
    name: str
    keywords: tuple[str, ...]
    allowlist: tuple[str, ...]


def load_brands(path: Path = BRANDS_FILE) -> list[Brand]:
    data = yaml.safe_load(path.read_text())
    brands = []
    for b in data["brands"]:
        brands.append(
            Brand(
                name=b["name"],
                keywords=tuple(k.lower() for k in b["keywords"]),
                allowlist=tuple(d.lower() for d in b["allowlist"]),
            )
        )
    return brands
