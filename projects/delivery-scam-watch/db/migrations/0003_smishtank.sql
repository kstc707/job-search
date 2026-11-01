-- 0003: real scam text messages from SmishTank (a public, community-reported smishing collection
-- run by university researchers). Stored in the existing `reports` table, with a few extra fields.

INSERT INTO sources (name, kind, terms_url, min_interval_seconds, enabled, notes) VALUES
  ('smishtank', 'reports', 'https://smishtank.com/terms', 5, TRUE,
     'SmishTank: Dataset I (published research CSV, cite Timko & Rahman 2024) plus the public feed of the '
     'newest 100 reported texts; robots.txt allows all');

ALTER TABLE reports
  ADD COLUMN sender        TEXT,          -- phone number, short code or email address that sent the text
  ADD COLUMN sender_type   TEXT,          -- as given by the source (e.g. 'Short Code'), or derived
  ADD COLUMN brand_claimed TEXT,          -- brand the source says the text impersonates, if any
  ADD COLUMN collected_at  TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE INDEX reports_posted_at ON reports (posted_at);
