import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from app.config import settings


SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS ingest_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    region_key TEXT NOT NULL,
    query TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT (datetime('now')),
    completed_at TEXT,
    element_count INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'running',
    error TEXT
);

CREATE TABLE IF NOT EXISTS osm_elements (
    osm_type TEXT NOT NULL,
    osm_id INTEGER NOT NULL,
    power TEXT NOT NULL,
    name TEXT,
    voltage TEXT,
    operator TEXT,
    frequency TEXT,
    cables TEXT,
    circuits TEXT,
    location TEXT,
    tags_json TEXT NOT NULL,
    geometry_json TEXT,
    lat REAL,
    lon REAL,
    updated_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (osm_type, osm_id)
);

CREATE TABLE IF NOT EXISTS element_regions (
    osm_type TEXT NOT NULL,
    osm_id INTEGER NOT NULL,
    region_key TEXT NOT NULL,
    ingest_run_id INTEGER NOT NULL,
    PRIMARY KEY (osm_type, osm_id, region_key),
    FOREIGN KEY (osm_type, osm_id) REFERENCES osm_elements(osm_type, osm_id) ON DELETE CASCADE,
    FOREIGN KEY (ingest_run_id) REFERENCES ingest_runs(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_osm_elements_power ON osm_elements(power);
CREATE INDEX IF NOT EXISTS idx_osm_elements_name ON osm_elements(name);
CREATE INDEX IF NOT EXISTS idx_osm_elements_voltage ON osm_elements(voltage);
CREATE INDEX IF NOT EXISTS idx_element_regions_region ON element_regions(region_key);
"""


def connect(path: Path | None = None) -> sqlite3.Connection:
    database_path = path or settings.database_path
    database_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(database_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path: Path | None = None) -> None:
    with connect(path) as conn:
        conn.executescript(SCHEMA)


@contextmanager
def get_db() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
