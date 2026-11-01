"""Build the labelled real dataset from what the collectors stored.

  scam        on a community blocklist (Phishing.Database, phishing.army, OpenPhish) AND the
              brand appears as a word of its own (so 'microsoft-groups-login' is not counted as
              a delivery scam; it is phishing, but out of scope)
  legitimate  in the Tranco top-1M popular sites, not on any blocklist, not allowlisted
  stream      everything else the certificate log and new-registration list surfaced: the
              unlabelled input a live monitor actually has to triage

Allowlisted domains (the brands' own sites) are left out: they are never flagged by rule.
"""

from __future__ import annotations

import pandas as pd
import psycopg

from .features import brand_token

BLOCKLISTS = ("phishingdb", "phishingarmy", "openphish")


def load(conn: psycopg.Connection) -> pd.DataFrame:
    rows = conn.execute(
        """SELECT d.fqdn, d.registered_domain, d.tld, d.allowlisted, d.first_seen,
                  array_agg(DISTINCT s.name) AS sources,
                  min(o.observed_at) FILTER (WHERE s.name IN ('phishingdb','phishingarmy','openphish')) AS first_listed,
                  min(o.source_time) FILTER (WHERE s.name IN ('whoisds','ctlog')) AS first_new_signal,
                  min(o.observed_at) FILTER (WHERE s.name IN ('whoisds','ctlog')) AS first_new_observed
           FROM domains d JOIN observations o ON o.domain_id = d.id JOIN sources s ON s.id = o.source_id
           WHERE s.name <> 'selftest'
           GROUP BY d.id"""
    ).fetchall()
    df = pd.DataFrame(
        rows,
        columns=[
            "fqdn",
            "registered_domain",
            "tld",
            "allowlisted",
            "first_seen",
            "sources",
            "first_listed",
            "first_new_signal",
            "first_new_observed",
        ],
    )
    df = df[~df.allowlisted].copy()
    df["on_blocklist"] = df.sources.apply(lambda s: any(x in BLOCKLISTS for x in s))
    df["in_tranco"] = df.sources.apply(lambda s: "tranco" in s)
    df["brand"] = df.fqdn.apply(brand_token)
    df["label"] = None
    df.loc[df.on_blocklist & df.brand.notna(), "label"] = "scam"
    df.loc[df.in_tranco & ~df.on_blocklist, "label"] = "legitimate"
    df["set"] = df.label.fillna("stream").where(
        df.label.notna() | df.sources.apply(lambda s: any(x in ("whoisds", "ctlog") for x in s)), "out_of_scope"
    )
    return df.reset_index(drop=True)
