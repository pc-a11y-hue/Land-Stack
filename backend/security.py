"""
Security primitives: authentication decorators, access predicates,
brute-force lockout, one-time passwords, and input validation.
"""
import hashlib
import hmac
import re
import secrets
import time
from functools import wraps

from flask import session, jsonify

import config
import state

OFFICER_ROLES = ["revenue_officer", "registration_officer", "planning_officer"]


# ------------------------------------------------------------- decorators
def login_required(allowed_roles=None):
    """Officer session required; optionally restricted to specific roles."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*a, **kw):
            if not session.get("username") or session.get("role") not in OFFICER_ROLES:
                return jsonify({"error": "Officer login required"}), 401
            if allowed_roles and session.get("role") not in allowed_roles:
                return jsonify({"error": f"This action requires role: {allowed_roles}"}), 403
            return fn(*a, **kw)
        wrapper._auth = {"type": "officer", "roles": list(allowed_roles or OFFICER_ROLES)}
        return wrapper
    return decorator


def citizen_login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if session.get("role") != "citizen":
            return jsonify({"error": "Citizen login required"}), 401
        return fn(*a, **kw)
    wrapper._auth = {"type": "citizen"}
    return wrapper


def any_login_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        if not session.get("username"):
            return jsonify({"error": "Login required"}), 401
        return fn(*a, **kw)
    wrapper._auth = {"type": "any"}
    return wrapper


# ------------------------------------------------------ access predicates
def is_officer():
    return session.get("role") in OFFICER_ROLES


def is_citizen():
    return session.get("role") == "citizen"


def my_person_id():
    return session.get("person_id") if is_citizen() else None


def is_owning_citizen(parcel):
    return is_citizen() and parcel["record_of_rights"]["owner_id"] == session.get("person_id")


def has_full_access(parcel):
    """Officers: only their own district. Citizens: only plots they own (by person ID, never by name)."""
    if is_officer():
        return session.get("region") == parcel["context"]
    return is_owning_citizen(parcel)


def require_own_district(parcel):
    if session.get("region") != parcel["context"]:
        return jsonify({"error": f"You are only authorized to act on parcels in your own district "
                                 f"({session.get('district')}). This parcel is in {parcel['district']}."}), 403
    return None


# ---------------------------------------------------- brute-force lockout
_FAILS = {}


def lock_remaining(kind, username):
    rec = _FAILS.get((kind, username))
    if rec and rec["until"] > time.time():
        return int(rec["until"] - time.time()) + 1
    return 0


def note_failure(kind, username):
    rec = _FAILS.setdefault((kind, username), {"count": 0, "until": 0})
    if rec["until"] and rec["until"] <= time.time():
        rec["count"], rec["until"] = 0, 0
    rec["count"] += 1
    if rec["count"] >= config.MAX_FAILED_LOGINS:
        rec["until"] = time.time() + config.LOCKOUT_SECONDS
        rec["count"] = 0


def clear_failures(kind, username):
    _FAILS.pop((kind, username), None)


def reset_lockouts():
    _FAILS.clear()


# ------------------------------------------------------------------- OTPs
_OTPS = {}
MAX_OTP_ATTEMPTS = 5


def _otp_hash(key, otp):
    return hashlib.sha256(f"{key}:{otp}".encode()).hexdigest()


def issue_otp(key, ttl=None):
    otp = f"{secrets.randbelow(10 ** 6):06d}"
    _OTPS[key] = {"hash": _otp_hash(key, otp), "expires": time.time() + (ttl or config.OTP_TTL_SECONDS), "attempts": 0}
    return otp


def verify_otp(key, otp):
    """Returns (ok, reason). Consumes the OTP on success; locks it after too many wrong tries."""
    rec = _OTPS.get(key)
    if not rec:
        return False, "No active OTP — request a new one."
    if rec["expires"] < time.time():
        _OTPS.pop(key, None)
        return False, "OTP expired — request a new one."
    if rec["attempts"] >= MAX_OTP_ATTEMPTS:
        _OTPS.pop(key, None)
        return False, "Too many wrong attempts — request a new OTP."
    if hmac.compare_digest(rec["hash"], _otp_hash(key, str(otp or "").strip())):
        _OTPS.pop(key, None)
        return True, None
    rec["attempts"] += 1
    left = MAX_OTP_ATTEMPTS - rec["attempts"]
    return False, f"Incorrect OTP ({left} attempt{'s' if left != 1 else ''} left)."


# ------------------------------------------------------------- validation
_L = "A-Za-z\u0900-\u097F\u0B80-\u0BFF\u0C00-\u0C7F\u0D00-\u0D7F"
NAME_RE = re.compile(rf"^[{_L}][{_L} .'\-]{{1,79}}$")
MOBILE_RE = re.compile(r"^\d{10}$")
ULPIN_RE = re.compile(r"^[A-Z0-9]{14}$")


def clean_name(value):
    name = re.sub(r"\s+", " ", str(value or "")).strip()
    if not NAME_RE.match(name):
        return None, ("Name must be 2–80 characters: letters (Latin, Devanagari, Tamil, Telugu or Malayalam), "
                      "spaces, dots, apostrophes and hyphens only.")
    return name, None


def clean_text(value, max_len=500):
    text = "".join(ch for ch in str(value or "") if ch == "\n" or ch >= " ").strip()
    return text[:max_len]


def clean_mobile(value):
    m = re.sub(r"[\s\-+]", "", str(value or ""))
    m = m[-10:] if len(m) > 10 and m.startswith("91") else m
    return (m, None) if MOBILE_RE.match(m) else (None, "Mobile number must be 10 digits.")


def mask_mobile(m):
    return "XXXXXX" + (m or "")[-4:]
