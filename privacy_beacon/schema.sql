-- Privacy Beacon Analytics (SQLite schema)
-- NOTE: No IP address field exists by design.

CREATE TABLE IF NOT EXISTS beacons (
  beacon_id TEXT PRIMARY KEY,
  label TEXT NOT NULL DEFAULT '',
  created_ts INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS hits (
  hit_id INTEGER PRIMARY KEY AUTOINCREMENT,
  ts INTEGER NOT NULL,
  beacon_id TEXT NOT NULL,
  hit_type TEXT NOT NULL,
  origin_type TEXT NOT NULL,         -- client | server | unknown
  user_agent TEXT NOT NULL,
  referrer TEXT NOT NULL,            -- normalized URL
  page_url TEXT NOT NULL,            -- normalized URL
  screen_w INTEGER,
  screen_h INTEGER,
  headers_json TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_hits_ts ON hits(ts);
CREATE INDEX IF NOT EXISTS idx_hits_beacon_ts ON hits(beacon_id, ts);
CREATE INDEX IF NOT EXISTS idx_hits_type_ts ON hits(hit_type, ts);

