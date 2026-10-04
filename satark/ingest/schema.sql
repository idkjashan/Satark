-- Registry database (LLD §14.1). Built fresh by `python -m satark.ingest`, opened read-only by the API.
-- Normalised columns (*_norm) are computed with satark.infra.norm so lookups compare like with like.

CREATE TABLE meta (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);  -- data_version, built_at

CREATE TABLE ingest_run (
  id          INTEGER PRIMARY KEY,
  source_id   TEXT NOT NULL,
  started_at  TEXT NOT NULL,
  finished_at TEXT,
  status      TEXT NOT NULL CHECK (status IN ('ok', 'failed', 'kept_previous')),
  row_count   INTEGER NOT NULL DEFAULT 0,
  sha256      TEXT,
  as_on       TEXT NOT NULL
);
CREATE INDEX ingest_run_source ON ingest_run (source_id, finished_at);

-- SEBI registered intermediaries. A broker appears once per segment file, so reg_no is not unique.
CREATE TABLE intermediary (
  id         INTEGER PRIMARY KEY,
  reg_no     TEXT NOT NULL,           -- upper case, no spaces: INA000012345, IN-DP-192-2016, MF/020/94/8
  category   TEXT NOT NULL,           -- IA RA BROKER DP PMS MF AIF MB RTA
  name       TEXT NOT NULL,
  name_norm  TEXT NOT NULL,
  trade_name TEXT,
  exchange   TEXT,
  valid_from TEXT,                    -- ISO date or NULL
  valid_to   TEXT,                    -- ISO date, 'perpetual' or NULL
  source_id  TEXT NOT NULL,           -- e.g. sebi_ia
  run_id     INTEGER NOT NULL REFERENCES ingest_run (id)
);
CREATE INDEX intermediary_reg ON intermediary (reg_no);
CREATE INDEX intermediary_name ON intermediary (name_norm);
CREATE VIRTUAL TABLE intermediary_fts USING fts5 (name_norm, trade_name, content = 'intermediary', content_rowid = 'id');

-- Official caution / alert lists: NSE, BSE, RBI Alert List, IRDAI, FIU-IND...
CREATE TABLE caution_entry (
  id           INTEGER PRIMARY KEY,
  list_id      TEXT NOT NULL,         -- e.g. nse_caution, rbi_alert_list
  entry_type   TEXT NOT NULL CHECK (entry_type IN ('name', 'phone', 'domain', 'url', 'upi', 'telegram', 'handle', 'app')),
  value_norm   TEXT NOT NULL,
  display      TEXT NOT NULL,
  published_at TEXT,
  source_url   TEXT NOT NULL,
  run_id       INTEGER NOT NULL REFERENCES ingest_run (id)
);
CREATE INDEX caution_lookup ON caution_entry (entry_type, value_norm);

-- Phishing / threat-intelligence domains (Phishing.Database, Hagezi TIF, local additions).
CREATE TABLE blocklist_domain (
  domain TEXT PRIMARY KEY,            -- registrable domain or full host, lower case, punycode
  feeds  TEXT NOT NULL,               -- comma list of feed ids
  run_id INTEGER NOT NULL
) WITHOUT ROWID;

-- Official domains of regulators, exchanges, depositories, brokers, banks, AMCs.
CREATE TABLE official_domain (
  domain      TEXT PRIMARY KEY,       -- registrable domain, lower case
  entity_name TEXT NOT NULL,
  category    TEXT NOT NULL,          -- regulator exchange depository broker bank amc government other
  brand_id    TEXT,                   -- config/brands.yaml id when it came from there
  run_id      INTEGER NOT NULL REFERENCES ingest_run (id)
);

-- Brokers' and AMCs' official apps (NSE list, AMFI list).
CREATE TABLE app_registry (
  package_id  TEXT PRIMARY KEY,
  app_name    TEXT,
  member_name TEXT,
  developer   TEXT,
  source_list TEXT NOT NULL,          -- nse_broker_apps, amfi_apps
  run_id      INTEGER NOT NULL REFERENCES ingest_run (id)
);

-- Brokers' and AMCs' official social handles.
CREATE TABLE social_handle (
  platform    TEXT NOT NULL CHECK (platform IN ('x', 'facebook', 'instagram', 'youtube', 'telegram', 'whatsapp', 'linkedin')),
  handle_norm TEXT NOT NULL,
  entity_name TEXT NOT NULL,
  entity_kind TEXT NOT NULL,          -- broker amc regulator
  run_id      INTEGER NOT NULL REFERENCES ingest_run (id),
  PRIMARY KEY (platform, handle_norm)
);

-- SEBI-debarred entities (NSE list). PAN is stored only as SHA-256 of the upper-case PAN.
CREATE TABLE debarred (
  id         INTEGER PRIMARY KEY,
  name       TEXT NOT NULL,
  name_norm  TEXT NOT NULL,
  pan_sha256 TEXT,
  order_date TEXT,
  order_ref  TEXT,
  period     TEXT,
  revoked    INTEGER NOT NULL DEFAULT 0,
  run_id     INTEGER NOT NULL REFERENCES ingest_run (id)
);
CREATE INDEX debarred_name ON debarred (name_norm);
CREATE INDEX debarred_pan ON debarred (pan_sha256);

-- Popularity: Chrome UX Report India top list (rank bucket 1000, 5000, 10000, ... 1000000).
CREATE TABLE popularity (
  domain      TEXT PRIMARY KEY,       -- registrable domain
  crux_bucket INTEGER,
  run_id      INTEGER NOT NULL
) WITHOUT ROWID;

-- UPI handles -> bank and probable app.
CREATE TABLE psp_handle (
  handle TEXT PRIMARY KEY,            -- without '@', lower case: okaxis, ybl, validhdfc
  bank   TEXT NOT NULL,
  app    TEXT,
  run_id INTEGER NOT NULL REFERENCES ingest_run (id)
);

-- Listed securities (NSE EQUITY_L): company names arm the no-tips output guard.
CREATE TABLE listed_security (
  symbol    TEXT PRIMARY KEY,
  name      TEXT NOT NULL,
  name_norm TEXT NOT NULL,
  isin      TEXT,
  run_id    INTEGER NOT NULL REFERENCES ingest_run (id)
);
