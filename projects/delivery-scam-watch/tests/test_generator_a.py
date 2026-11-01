"""Generator A is frozen: these tests fail if anyone changes it after real data was seen."""

from __future__ import annotations

import csv
import hashlib
import re

from scamwatch.config import PROJECT_ROOT, load_brands
from scamwatch.store import brand_match
from scamwatch.synthetic import generator_a

FREEZE = (PROJECT_ROOT / "FREEZE.md").read_text()


def _frozen_sha(name: str) -> str:
    return re.search(rf"{re.escape(name)}\s+sha256\s+([0-9a-f]{{64}})", FREEZE).group(1)


def test_output_matches_frozen_checksums(tmp_path):
    for path in generator_a.write(tmp_path):
        assert hashlib.sha256(path.read_bytes()).hexdigest() == _frozen_sha(path.name), (
            f"{path.name} changed: generator A is frozen; put improvements in generator B"
        )


def test_committed_files_match_frozen_checksums():
    for name in ("generator_a_domains.csv", "generator_a_texts.csv"):
        data = (PROJECT_ROOT / "data" / "synthetic" / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == _frozen_sha(name)


def test_every_assumed_pattern_is_present():
    domains, _ = generator_a.generate()
    found = {d["pattern"] for d in domains}
    assert {p for p, _ in generator_a.SCAM_PATTERNS} | {p for p, _ in generator_a.LEGIT_PATTERNS} <= found


def test_no_allowlisted_domain_is_labelled_scam():
    brands = load_brands()
    domains, _ = generator_a.generate()
    assert not [d for d in domains if d["label"] == "scam" and brand_match(d["domain"], brands)[1]]


def test_texts_link_where_they_should():
    _, texts = generator_a.generate()
    official = set(generator_a.OFFICIAL.values())
    for t in texts:
        host = re.search(r"https://([^/\s]+)", t["text"]).group(1)
        is_official = host.removeprefix("www.") in official
        assert is_official == (t["label"] == "legitimate"), t["text"]


def test_committed_csv_is_readable():
    rows = list(csv.DictReader((PROJECT_ROOT / "data" / "synthetic" / "generator_a_domains.csv").open()))
    assert len(rows) == generator_a.N_DOMAINS
