-- One row per pickup task (LaDe-P). Times are stored as timestamps using the configured reference year.
CREATE TABLE IF NOT EXISTS pickups (
    order_id           BIGINT PRIMARY KEY,
    city               TEXT        NOT NULL,
    region_id          INTEGER     NOT NULL,
    aoi_id             INTEGER     NOT NULL,
    aoi_type           INTEGER     NOT NULL,
    courier_id         INTEGER     NOT NULL,
    lng                DOUBLE PRECISION NOT NULL,
    lat                DOUBLE PRECISION NOT NULL,
    accept_time        TIMESTAMP   NOT NULL,
    time_window_start  TIMESTAMP   NOT NULL,
    time_window_end    TIMESTAMP   NOT NULL,
    pickup_time        TIMESTAMP   NOT NULL,
    accept_gps_lng     DOUBLE PRECISION,
    accept_gps_lat     DOUBLE PRECISION,
    ds                 INTEGER     NOT NULL
);

-- The /at-risk endpoint asks "which tasks are open at time T" (accepted at or before T, picked up after T),
-- and for each of them "how many tasks did this courier have open when it was accepted".
-- A B-tree on accept_time cannot answer "T falls inside [accept, pickup)" efficiently, because most rows
-- were accepted before T. A GiST index on the time range can; adding courier_id (needs btree_gist)
-- answers the per-courier count from the index too. Measured on Shanghai at 10:00 on Oct 12
-- (5,702 open tasks): 3.3 s with B-tree indexes only, 0.48 s with this index.
CREATE EXTENSION IF NOT EXISTS btree_gist;
CREATE INDEX IF NOT EXISTS pickups_courier_open_range
    ON pickups USING gist (courier_id, tsrange(accept_time, pickup_time, '[)'));
-- Tasks accepted earlier the same day, per courier.
CREATE INDEX IF NOT EXISTS pickups_courier_accept ON pickups (courier_id, accept_time);
-- Region filter on /at-risk.
CREATE INDEX IF NOT EXISTS pickups_region_accept  ON pickups (region_id, accept_time);
