-- 0001_init: the foundation tables. Never edit this file once applied; add 0002_... instead.
-- Every sighting from every source lands in `observations` (append-only). Domains and URLs
-- are stored once each and point back to all their sightings, so every number on the
-- dashboard can be traced to the source, run and time it came from.

CREATE TABLE sources (
    id            SERIAL PRIMARY KEY,
    name          TEXT NOT NULL UNIQUE,          -- short code, e.g. 'crtsh'
    kind          TEXT NOT NULL CHECK (kind IN ('certificates', 'feed', 'reports', 'enrichment', 'test')),
    terms_url     TEXT,                          -- the terms of service we follow
    min_interval_seconds NUMERIC NOT NULL DEFAULT 1,  -- our own politeness limit between requests
    enabled       BOOLEAN NOT NULL DEFAULT FALSE, -- switched on when its collector is built and reviewed
    notes         TEXT
);

CREATE TABLE collector_runs (
    id            BIGSERIAL PRIMARY KEY,
    source_id     INTEGER NOT NULL REFERENCES sources(id),
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ,
    status        TEXT NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'success', 'partial', 'failed')),
    items_seen    INTEGER NOT NULL DEFAULT 0,
    items_new     INTEGER NOT NULL DEFAULT 0,
    error         TEXT
);
CREATE INDEX collector_runs_source_started ON collector_runs (source_id, started_at DESC);

CREATE TABLE domains (
    id                BIGSERIAL PRIMARY KEY,
    fqdn              TEXT NOT NULL UNIQUE,      -- full name, lower-case, e.g. 'track.fedex-help.top'
    registered_domain TEXT NOT NULL,             -- what someone actually registers, e.g. 'fedex-help.top'
    tld               TEXT NOT NULL,             -- public suffix, e.g. 'top' or 'co.uk'
    first_seen        TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen         TIMESTAMPTZ NOT NULL DEFAULT now(),
    brand_guess       TEXT,                      -- which brand keyword it contains, if any
    allowlisted       BOOLEAN NOT NULL DEFAULT FALSE  -- on a brand's allowlist: never flagged
);
CREATE INDEX domains_registered ON domains (registered_domain);
CREATE INDEX domains_first_seen ON domains (first_seen DESC);

CREATE TABLE urls (
    id          BIGSERIAL PRIMARY KEY,
    url         TEXT NOT NULL UNIQUE,            -- stored raw for analysis; only ever displayed defanged
    domain_id   BIGINT NOT NULL REFERENCES domains(id),
    first_seen  TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX urls_domain ON urls (domain_id);

CREATE TABLE observations (
    id            BIGSERIAL PRIMARY KEY,
    source_id     INTEGER NOT NULL REFERENCES sources(id),
    run_id        BIGINT NOT NULL REFERENCES collector_runs(id),
    observed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),  -- when we saw it
    source_time   TIMESTAMPTZ,                         -- when the source says it happened
    source_ref    TEXT NOT NULL,                       -- the source's own ID for the item
    domain_id     BIGINT REFERENCES domains(id),
    url_id        BIGINT REFERENCES urls(id),
    raw           JSONB,                               -- original record; cleared after 30 days
    raw_purged_at TIMESTAMPTZ,
    UNIQUE (source_id, source_ref)                     -- re-running a collector never duplicates
);
CREATE INDEX observations_domain ON observations (domain_id);
CREATE INDEX observations_observed ON observations (observed_at DESC);

CREATE TABLE reports (
    id               BIGSERIAL PRIMARY KEY,
    source_id        INTEGER NOT NULL REFERENCES sources(id),
    run_id           BIGINT NOT NULL REFERENCES collector_runs(id),
    external_id      TEXT NOT NULL,                    -- e.g. the Reddit post ID
    posted_at        TIMESTAMPTZ,
    text             TEXT NOT NULL,
    extracted_urls   TEXT[] NOT NULL DEFAULT '{}',
    UNIQUE (source_id, external_id)
);

CREATE TABLE labels (
    id          BIGSERIAL PRIMARY KEY,
    domain_id   BIGINT NOT NULL REFERENCES domains(id),
    label       TEXT NOT NULL CHECK (label IN ('scam', 'legitimate', 'unsure')),
    labeler     TEXT NOT NULL,
    labeled_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    note        TEXT,
    UNIQUE (domain_id, labeler)                        -- one current label per person per domain
);

-- The sources we plan to use. All start disabled; each is switched on after its collector
-- is built and reviewed. min_interval_seconds is our own politeness floor, below any limit
-- the source publishes.
INSERT INTO sources (name, kind, terms_url, min_interval_seconds, notes) VALUES
  ('crtsh',     'certificates', 'https://crt.sh/', 5,  'Certificate Transparency search; no key'),
  ('urlscan',   'feed',         'https://urlscan.io/terms/', 2, 'API key; daily quota'),
  ('urlhaus',   'feed',         'https://urlhaus.abuse.ch/api/', 2, 'abuse.ch Auth-Key'),
  ('phishtank', 'feed',         'https://phishtank.org/developer_info.php', 5, 'app key and user-agent required'),
  ('openphish', 'feed',         'https://openphish.com/', 60, 'community feed; check terms before enabling'),
  ('reddit',    'reports',      'https://redditinc.com/policies/data-api-terms', 1, 'OAuth2 script app'),
  ('rdap',      'enrichment',   'https://about.rdap.org/', 2, 'registration date and registrar'),
  ('selftest',  'test',         NULL, 0, 'used by the hello command and tests only');
