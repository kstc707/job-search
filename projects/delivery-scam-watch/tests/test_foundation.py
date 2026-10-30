"""Component 0 checks: migrations, run logging, no duplicates, brand matching, retention."""

from __future__ import annotations

import shutil

import pytest

from scamwatch import db
from scamwatch.runlog import CollectorRun
from scamwatch.store import add_observation, brand_match, purge_raw, source_id, split_domain, upsert_domain, upsert_url

TABLES = {"sources", "collector_runs", "domains", "urls", "observations", "reports", "labels", "schema_migrations"}


def test_migration_creates_every_table(conn):
    names = {
        r[0]
        for r in conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'"
        ).fetchall()
    }
    assert TABLES <= names


def test_migrate_twice_applies_nothing_new(conn):
    assert db.migrate(conn) == []


def test_edited_migration_is_refused(conn, tmp_path):
    copy = tmp_path / "migrations"
    shutil.copytree(db.MIGRATIONS_DIR, copy)
    target = copy / "0001_init.sql"
    target.write_text(target.read_text() + "\n-- sneaky edit\n")
    with pytest.raises(db.MigrationEdited):
        db.migrate(conn, copy)


def test_planned_sources_are_seeded_disabled(conn):
    rows = dict(conn.execute("SELECT name, enabled FROM sources").fetchall())
    assert {"crtsh", "urlscan", "urlhaus", "phishtank", "openphish", "reddit", "rdap"} <= set(rows)
    assert not any(rows.values())


def test_successful_run_is_logged(conn):
    with CollectorRun(conn, "selftest") as run:
        run.seen, run.new = 3, 2
    status, seen, new, finished = conn.execute(
        "SELECT status, items_seen, items_new, finished_at FROM collector_runs WHERE id = %s", (run.id,)
    ).fetchone()
    assert (status, seen, new) == ("success", 3, 2) and finished is not None


def test_failed_run_is_logged_and_reraised(conn):
    with pytest.raises(ValueError):
        with CollectorRun(conn, "selftest") as run:
            raise ValueError("source returned garbage")
    status, error = conn.execute("SELECT status, error FROM collector_runs WHERE id = %s", (run.id,)).fetchone()
    assert status == "failed" and "source returned garbage" in error


def test_partial_run_keeps_the_problem(conn):
    with CollectorRun(conn, "selftest") as run:
        run.partial("1 of 4 keywords timed out")
    status, error = conn.execute("SELECT status, error FROM collector_runs WHERE id = %s", (run.id,)).fetchone()
    assert status == "partial" and "timed out" in error


def test_same_sighting_twice_is_stored_once(conn, brands):
    sid = source_id(conn, "selftest")
    with CollectorRun(conn, "selftest") as run:
        url_id, dom_id = upsert_url(conn, "https://fedex-redelivery.top/pay", brands)
        first = add_observation(
            conn, source_id=sid, run_id=run.id, source_ref="item-1", domain_id=dom_id, url_id=url_id, raw={"a": 1}
        )
        again = add_observation(
            conn, source_id=sid, run_id=run.id, source_ref="item-1", domain_id=dom_id, url_id=url_id, raw={"a": 1}
        )
        upsert_url(conn, "https://fedex-redelivery.top/pay", brands)
    assert (first, again) == (True, False)
    assert conn.execute("SELECT count(*) FROM observations").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM urls").fetchone()[0] == 1
    assert conn.execute("SELECT count(*) FROM domains").fetchone()[0] == 1


@pytest.mark.parametrize(
    "host,fqdn,registered,tld",
    [
        ("Track.FedEx-Help.co.uk.", "track.fedex-help.co.uk", "fedex-help.co.uk", "co.uk"),
        ("*.usps-redelivery.top", "usps-redelivery.top", "usps-redelivery.top", "top"),
        ("dhl.com", "dhl.com", "dhl.com", "com"),
    ],
)
def test_split_domain(host, fqdn, registered, tld):
    p = split_domain(host)
    assert (p.fqdn, p.registered_domain, p.tld) == (fqdn, registered, tld)


@pytest.mark.parametrize(
    "fqdn,brand,allowlisted",
    [
        ("www.fedex.com", "FedEx", True),  # the brand's own site: never flagged
        ("fedex-redelivery.top", "FedEx", False),  # lookalike
        ("tools.usps.com", "USPS", True),
        ("usps-postal-fee.xyz", "USPS", False),
        ("startups.example.org", "UPS", False),  # noisy keyword match, handled in component 5
        ("example.org", None, False),
    ],
)
def test_brand_match(brands, fqdn, brand, allowlisted):
    assert brand_match(fqdn, brands) == (brand, allowlisted)


def test_allowlisted_domain_is_marked(conn, brands):
    dom_id = upsert_domain(conn, "www.fedex.com", brands)
    assert conn.execute("SELECT allowlisted, brand_guess FROM domains WHERE id = %s", (dom_id,)).fetchone() == (
        True,
        "FedEx",
    )


def test_raw_records_are_purged_after_30_days(conn, brands):
    sid = source_id(conn, "selftest")
    with CollectorRun(conn, "selftest") as run:
        dom_id = upsert_domain(conn, "dhl-parcel-fee.top", brands)
        add_observation(conn, source_id=sid, run_id=run.id, source_ref="old", domain_id=dom_id, raw={"x": 1})
        add_observation(conn, source_id=sid, run_id=run.id, source_ref="new", domain_id=dom_id, raw={"x": 2})
    conn.execute("UPDATE observations SET observed_at = now() - interval '31 days' WHERE source_ref = 'old'")
    assert purge_raw(conn) == 1
    rows = dict(conn.execute("SELECT source_ref, raw IS NULL FROM observations").fetchall())
    assert rows == {"old": True, "new": False}
