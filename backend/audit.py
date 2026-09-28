"""
Tamper-evident audit log: each entry embeds the SHA-256 of the previous
entry, so editing, reordering or deleting any past entry breaks every hash
after it and is caught by verify_chain().

What this does and does not give you:
  * It makes silent edits to history DETECTABLE. It does not make them
    impossible — whoever controls the database could recompute the whole
    chain. The fix in production is to periodically anchor the latest
    ("head") hash somewhere the database admin cannot rewrite (a separate
    write-once log, an NIC-hosted service, or a public ledger).
  * Deleting the newest entries is invisible unless the head hash has been
    anchored externally — verify_chain() returns the head hash for that.
"""
import hashlib
import json
from datetime import datetime, timezone

GENESIS = "0" * 64
FIELDS = ("seq", "id", "timestamp", "actor", "action", "ulpin", "details")


def _canonical(entry):
    return json.dumps({k: entry.get(k) for k in FIELDS}, sort_keys=True, separators=(",", ":"))


def entry_hash(prev_hash, entry):
    return hashlib.sha256((prev_hash + _canonical(entry)).encode("utf-8")).hexdigest()


def make_entry(prev_hash, seq, entry_id, actor, action, ulpin=None, details="", timestamp=None):
    entry = {
        "seq": seq, "id": entry_id,
        "timestamp": timestamp or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "actor": actor, "action": action, "ulpin": ulpin, "details": details,
        "prev_hash": prev_hash,
    }
    entry["hash"] = entry_hash(prev_hash, entry)
    return entry


def verify_chain(entries):
    """Walk the chain in order; report the first broken link, if any."""
    prev = GENESIS
    expected_seq = 1
    for e in entries:
        if e.get("seq") != expected_seq:
            return {"valid": False, "entries": len(entries), "first_bad_seq": e.get("seq"),
                    "reason": f"sequence gap: expected {expected_seq}, found {e.get('seq')} (an entry was removed or reordered)",
                    "head_hash": prev}
        if e.get("prev_hash") != prev:
            return {"valid": False, "entries": len(entries), "first_bad_seq": e["seq"],
                    "reason": "prev_hash does not match the preceding entry", "head_hash": prev}
        if entry_hash(prev, e) != e.get("hash"):
            return {"valid": False, "entries": len(entries), "first_bad_seq": e["seq"],
                    "reason": "entry contents do not match their hash (the entry was modified)", "head_hash": prev}
        prev = e["hash"]
        expected_seq += 1
    return {"valid": True, "entries": len(entries), "first_bad_seq": None, "reason": None, "head_hash": prev}
