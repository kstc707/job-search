"""Safety checks that need no database: defanging and no secrets in the repository."""

from __future__ import annotations

import re
import subprocess

import pytest

from scamwatch.config import PROJECT_ROOT, load_brands
from scamwatch.defang import defang


@pytest.mark.parametrize(
    "raw,safe",
    [
        ("https://fedex-help.top/pay?id=1", "hxxps://fedex-help[.]top/pay?id=1"),
        ("http://usps-fee.xyz", "hxxp://usps-fee[.]xyz"),
        ("http://192.168.10.5:8080/login", "hxxp://192[.]168[.]10[.]5:8080/login"),
        ("https://ups.com@evil.example/track", "hxxps://ups.com@evil[.]example/track"),
        ("http://[2001:db8::1]/x", "hxxp://[2001:db8::1]/x"),
        ("dhl-delivery.top", "dhl-delivery[.]top"),
    ],
)
def test_defang(raw, safe):
    assert defang(raw) == safe


def test_defanged_url_has_no_live_link():
    out = defang("https://usps.redelivery-fee.top/a.b.c")
    assert "http" not in out.replace("hxxp", "") and "redelivery-fee.top" not in out


def test_brands_config_is_complete():
    names = [b.name for b in load_brands()]
    assert names == ["FedEx", "UPS", "USPS", "DHL"]
    for b in load_brands():
        assert b.keywords and b.allowlist


SECRET_PATTERNS = [
    re.compile(r"postgres(ql)?://[^:\s]+:(?!PASSWORD@|scamwatch@)[^@\s]+@(?!localhost|HOST)"),  # real DB password
    re.compile(r"(?i)(api[_-]?key|auth[_-]?key|client[_-]?secret)\s*[=:]\s*['\"][A-Za-z0-9_\-]{16,}['\"]"),
    re.compile(r"npg_[A-Za-z0-9]{10,}"),  # Neon password
]


def test_no_secrets_committed():
    files = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    hits = []
    for name in files:
        path = PROJECT_ROOT / name
        if not path.is_file() or path.suffix in {".png", ".pdf"}:
            continue
        text = path.read_text(errors="ignore")
        hits += [f"{name}: {p.pattern[:30]}" for p in SECRET_PATTERNS if p.search(text)]
    assert not hits, f"possible secrets: {hits}"
