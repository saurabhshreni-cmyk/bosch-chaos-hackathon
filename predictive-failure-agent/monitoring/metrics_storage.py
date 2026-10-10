import json
import sqlite3
import time
from pathlib import Path


class Storage:
    def __init__(self, path, retention_days=7, max_samples=10000):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.retention_days = max(1, min(int(retention_days), 365))
        self.max_samples = max(10, min(int(max_samples), 100000))
        with self.connect() as db:
            db.executescript("CREATE TABLE IF NOT EXISTS records(id INTEGER PRIMARY KEY, kind TEXT, ts REAL, payload TEXT); CREATE INDEX IF NOT EXISTS record_kind ON records(kind, ts); CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY, ts REAL, payload TEXT);")

    def connect(self):
        return sqlite3.connect(self.path, timeout=10)

    def save(self, kind, payload):
        with self.connect() as db:
            db.execute("INSERT INTO records(kind,ts,payload) VALUES(?,?,?)", (kind, time.time(), json.dumps(payload, allow_nan=False)))
            db.execute("DELETE FROM records WHERE ts < ?", (time.time() - self.retention_days * 86400,))
            db.execute("DELETE FROM records WHERE id NOT IN (SELECT id FROM records ORDER BY id DESC LIMIT ?)", (self.max_samples,))
            db.execute("DELETE FROM cache WHERE ts < ?", (time.time() - self.retention_days * 86400,))

    def read(self, kind, limit=100):
        with self.connect() as db:
            return [json.loads(row[0]) for row in db.execute("SELECT payload FROM records WHERE kind=? ORDER BY id DESC LIMIT ?", (kind, min(max(limit, 1), 10000)))]

    def cache_get(self, key):
        with self.connect() as db:
            row = db.execute("SELECT payload FROM cache WHERE key=? AND ts>?", (key, time.time() - self.retention_days * 86400)).fetchone()
            return json.loads(row[0]) if row else None

    def cache_set(self, key, value):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO cache VALUES(?,?,?)", (key, time.time(), json.dumps(value)))
            db.execute("DELETE FROM cache WHERE key NOT IN (SELECT key FROM cache ORDER BY ts DESC LIMIT ?)", (self.max_samples,))
