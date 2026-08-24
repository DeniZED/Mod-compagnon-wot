-- Schema historique local WoT Companion (SQLite). Versionne via PRAGMA user_version.
CREATE TABLE IF NOT EXISTS battles (
    id            TEXT PRIMARY KEY,
    started_ms    INTEGER,
    ended_ms      INTEGER,
    map_id        TEXT,
    spawn         TEXT,
    vehicle_id    TEXT,
    vehicle_role  TEXT,
    result        TEXT,
    damage        REAL DEFAULT 0,
    assist        REAL DEFAULT 0,
    survived      INTEGER DEFAULT 0,
    kills         INTEGER DEFAULT 0,
    hp_ratio_end  REAL,
    hp_lost_early INTEGER DEFAULT 0,   -- 1 si >50% HP perdus avant 3 min
    app_version   TEXT
);

CREATE TABLE IF NOT EXISTS battle_metrics (
    battle_id    TEXT,
    metric_code  TEXT,
    value        REAL,
    timestamp_ms INTEGER,
    FOREIGN KEY (battle_id) REFERENCES battles(id)
);

CREATE TABLE IF NOT EXISTS settings (
    key        TEXT PRIMARY KEY,
    value      TEXT,
    updated_at INTEGER
);

CREATE INDEX IF NOT EXISTS idx_battles_vehicle ON battles(vehicle_id);
CREATE INDEX IF NOT EXISTS idx_battles_started ON battles(started_ms);
CREATE INDEX IF NOT EXISTS idx_metrics_battle  ON battle_metrics(battle_id);
