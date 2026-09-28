"""Authentication: officer login (password) and citizen login (password + OTP)."""
import secrets
import time

from flask import Blueprint, jsonify, request, session
from werkzeug.security import check_password_hash

import config
import security
import services
import state

bp = Blueprint("auth", __name__)
_CHALLENGES = {}


def _body():
    return request.get_json(silent=True) or {}


def _too_many(kind, username):
    left = security.lock_remaining(kind, username)
    if left:
        return jsonify({"error": f"Too many failed attempts. Try again in {left} seconds."}), 429
    return None


@bp.route("/api/login/officer", methods=["POST"])
def login_officer():
    """Officer login with username and password."""
    b = _body()
    username, password = str(b.get("username") or "").strip(), str(b.get("password") or "")
    blocked = _too_many("officer", username)
    if blocked:
        return blocked
    user = state.OFFICERS.get(username)
    if not user or not check_password_hash(user["password_hash"], password):
        security.note_failure("officer", username)
        state.log_audit(username or "unknown", "LOGIN_FAILED", None, "Officer login failed")
        return jsonify({"error": "Invalid officer username or password"}), 401
    security.clear_failures("officer", username)
    session.clear()
    session.permanent = True
    session.update({"username": username, "role": user["role"], "region": user["region"], "district": user["district"]})
    state.log_audit(username, "LOGIN", None, f"Officer login ({user['role']}, {user['district']} district)")
    return jsonify({"username": username, "role": user["role"], "display_name": user["display_name"],
                    "district": user["district"], "region": user["region"]})


@bp.route("/api/login/citizen", methods=["POST"])
def login_citizen():
    """Citizen login step 1: username + password, then an OTP is sent to the registered mobile."""
    b = _body()
    username, password = str(b.get("username") or "").strip(), str(b.get("password") or "")
    blocked = _too_many("citizen", username)
    if blocked:
        return blocked
    person = state.PERSONS.get(state.USERNAMES.get(username))
    if not person or not check_password_hash(person["password_hash"], password):
        security.note_failure("citizen", username)
        state.log_audit(username or "unknown", "LOGIN_FAILED", None, "Citizen login failed")
        return jsonify({"error": "Invalid citizen username or password"}), 401
    security.clear_failures("citizen", username)
    cid = secrets.token_urlsafe(16)
    _CHALLENGES[cid] = {"person_id": person["person_id"], "expires": time.time() + config.OTP_TTL_SECONDS}
    otp = security.issue_otp(f"login:{cid}")
    state.log_audit(username, "LOGIN_OTP_SENT", None, f"OTP sent to {security.mask_mobile(person['mobile'])}")
    resp = {"otp_required": True, "challenge_id": cid, "mobile_masked": security.mask_mobile(person["mobile"]),
            "expires_in": config.OTP_TTL_SECONDS}
    if config.DEMO_MODE:
        resp["demo_otp"] = otp
        resp["demo_note"] = ("Demo mode: in production this OTP is sent by SMS and is never returned by the API.")
    return jsonify(resp)


@bp.route("/api/login/citizen/verify", methods=["POST"])
def login_citizen_verify():
    """Citizen login step 2: verify the OTP and start the session."""
    b = _body()
    cid, otp = str(b.get("challenge_id") or ""), b.get("otp")
    ch = _CHALLENGES.get(cid)
    if not ch or ch["expires"] < time.time():
        _CHALLENGES.pop(cid, None)
        return jsonify({"error": "Login attempt expired — start again."}), 400
    ok, reason = security.verify_otp(f"login:{cid}", otp)
    if not ok:
        if "Too many" in reason or "expired" in reason:
            _CHALLENGES.pop(cid, None)
        return jsonify({"error": reason}), 400
    _CHALLENGES.pop(cid, None)
    person = state.PERSONS[ch["person_id"]]
    session.clear()
    session.permanent = True
    session.update({"username": person["username"], "role": "citizen", "person_id": person["person_id"],
                    "owner_name": person["name"]})
    state.log_audit(person["username"], "LOGIN", None, f"Citizen login (person {person['person_id']}, OTP verified)")
    owned = services.owned_parcels(person["person_id"])
    return jsonify({"username": person["username"], "role": "citizen", "display_name": person["name"],
                    "owner_name": person["name"], "person_id": person["person_id"],
                    "owned_ulpins": [p["ulpin"] for p in owned]})


@bp.route("/api/logout", methods=["POST"])
def logout():
    """End the current session."""
    username = session.get("username")
    if username:
        state.log_audit(username, "LOGOUT", None, f"{session.get('role', 'user')} logged out")
    session.clear()
    return jsonify({"ok": True})


@bp.route("/api/me")
def me():
    """Current session profile."""
    if not session.get("username"):
        return jsonify({"logged_in": False})
    if security.is_citizen():
        owned = services.owned_parcels(session["person_id"])
        return jsonify({"logged_in": True, "username": session["username"], "role": "citizen",
                        "display_name": session["owner_name"], "owner_name": session["owner_name"],
                        "person_id": session["person_id"], "owned_ulpins": [p["ulpin"] for p in owned]})
    u = state.OFFICERS.get(session["username"], {})
    return jsonify({"logged_in": True, "username": session["username"], "role": session["role"],
                    "display_name": u.get("display_name", session["username"]),
                    "district": session.get("district"), "region": session.get("region")})
