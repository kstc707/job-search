"""Collectors: each one downloads a public source, keeps only items that mention a watched
brand keyword, and stores them through scamwatch.store inside a logged CollectorRun.

Parsing is kept in pure functions (`parse_*`) so tests can run them on recorded samples without
touching the network.
"""

from __future__ import annotations

import re

from ..config import load_brands


def keyword_pattern() -> re.Pattern[str]:
    """One regular expression matching any brand keyword, longest first."""
    words = sorted({k for b in load_brands() for k in b.keywords}, key=len, reverse=True)
    return re.compile("|".join(re.escape(w) for w in words))
