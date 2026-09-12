import json
import os
import socket
import sqlite3
import time
import uuid
from pathlib import Path

import networkx as nx

from swarmci.adapters.tracing import attributes, rename, summary, traced


def uid():
    return uuid.uuid4().hex[:12]


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
        PRAGMA journal_mode=WAL;
        CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, status TEXT, config TEXT, created REAL, error TEXT);
        CREATE TABLE IF NOT EXISTS states(run TEXT, id TEXT, payload TEXT, PRIMARY KEY(run,id));
        CREATE TABLE IF NOT EXISTS edges(id TEXT PRIMARY KEY, run TEXT, source TEXT, target TEXT, payload TEXT);
        CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY, run TEXT, signature TEXT, status TEXT, payload TEXT, worker TEXT, error TEXT, UNIQUE(run,signature));
        CREATE TABLE IF NOT EXISTS bugs(id TEXT PRIMARY KEY, run TEXT, signature TEXT, payload TEXT, UNIQUE(run,signature));
        CREATE TABLE IF NOT EXISTS events(seq INTEGER PRIMARY KEY AUTOINCREMENT, run TEXT, kind TEXT, payload TEXT, created REAL);
        CREATE TABLE IF NOT EXISTS run_owners(run TEXT PRIMARY KEY, host TEXT, pid INTEGER);
        CREATE TABLE IF NOT EXISTS replay_failures(run TEXT, prefix TEXT, attempts INTEGER, PRIMARY KEY(run,prefix));
        """)

    def recover(self):
        for row in self.db.execute(
            "SELECT runs.id,run_owners.host,run_owners.pid FROM runs LEFT JOIN run_owners "
            "ON runs.id=run_owners.run WHERE status IN ('queued','running')"
        ).fetchall():
            if row["host"] and row["host"] != socket.gethostname():
                continue  # Another host owns recovery of its processes.
            if row["pid"]:
                try:
                    os.kill(row["pid"], 0)
                    continue
                except ProcessLookupError:
                    pass
                except PermissionError:
                    continue
            self.db.execute(
                "UPDATE runs SET status='interrupted',error='Owning process stopped; retained evidence is available.' WHERE id=?",
                (row["id"],),
            )
            self.db.execute(
                "UPDATE jobs SET status='interrupted' WHERE run=? AND status IN ('queued','running')",
                (row["id"],),
            )

    def event(self, run, kind, payload):
        self.db.execute(
            "INSERT INTO events(run,kind,payload,created) VALUES(?,?,?,?)",
            (run, kind, json.dumps(payload), time.time()),
        )

    def create_run(self, config):
        run = uid()
        self.db.execute(
            "INSERT INTO runs VALUES(?,?,?,?,?)", (run, "queued", config.model_dump_json(), time.time(), None)
        )
        self.event(run, "run.created", {"id": run})
        return run

    def status(self, run, status, error=None):
        if status == "running":
            self.db.execute(
                "INSERT OR REPLACE INTO run_owners VALUES(?,?,?)", (run, socket.gethostname(), os.getpid())
            )
        self.db.execute("UPDATE runs SET status=?,error=? WHERE id=?", (status, error, run))
        self.event(run, "run.status", {"status": status, "error": error})

    @traced("Graph: resolve discovered state")
    def node(self, run, state):
        new = (
            self.db.execute(
                "INSERT OR IGNORE INTO states VALUES(?,?,?)", (run, state["id"], json.dumps(state))
            ).rowcount
            > 0
        )
        attributes(state_id=state["id"], screen_key=state["screen_key"], new_state=new, merged=not new)
        rename(f"Graph · {'Add new state' if new else 'Merge existing state'}")
        summary(
            outputs={
                "state": state.get("label", ""),
                "resolution": "new" if new else "merged",
                "state_id": state["id"],
            }
        )
        self.event(run, "state.new" if new else "state.merged", state)
        return new

    def edge(self, run, source, target, payload):
        id = uid()
        self.db.execute("INSERT INTO edges VALUES(?,?,?,?,?)", (id, run, source, target, json.dumps(payload)))
        self.event(run, "transition", {"id": id, "source": source, "target": target, **payload})

    def enqueue(self, run, signature, payload):
        for row in self.db.execute("SELECT prefix FROM replay_failures WHERE run=? AND attempts>=2", (run,)):
            prefix = json.loads(row["prefix"])
            if payload.get("path", [])[: len(prefix)] == prefix:
                return False
        id = uid()
        added = self.db.execute(
            "INSERT OR IGNORE INTO jobs VALUES(?,?,?,?,?,?,?)",
            (id, run, signature, "queued", json.dumps(payload), None, None),
        ).rowcount
        if added:
            self.event(run, "job.queued", {"id": id, "depth": len(payload.get("path", []))})
        return bool(added)

    def claim(self, run, worker):
        # SQLite writer lock + UPDATE RETURNING makes claims atomic across processes.
        row = self.db.execute(
            "UPDATE jobs SET status='running',worker=? WHERE id=(SELECT id FROM jobs WHERE run=? AND status='queued' ORDER BY COALESCE(json_extract(payload,'$.priority'),0) DESC, rowid LIMIT 1) RETURNING *",
            (worker, run),
        ).fetchone()
        if row:
            self.event(run, "job.started", {"id": row["id"], "worker": worker})
            return {**dict(row), "payload": json.loads(row["payload"])}

    def finish(self, job, error=None):
        self.db.execute(
            "UPDATE jobs SET status=?,error=? WHERE id=?", ("error" if error else "done", error, job)
        )

    def exploration_attempts(self, run, screen_key):
        """Reservations count too, so workers select different controls while peers run."""
        rows = self.db.execute(
            "SELECT json_extract(payload,'$.control_key') AS control, count(*) AS n "
            "FROM jobs WHERE run=? AND status!='skipped' "
            "AND json_extract(payload,'$.screen_key')=? GROUP BY control",
            (run, screen_key),
        )
        return {r["control"]: r["n"] for r in rows if r["control"]}

    def attempted_job_count(self, run):
        return self.db.execute(
            "SELECT count(*) FROM jobs WHERE run=? AND status IN ('running','done','error')", (run,)
        ).fetchone()[0]

    def replay_failure(self, run, prefix):
        encoded = json.dumps(prefix, sort_keys=True)
        attempts = self.db.execute(
            "INSERT INTO replay_failures VALUES(?,?,1) ON CONFLICT(run,prefix) "
            "DO UPDATE SET attempts=attempts+1 RETURNING attempts",
            (run, encoded),
        ).fetchone()[0]
        skipped = 0
        if attempts >= 2:
            for row in self.db.execute(
                "SELECT id,payload FROM jobs WHERE run=? AND status='queued'", (run,)
            ).fetchall():
                path = json.loads(row["payload"]).get("path", [])
                if path[: len(prefix)] == prefix:
                    skipped += self.db.execute(
                        "UPDATE jobs SET status='skipped',error='Prefix failed replay twice' WHERE id=? AND status='queued'",
                        (row["id"],),
                    ).rowcount
        self.event(
            run,
            "checkpoint.unreliable",
            {"depth": len(prefix), "failed_attempts": attempts, "skipped_branches": skipped},
        )

    def bug(self, run, signature, payload):
        id = uid()
        added = self.db.execute(
            "INSERT OR IGNORE INTO bugs VALUES(?,?,?,?)", (id, run, signature, json.dumps(payload))
        ).rowcount
        if added:
            self.event(run, "bug.verified", {"id": id, **payload})
        return id if added else None

    def snapshot(self, run):
        row = self.db.execute("SELECT * FROM runs WHERE id=?", (run,)).fetchone()
        if not row:
            raise KeyError(run)
        nodes = [
            json.loads(r["payload"])
            for r in self.db.execute("SELECT payload FROM states WHERE run=?", (run,))
        ]
        edges = [
            {**dict(r), "payload": json.loads(r["payload"])}
            for r in self.db.execute("SELECT * FROM edges WHERE run=?", (run,))
        ]
        bugs = [
            {"id": r["id"], **json.loads(r["payload"])}
            for r in self.db.execute("SELECT * FROM bugs WHERE run=?", (run,))
        ]
        counts = {
            r["status"]: r["n"]
            for r in self.db.execute("SELECT status,count(*) n FROM jobs WHERE run=? GROUP BY status", (run,))
        }
        g = nx.MultiDiGraph()
        g.add_nodes_from(n["id"] for n in nodes)
        g.add_edges_from((e["source"], e["target"]) for e in edges)
        return {
            **dict(row),
            "config": json.loads(row["config"]),
            "nodes": nodes,
            "edges": edges,
            "bugs": bugs,
            "candidates": [
                json.loads(r["payload"])
                for r in self.db.execute(
                    "SELECT payload FROM events WHERE run=? AND kind='ux.candidate' ORDER BY seq", (run,)
                )
            ],
            "jobs": counts,
            "metrics": {
                "states": len(nodes),
                "transitions": len(edges),
                "screen_groups": len({n["screen_key"] for n in nodes}),
                "max_depth": max((n["depth"] for n in nodes), default=0),
                "verified_bugs": len(bugs),
                "converging_states": sum(1 for n in g if g.in_degree(n) > 1),
                "handoffs": sum(1 for e in edges if e["payload"].get("inherited")),
            },
        }

    def runs(self):
        return [
            dict(r)
            for r in self.db.execute(
                "SELECT id,status,created,error FROM runs ORDER BY created DESC LIMIT 50"
            )
        ]

    def events(self, run, after=0):
        return [
            {**dict(r), "payload": json.loads(r["payload"])}
            for r in self.db.execute(
                "SELECT * FROM events WHERE run=? AND seq>? ORDER BY seq LIMIT 200", (run, after)
            )
        ]

    def job_count(self, run):
        return self.db.execute("SELECT count(*) FROM jobs WHERE run=?", (run,)).fetchone()[0]

    def has_bug(self, run, signature):
        return bool(
            self.db.execute("SELECT 1 FROM bugs WHERE run=? AND signature=?", (run, signature)).fetchone()
        )
