"""SQLite storage. One file, no setup."""
import json
import sqlite3
import threading
import time

from . import config

DB_PATH = config.DATA_DIR / "naqsha.db"
_lock = threading.Lock()
_conn = sqlite3.connect(DB_PATH, check_same_thread=False)
_conn.row_factory = sqlite3.Row

JSON_COLS = {"indicators", "rain_daily", "exposure", "risk_breakdown", "attempts"}

SCHEMA = """
CREATE TABLE IF NOT EXISTS hazards(
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  lat REAL, lon REAL, place TEXT,
  hazard_type TEXT, severity INTEGER, confidence REAL,
  indicators TEXT, evidence TEXT, recommended_action TEXT, road_blocked INTEGER,
  summary_en TEXT, summary_ur TEXT,
  transcript TEXT, language TEXT, description TEXT,
  photo TEXT, audio TEXT,
  rain_72h REAL, rain_daily TEXT, slope_deg REAL, exposure TEXT,
  risk_score INTEGER, risk_level TEXT, risk_breakdown TEXT,
  report_count INTEGER DEFAULT 1, status TEXT DEFAULT 'New',
  source TEXT, reporter TEXT,
  created_at REAL, updated_at REAL);
CREATE TABLE IF NOT EXISTS queries(
  id INTEGER PRIMARY KEY AUTOINCREMENT, question TEXT, query TEXT, attempts TEXT,
  result_count INTEGER, summary TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS alerts(
  id INTEGER PRIMARY KEY AUTOINCREMENT, hazard_id INTEGER, sms_en TEXT, sms_ur TEXT,
  notice_en TEXT, notice_ur TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS subscribers(
  chat_id TEXT PRIMARY KEY, name TEXT, lat REAL, lon REAL, radius_km REAL, created_at REAL);
CREATE TABLE IF NOT EXISTS families(code TEXT PRIMARY KEY, created_at REAL);
CREATE TABLE IF NOT EXISTS family_members(
  chat_id TEXT PRIMARY KEY, code TEXT, name TEXT, status TEXT, lat REAL, lon REAL, updated_at REAL);
CREATE TABLE IF NOT EXISTS checkins(
  id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id TEXT, name TEXT, lat REAL, lon REAL,
  status TEXT, created_at REAL);
CREATE TABLE IF NOT EXISTS teams(
  id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, type TEXT, chat_id TEXT, status TEXT DEFAULT 'available');
CREATE TABLE IF NOT EXISTS assignments(
  id INTEGER PRIMARY KEY AUTOINCREMENT, hazard_id INTEGER, team_id INTEGER, status TEXT,
  created_at REAL, updated_at REAL);
"""


def init():
    with _lock:
        _conn.executescript(SCHEMA)
        _conn.commit()


def _row(r) -> dict:
    d = dict(r)
    for k in JSON_COLS & d.keys():
        if d[k]:
            try:
                d[k] = json.loads(d[k])
            except Exception:
                pass
    return d


def query(sql: str, args=()) -> list[dict]:
    with _lock:
        return [_row(r) for r in _conn.execute(sql, args).fetchall()]


def one(sql: str, args=()) -> dict | None:
    rows = query(sql, args)
    return rows[0] if rows else None


def execute(sql: str, args=()) -> int:
    with _lock:
        cur = _conn.execute(sql, args)
        _conn.commit()
        return cur.lastrowid


def insert(table: str, data: dict) -> int:
    data = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v) for k, v in data.items()}
    cols = ",".join(data)
    marks = ",".join("?" for _ in data)
    return execute(f"INSERT INTO {table}({cols}) VALUES({marks})", tuple(data.values()))


def update(table: str, row_id, data: dict, key: str = "id"):
    data = {k: (json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else v) for k, v in data.items()}
    sets = ",".join(f"{k}=?" for k in data)
    execute(f"UPDATE {table} SET {sets} WHERE {key}=?", (*data.values(), row_id))


def now() -> float:
    return time.time()
