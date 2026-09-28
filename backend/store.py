"""
SQLite persistence.

Every collection (parcels, persons, deeds, requests, updates) is stored as
JSON documents in one `docs` table with the district lifted into an indexed
column, plus an append-only `audit` table and a small `meta` table. The
application keeps working copies in memory and writes changed records back
in a single transaction at the end of each successful request.

This is a deliberate prototype trade-off: it survives restarts and needs no
server, but it is a single-writer embedded database. The production path is
PostgreSQL + PostGIS (real spatial indexes, row-level security per district,
replication) — the document boundaries here map 1:1 onto tables there.
"""
import json
import os
import sqlite3
import threading


class Store:
    def __init__(self, path):
        self.path = path
        if path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self.lock = threading.RLock()
        with self.lock:
            if path != ":memory:":
                self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.executescript("""
                CREATE TABLE IF NOT EXISTS docs (
                    collection TEXT NOT NULL, key TEXT NOT NULL, district TEXT,
                    doc TEXT NOT NULL, PRIMARY KEY (collection, key));
                CREATE INDEX IF NOT EXISTS docs_district ON docs (collection, district);
                CREATE TABLE IF NOT EXISTS audit (seq INTEGER PRIMARY KEY, entry TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
            """)

    # -- meta
    def meta_get(self, k, default=None):
        with self.lock:
            row = self.conn.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return row[0] if row else default

    def meta_set(self, k, v):
        with self.lock:
            self.conn.execute("INSERT INTO meta(k,v) VALUES(?,?) ON CONFLICT(k) DO UPDATE SET v=excluded.v", (k, v))

    # -- documents
    def load_collection(self, name):
        with self.lock:
            rows = self.conn.execute("SELECT key, doc FROM docs WHERE collection=?", (name,)).fetchall()
        return {k: json.loads(d) for k, d in rows}

    def load_audit(self):
        with self.lock:
            rows = self.conn.execute("SELECT entry FROM audit ORDER BY seq").fetchall()
        return [json.loads(r[0]) for r in rows]

    def flush(self, upserts, audit_rows):
        """upserts: [(collection, key, district, doc_dict)], audit_rows: [(seq, entry_dict)] — one transaction."""
        if not upserts and not audit_rows:
            return
        with self.lock:
            self.conn.execute("BEGIN")
            try:
                for collection, key, district, doc in upserts:
                    self.conn.execute(
                        "INSERT INTO docs(collection,key,district,doc) VALUES(?,?,?,?) "
                        "ON CONFLICT(collection,key) DO UPDATE SET district=excluded.district, doc=excluded.doc",
                        (collection, key, district, json.dumps(doc, sort_keys=True, default=str)))
                for seq, entry in audit_rows:
                    self.conn.execute("INSERT INTO audit(seq, entry) VALUES(?,?)",
                                      (seq, json.dumps(entry, sort_keys=True)))
                self.conn.execute("COMMIT")
            except Exception:
                self.conn.execute("ROLLBACK")
                raise

    def close(self):
        with self.lock:
            self.conn.close()
