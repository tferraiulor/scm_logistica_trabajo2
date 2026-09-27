from __future__ import annotations

"""Persistencia central: SQLite + tablas de negocio y catálogos maestros.

Todos los módulos leen y escriben aquí. Se usa un acceso síncrono simple con
sqlite3 (thread-safe con check_same_thread) + un caché en memoria para las
señales en tiempo real (POS, IoT, telemetría) que deben leerse a alta frecuencia.
"""

import json
import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from . import config

_lock = threading.RLock()
_real_time: dict[str, Any] = {}          # señales en streaming (POS, IoT)
_real_time_history: dict[str, list[dict]] = {}


def _db_path() -> Path:
    p = Path(config.SQLITE_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(_db_path()), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    sku TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    category TEXT,
    dimensions TEXT,
    weight_kg REAL,
    fragile INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS regions (
    region_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    warehouse_id TEXT
);

CREATE TABLE IF NOT EXISTS sales_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    sku TEXT NOT NULL,
    region_id TEXT NOT NULL,
    units INTEGER NOT NULL,
    price_eur REAL,
    channel TEXT
);

CREATE TABLE IF NOT EXISTS promotions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sku TEXT,
    region_id TEXT,
    promo_type TEXT,        -- discount | bundle | holiday
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    impact_factor REAL DEFAULT 1.0
);

CREATE TABLE IF NOT EXISTS forecasts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL,
    sku TEXT NOT NULL,
    region_id TEXT NOT NULL,
    date TEXT NOT NULL,
    predicted_units REAL NOT NULL,
    actual_units REAL,
    lower_bound REAL,
    upper_bound REAL,
    confidence REAL,
    mape REAL,
    model_info TEXT
);

CREATE TABLE IF NOT EXISTS stock (
    sku TEXT NOT NULL,
    region_id TEXT NOT NULL,
    warehouse_zone TEXT,
    on_hand INTEGER NOT NULL DEFAULT 0,
    reorder_point INTEGER DEFAULT 0,
    PRIMARY KEY (sku, region_id)
);

CREATE TABLE IF NOT EXISTS alerts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    module TEXT NOT NULL,
    type TEXT NOT NULL,          -- stockout | overstock | maintenance | delay | supplier
    severity TEXT NOT NULL,      -- critical | warning | info
    message TEXT NOT NULL,
    payload TEXT,
    created_at TEXT NOT NULL,
    ack_by TEXT,
    ack_at TEXT,
    status TEXT DEFAULT 'open'    -- open | ack | closed
);

CREATE TABLE IF NOT EXISTS carriers (
    carrier_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    vehicle_type TEXT,
    capacity_kg REAL,
    capacity_m3 REAL,
    pre_approved INTEGER DEFAULT 1,
    zones TEXT,                  -- JSON list of served zone ids
    per_km_cost REAL,
    rating REAL DEFAULT 5.0
);

CREATE TABLE IF NOT EXISTS deliveries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    shipment_id TEXT NOT NULL,
    carrier_id TEXT NOT NULL,
    origin TEXT,
    destination TEXT,
    customer_id TEXT,
    vehicle_telemetry TEXT,      -- JSON {status, lat, lng, delay_min, ...}
    route_plan TEXT,             -- JSON ordered waypoints
    planned_eta TEXT,
    current_eta TEXT,
    required_window_start TEXT,
    required_window_end TEXT,
    cost_eur REAL,
    status TEXT DEFAULT 'planned',   -- planned | in_transit | delivered | disrupted | retendered
    incident_log TEXT             -- JSON array de incidentes
);

CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    country TEXT,
    city TEXT,
    material TEXT NOT NULL,
    otif_rate REAL,          -- 0..1 on time in full
    financial_stability INTEGER,  -- 0..100
    geo_risk INTEGER,        -- 0..100 geopolitical/disaster
    unit_cost REAL,
    status TEXT DEFAULT 'active'
);

CREATE TABLE IF NOT EXISTS supplier_score_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    supplier_id TEXT NOT NULL,
    score REAL NOT NULL,
    breakdown TEXT,          -- JSON de factores
    evaluated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS recommendation_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    module TEXT NOT NULL,
    action TEXT NOT NULL,
    description TEXT NOT NULL,
    factors TEXT,            -- JSON explicabilidad
    confidence REAL,
    estimated_impact_eur REAL,
    requires_human_approval INTEGER DEFAULT 0,
    status TEXT DEFAULT 'pending',   -- pending | auto_executed | approved | rejected | requires_approval
    decision_by TEXT,
    decision_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS warehouse_zones (
    zone_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    dock_distance_m REAL,
    slot_count INTEGER DEFAULT 0,
    current_skus TEXT          -- JSON list
);

CREATE TABLE IF NOT EXISTS machines (
    machine_id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT,
    threshold_vibration REAL,
    threshold_temp REAL,
    degraded INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS work_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    machine_id TEXT NOT NULL,
    type TEXT NOT NULL,          -- predictive | corrective
    priority TEXT,
    description TEXT,
    triggered_by TEXT,           -- telemetry signature
    status TEXT DEFAULT 'open',
    created_at TEXT NOT NULL,
    completed_at TEXT
);

CREATE TABLE IF NOT EXISTS maintenance_telemetry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    machine_id TEXT NOT NULL,
    ts TEXT NOT NULL,
    vibration REAL,
    temperature REAL,
    anomaly INTEGER DEFAULT 0
);
"""


def init_db() -> None:
    with _lock, _conn() as conn:
        conn.executescript(SCHEMA)


def execute(sql: str, params: tuple = ()) -> int:
    with _lock, _conn() as conn:
        cur = conn.execute(sql, params)
        conn.commit()
        return cur.lastrowid


def executemany(sql: str, seq: list) -> None:
    with _lock, _conn() as conn:
        conn.executemany(sql, seq)
        conn.commit()


def query(sql: str, params: tuple = (), rows_to_dict=True) -> list[dict]:
    with _lock, _conn() as conn:
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows] if rows_to_dict else rows


def query_one(sql: str, params: tuple = ()) -> Optional[dict]:
    rows = query(sql, params, True)
    return rows[0] if rows else None


# --- RT (en memoria) ---

def rt_set(key: str, value: Any) -> None:
    _real_time[key] = value


def rt_get(key: str, default: Any = None) -> Any:
    return _real_time.get(key, default)


def rt_append(key: str, item: dict) -> None:
    _real_time_history.setdefault(key, []).append(item)
    if len(_real_time_history[key]) > 5000:
        _real_time_history[key] = _real_time_history[key][-2500:]


def rt_history(key: str) -> list[dict]:
    return _real_time_history.get(key, [])


def jloads(v: Any, default: Any = None) -> Any:
    if v is None:
        return default
    try:
        return json.loads(v)
    except (TypeError, ValueError):
        return default
