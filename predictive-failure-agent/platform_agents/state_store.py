"""Durable workflow state, deliberately separate from pruned metric history."""
import json
import sqlite3
import time
from platform_agents.schemas import Experiment, TERMINAL, digest


class Conflict(ValueError):
    pass


class StateStore:
    def __init__(self, storage, clock=time.time):
        self.storage, self.clock = storage, clock
        with storage.connect() as db:
            db.executescript("""
            CREATE TABLE IF NOT EXISTS chaos_experiments(id TEXT PRIMARY KEY, state TEXT NOT NULL, payload TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS chaos_events(seq INTEGER PRIMARY KEY, experiment TEXT, ts REAL, kind TEXT, payload TEXT);
            CREATE TABLE IF NOT EXISTS chaos_control(key TEXT PRIMARY KEY, value TEXT);
            """)

    def get(self, experiment_id):
        with self.storage.connect() as db:
            row = db.execute("SELECT payload FROM chaos_experiments WHERE id=?", (experiment_id,)).fetchone()
        if not row:
            raise KeyError(experiment_id)
        return Experiment.model_validate_json(row[0])

    def list(self):
        with self.storage.connect() as db:
            return [Experiment.model_validate_json(r[0]) for r in db.execute("SELECT payload FROM chaos_experiments ORDER BY rowid DESC LIMIT 500")]

    def create(self, experiment):
        with self.storage.connect() as db:
            db.execute("INSERT INTO chaos_experiments VALUES(?,?,?)", (experiment.id, experiment.state, experiment.model_dump_json()))
            self._event(db, experiment.id, "PLAN", {"proposal_hash": experiment.proposal_hash})
        return experiment

    def change(self, experiment_id, expected, update, exclusive=False):
        """Compare-and-set inside a write transaction, including concurrency admission."""
        with self.storage.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT payload FROM chaos_experiments WHERE id=?", (experiment_id,)).fetchone()
            if not row:
                raise KeyError(experiment_id)
            current = Experiment.model_validate_json(row[0])
            if current.state not in expected:
                raise Conflict("Experiment state changed; refresh before retrying")
            if exclusive:
                placeholders = ",".join("?" for _ in TERMINAL | {"AWAIT_USER_APPROVAL", "APPROVED"})
                active = db.execute(f"SELECT id FROM chaos_experiments WHERE id<>? AND state NOT IN ({placeholders})", (experiment_id, *sorted(TERMINAL | {"AWAIT_USER_APPROVAL", "APPROVED"}))).fetchone()
                if active:
                    raise Conflict("Another experiment or unresolved rollback holds the execution lease")
            before = current.state
            update(current)
            # Validate the whole updated object, including immutable proposal hash.
            current = Experiment.model_validate(current.model_dump())
            if digest(current.proposal.model_dump()) != current.proposal_hash:
                raise Conflict("Immutable proposal content changed")
            db.execute("UPDATE chaos_experiments SET state=?,payload=? WHERE id=?", (current.state, current.model_dump_json(), current.id))
            self._event(db, current.id, current.state, {"from": before})
        return current

    def event(self, experiment_id, kind, payload):
        with self.storage.connect() as db:
            self._event(db, experiment_id, kind, payload)

    def _event(self, db, experiment_id, kind, payload):
        db.execute("INSERT INTO chaos_events(experiment,ts,kind,payload) VALUES(?,?,?,?)", (experiment_id, self.clock(), kind, json.dumps(payload, allow_nan=False)))

    def events(self, experiment_id=None):
        with self.storage.connect() as db:
            if experiment_id:
                rows = db.execute("SELECT ts,kind,payload FROM chaos_events WHERE experiment=? ORDER BY seq", (experiment_id,))
            else:
                rows = db.execute("SELECT ts,kind,payload FROM chaos_events ORDER BY seq DESC LIMIT 500")
            return [{"timestamp": r[0], "kind": r[1], "data": json.loads(r[2])} for r in rows]

    def control(self, key, value=None):
        with self.storage.connect() as db:
            if value is not None:
                db.execute("INSERT OR REPLACE INTO chaos_control VALUES(?,?)", (key, json.dumps(value)))
                return value
            row = db.execute("SELECT value FROM chaos_control WHERE key=?", (key,)).fetchone()
            return json.loads(row[0]) if row else None
