-- 0002: the keyless sources the demo runs on, plus collector state and domain registration data.

INSERT INTO sources (name, kind, terms_url, min_interval_seconds, enabled, notes) VALUES
  ('phishingdb',   'feed',         'https://github.com/mitchellkrogza/Phishing.Database', 60, TRUE,
     'Phishing.Database ACTIVE domain list (GitHub raw); community blocklist used as scam labels'),
  ('phishingarmy', 'feed',         'https://phishing.army/', 60, TRUE,
     'phishing.army blocklist; second, independent community blocklist'),
  ('tranco',       'enrichment',   'https://tranco-list.eu/', 60, TRUE,
     'Tranco top 1M popular sites (research list); reference set of legitimate domains'),
  ('whoisds',      'certificates', 'https://www.whoisds.com/newly-registered-domains', 5, TRUE,
     'WhoisDS free daily newly registered domains; source_time = registration day'),
  ('ctlog',        'certificates', 'https://certificate.transparency.dev/', 0.5, TRUE,
     'Google Argon 2026h2 Certificate Transparency log, sampled; source_time = log timestamp');

UPDATE sources SET enabled = TRUE, min_interval_seconds = 300,
  notes = 'OpenPhish community feed; first sighting time approximates listing time'
  WHERE name = 'openphish';
UPDATE sources SET enabled = TRUE, min_interval_seconds = 1.5 WHERE name = 'rdap';

-- where a collector left off (for example the CT log position), so the next run continues
CREATE TABLE collector_state (
    source_id  INTEGER NOT NULL REFERENCES sources(id),
    key        TEXT NOT NULL,
    value      TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (source_id, key)
);

-- RDAP lookups: when a registered domain was created and by which registrar
CREATE TABLE registrations (
    registered_domain TEXT PRIMARY KEY,
    created_at        TIMESTAMPTZ,          -- registration date from the registry
    registrar         TEXT,
    status            TEXT NOT NULL,         -- 'ok', 'not_found', 'error', 'unsupported'
    checked_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
