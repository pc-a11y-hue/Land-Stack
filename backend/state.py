"""
Working state + persistence glue.

Collections live in memory (fast, simple) and are written back to SQLite at
the end of every request that changed them (see app.py after_request).
Always access these as `state.PARCELS` etc. (never `from state import ...`)
so re-initialising for tests keeps every module pointing at the same objects.
"""
import threading
import uuid

import audit as audit_mod
import config
from store import Store

LOCK = threading.RLock()
DB = None
SECRET_KEY = None
MODEL = None
BOOT_CHAIN_CHECK = None

PARCELS, PERSONS, DEEDS, REQUESTS, UPDATES, OFFICERS = {}, {}, {}, {}, {}, {}
USERNAMES = {}          # citizen username -> person_id
AUDIT = []
_COLL = {"parcels": PARCELS, "persons": PERSONS, "deeds": DEEDS,
         "requests": REQUESTS, "updates": UPDATES, "officers": OFFICERS}
_dirty = set()
_pending_audit = []


def init(db_path=None):
    """(Re)load state from the database, seeding it on first run."""
    global DB, SECRET_KEY, MODEL, BOOT_CHAIN_CHECK
    import bootstrap
    import risk_model
    if DB is not None:
        DB.close()
    DB = Store(db_path or config.DB_PATH)
    for c in _COLL.values():
        c.clear()
    AUDIT.clear()
    USERNAMES.clear()
    _dirty.clear()
    _pending_audit.clear()

    if DB.meta_get("seeded") is None:
        bootstrap.seed()
    else:
        for name, coll in _COLL.items():
            coll.update(DB.load_collection(name))
        AUDIT.extend(DB.load_audit())
    for pid, p in PERSONS.items():
        USERNAMES[p["username"]] = pid

    SECRET_KEY = DB.meta_get("secret_key")
    if not SECRET_KEY:
        import secrets
        SECRET_KEY = secrets.token_hex(32)
        DB.meta_set("secret_key", SECRET_KEY)

    BOOT_CHAIN_CHECK = audit_mod.verify_chain(AUDIT)
    MODEL = risk_model.RiskModel().train()
    flush()


def touch(collection, key):
    _dirty.add((collection, key))


def has_pending():
    return bool(_dirty or _pending_audit)


def flush():
    with LOCK:
        if not has_pending():
            return
        ups = []
        for coll, key in _dirty:
            doc = _COLL[coll].get(key)
            if doc is not None:
                ups.append((coll, key, doc.get("district"), doc))
        DB.flush(ups, list(_pending_audit))
        _dirty.clear()
        _pending_audit.clear()


def log_audit(actor, action, ulpin=None, details=""):
    with LOCK:
        prev = AUDIT[-1]["hash"] if AUDIT else audit_mod.GENESIS
        e = audit_mod.make_entry(prev, len(AUDIT) + 1, uuid.uuid4().hex[:8], actor, action, ulpin, details)
        AUDIT.append(e)
        _pending_audit.append((e["seq"], e))
    return e
