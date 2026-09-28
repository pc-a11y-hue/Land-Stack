"""Governance: record-update requests, updates, analytics, satellite, reports, audit, meta."""
import uuid

from flask import Blueprint, Response, jsonify, request, session

import audit as audit_mod
import config
import satellite
import security
import services
import state

bp = Blueprint("governance", __name__)


def _body():
    return request.get_json(silent=True) or {}


# ------------------------------------------------ record-update requests
REQUEST_TYPES = ["Succession / Inheritance", "Name / Detail Correction",
                 "Encumbrance Certificate Update", "Building Permission Correction"]


@bp.route("/api/parcel/<ulpin>/service-request", methods=["POST"])
@security.login_required()
def create_service_request(ulpin):
    """Officer initiates a record-update request with the citizen present. (Sales go through the deed workflow.)"""
    p = state.PARCELS.get(ulpin)
    if not p:
        return jsonify({"error": "ULPIN not found"}), 404
    err = security.require_own_district(p)
    if err:
        return err
    b = _body()
    rtype = str(b.get("type") or REQUEST_TYPES[1])
    if rtype not in REQUEST_TYPES:
        hint = " Ownership transfers by sale use the Sale Deed workflow." if "Transfer" in rtype or "Mutation" in rtype else ""
        return jsonify({"error": f"type must be one of {REQUEST_TYPES}.{hint}"}), 400
    if not b.get("citizen_present"):
        return jsonify({"error": "This action must be confirmed as performed in the citizen's presence"}), 400
    citizen, e = security.clean_name(b.get("citizen_name"))
    if e:
        return jsonify({"error": "Citizen name: " + e}), 400
    new_owner_id = None
    if rtype.startswith("Succession"):
        person = state.PERSONS.get(str(b.get("new_owner_id") or ""))
        if not person:
            return jsonify({"error": "Succession requires new_owner_id (look the heir up first)"}), 400
        if person["person_id"] == p["record_of_rights"]["owner_id"]:
            return jsonify({"error": "The heir is already the recorded owner"}), 400
        new_owner_id = person["person_id"]
    rid = uuid.uuid4().hex[:8]
    state.REQUESTS[rid] = {
        "id": rid, "ulpin": ulpin, "district": p["district"], "type": rtype,
        "initiated_by": session["username"], "initiated_by_role": session["role"],
        "citizen_name": citizen, "citizen_present_confirmed": True, "new_owner_id": new_owner_id,
        "new_owner_name": state.PERSONS[new_owner_id]["name"] if new_owner_id else None,
        "notes": security.clean_text(b.get("notes"), 500), "status": "Pending Approval",
        "created_at": services.now_iso()}
    state.touch("requests", rid)
    state.log_audit(session["username"], "RECORD_UPDATE_INITIATED", ulpin,
                    f"Request {rid} ({rtype}) initiated in presence of '{citizen}'")
    return jsonify(state.REQUESTS[rid]), 201


@bp.route("/api/requests")
@security.login_required()
def list_requests():
    """Record-update requests in the officer's own district."""
    rows = [r for r in state.REQUESTS.values() if r["district"] == session["district"]]
    return jsonify(sorted(rows, key=lambda r: r["created_at"], reverse=True))


def _own_request(rid):
    r = state.REQUESTS.get(rid)
    if not r:
        return None, (jsonify({"error": "request not found"}), 404)
    err = security.require_own_district(state.PARCELS[r["ulpin"]])
    return (r, None) if not err else (None, err)


@bp.route("/api/requests/<rid>/approve", methods=["POST"])
@security.login_required(["registration_officer"])
def approve_request(rid):
    """Registration Officer approves. A succession moves ownership (RoR, history, tax) in one step."""
    r, err = _own_request(rid)
    if err:
        return err
    if r["status"] != "Pending Approval":
        return jsonify({"error": f"request already {r['status']}"}), 400
    p = state.PARCELS[r["ulpin"]]
    if r["new_owner_id"]:
        services.apply_ownership_transfer(p, state.PERSONS[r["new_owner_id"]], f"Succession (request {rid})",
                                          transaction_type="Succession")
    r.update({"status": "Approved", "approved_by": session["username"], "approved_at": services.now_iso()})
    state.touch("requests", rid)
    state.log_audit(session["username"], "RECORD_UPDATE_APPROVED", r["ulpin"], f"Request {rid} approved")
    return jsonify({"request": r, "parcel": services.dossier(p)})


@bp.route("/api/requests/<rid>/reject", methods=["POST"])
@security.login_required(["registration_officer"])
def reject_request(rid):
    """Registration Officer rejects a pending request."""
    r, err = _own_request(rid)
    if err:
        return err
    if r["status"] != "Pending Approval":
        return jsonify({"error": f"request already {r['status']}"}), 400
    r.update({"status": "Rejected", "rejected_by": session["username"]})
    state.touch("requests", rid)
    state.log_audit(session["username"], "RECORD_UPDATE_REJECTED", r["ulpin"], f"Request {rid} rejected")
    return jsonify(r)


# ---------------------------------------------------------------- updates
@bp.route("/api/updates", methods=["POST"])
@security.login_required()
def post_update():
    """Officer posts an announcement for their district, or for one plot."""
    b = _body()
    title, message = security.clean_text(b.get("title"), 120), security.clean_text(b.get("message"), 1000)
    ulpin = security.clean_text(b.get("ulpin"), 20).upper() or None
    if not title or not message:
        return jsonify({"error": "Title and message are required"}), 400
    if ulpin:
        p = state.PARCELS.get(ulpin)
        if not p:
            return jsonify({"error": "ULPIN not found"}), 404
        err = security.require_own_district(p)
        if err:
            return err
    uid = uuid.uuid4().hex[:8]
    state.UPDATES[uid] = {"id": uid, "district": session["district"], "title": title, "message": message,
                          "ulpin": ulpin, "posted_by": session["username"], "posted_by_role": session["role"],
                          "posted_at": services.now_iso()}
    state.touch("updates", uid)
    state.log_audit(session["username"], "UPDATE_POSTED", ulpin,
                    f"Posted update '{title}' " + (f"for parcel {ulpin}" if ulpin else f"district-wide for {session['district']}"))
    return jsonify(state.UPDATES[uid]), 201


@bp.route("/api/updates")
@security.any_login_required
def list_updates():
    """Citizens: district-wide updates where they own land + updates addressed to their plots. Officers: their district's."""
    if security.is_citizen():
        owned = services.owned_parcels(session["person_id"])
        ulpins, districts = {p["ulpin"] for p in owned}, {p["district"] for p in owned}
        rows = [u for u in state.UPDATES.values()
                if (u["ulpin"] is None and u["district"] in districts) or u["ulpin"] in ulpins]
    else:
        rows = [u for u in state.UPDATES.values() if u["district"] == session["district"]]
    return jsonify(sorted(rows, key=lambda u: u["posted_at"], reverse=True))


# -------------------------------------------------------------- analytics
@bp.route("/api/anomalies")
@security.login_required()
def api_anomalies():
    """Dispute-risk view for the officer's district: rule-based score + learned model score with explanations."""
    rows = []
    for p in state.PARCELS.values():
        if p["district"] != session["district"]:
            continue
        rule, ml = services.rule_assessment(p), services.risk_assessment(p)
        if rule["issues"] or ml["risk"] >= 0.5:
            rows.append({"ulpin": p["ulpin"], "location_label": p["location_label"], "district": p["district"],
                         "ror_owner": p["record_of_rights"]["owner_name"],
                         "registration_owner": p["registration"]["latest_owner_name"],
                         "tax_owner": p["property_tax"]["assessee_name"], "issues": rule["issues"],
                         "risk_score": rule["score"], "anomalous": rule["anomalous"],
                         "ml_risk": ml["risk"], "top_factors": ml["factors"]})
    rows.sort(key=lambda r: (r["ml_risk"], r["risk_score"]), reverse=True)
    return jsonify(rows)


@bp.route("/api/ml/model-card")
@security.login_required()
def ml_card():
    """Model card for the risk model: data, metrics against the rule baseline, and limitations."""
    return jsonify(state.MODEL.card)


# -------------------------------------------------------------- satellite
def _analysis(p):
    w = p["satellite_watch"]
    return satellite.get_satellite_analysis(p["ulpin"], w["seed_unauthorized_change"], p["land_use_zoning"]["designated_use"])


@bp.route("/api/parcel/<ulpin>/satellite")
def api_parcel_satellite(ulpin):
    """Satellite change-detection result (owner or the district's officer)."""
    p = state.PARCELS.get(ulpin)
    if not p:
        return jsonify({"error": "ULPIN not found"}), 404
    if not security.has_full_access(p):
        return jsonify({"error": "Not authorized to view satellite data for this parcel"}), 403
    if not p["satellite_watch"]["under_watch"]:
        return jsonify({"under_watch": False})
    a = _analysis(p)
    return jsonify({"under_watch": True, "change_pct": a["change_pct"], "flag": a["flag"], "reason": a["reason"],
                    "before_image_url": f"/api/satellite-image/{ulpin}/before",
                    "after_image_url": f"/api/satellite-image/{ulpin}/after"})


@bp.route("/api/satellite-image/<ulpin>/<stage>")
def api_satellite_image(ulpin, stage):
    """Synthetic before/after tile."""
    p = state.PARCELS.get(ulpin)
    if not p or stage not in ("before", "after") or not p["satellite_watch"]["under_watch"]:
        return jsonify({"error": "not found"}), 404
    if not security.has_full_access(p):
        return jsonify({"error": "Not authorized"}), 403
    a = _analysis(p)
    return Response(a["before_png"] if stage == "before" else a["after_png"], mimetype="image/png")


@bp.route("/api/satellite-watchlist")
@security.login_required()
def api_satellite_watchlist():
    """Parcels under satellite watch in the officer's district."""
    out = []
    for p in state.PARCELS.values():
        if p["district"] != session["district"] or not p["satellite_watch"]["under_watch"]:
            continue
        a = _analysis(p)
        out.append({"ulpin": p["ulpin"], "location_label": p["location_label"],
                    "designated_use": p["land_use_zoning"]["designated_use"],
                    "change_pct": a["change_pct"], "flag": a["flag"], "reason": a["reason"]})
    out.sort(key=lambda x: (not x["flag"], -x["change_pct"]))
    return jsonify(out)


# ---------------------------------------------------------------- reports
@bp.route("/api/reports")
@security.login_required()
def api_reports():
    """District analytics for the logged-in officer."""
    district = session["district"]
    scoped = [p for p in state.PARCELS.values() if p["district"] == district]
    by_zoning, tax, enc, due, linked = {}, {"Paid": 0, "Due": 0}, 0, 0.0, 0
    for p in scoped:
        z = p["land_use_zoning"]["designated_use"]
        by_zoning[z] = by_zoning.get(z, 0) + 1
        tax[p["property_tax"]["status"]] += 1
        enc += p["encumbrance"]["has_encumbrance"]
        due += p["property_tax"]["annual_tax_due"] if p["property_tax"]["status"] == "Due" else 0
        linked += p["bank_link"]["linked"]
    req_status, deed_status, fees = {}, {}, 0.0
    for r in state.REQUESTS.values():
        if r["district"] == district:
            req_status[r["status"]] = req_status.get(r["status"], 0) + 1
    for d in state.DEEDS.values():
        if d["district"] == district:
            deed_status[d["status"]] = deed_status.get(d["status"], 0) + 1
            if d["status"] in ("PAID", "REGISTERED", "MUTATED"):
                fees += d["total_fees"]
    watch = [p for p in scoped if p["satellite_watch"]["under_watch"]]
    return jsonify({
        "district": district, "total_parcels": len(scoped), "by_zoning": by_zoning, "tax_status": tax,
        "total_tax_due": round(due, 2), "encumbrance_count": enc, "linked_bank_count": linked,
        "anomaly_count": sum(1 for p in scoped if services.rule_assessment(p)["anomalous"]),
        "requests_by_status": req_status, "deeds_by_status": deed_status, "fees_collected": round(fees, 2),
        "pending_mutations": sum(1 for p in scoped if p.get("pending_mutation")),
        "new_registrations": sum(1 for p in scoped if p["registered_by"] != "seed-data"),
        "satellite_watchlist_count": len(watch),
        "satellite_flagged_count": sum(1 for p in watch if _analysis(p)["flag"])})


# ------------------------------------------------------------------ audit
@bp.route("/api/audit-log")
@security.login_required()
def api_audit_log():
    """Most recent audit entries, newest first (each carries its chain hash)."""
    return jsonify(list(reversed(state.AUDIT))[:200])


@bp.route("/api/audit-log/verify")
@security.login_required()
def api_audit_verify():
    """Recompute the hash chain over the whole audit log and report whether it is intact."""
    return jsonify(audit_mod.verify_chain(state.AUDIT))


# ------------------------------------------------------------------- meta
@bp.route("/api/stats")
def api_stats():
    """Headline counts."""
    return jsonify({"total_parcels": len(state.PARCELS), "total_service_requests": len(state.REQUESTS),
                    "contexts": sorted({p["context"] for p in state.PARCELS.values()}),
                    "districts": len(config.REGIONS)})


@bp.route("/api/regions")
def api_regions():
    """The districts in the prototype."""
    return jsonify([{"context": k, "label": v["label"], "district": v["district"], "state": v["state"],
                     "center": list(v["center"])} for k, v in config.REGIONS.items()])


@bp.route("/api/health")
def api_health():
    """Liveness check."""
    return jsonify({"status": "ok", "parcels": len(state.PARCELS)})


@bp.route("/api/demo/logins")
def demo_logins():
    """Demo mode only: sample officer and citizen logins for trying the prototype. Returns 404 when demo mode is off."""
    if not config.DEMO_MODE:
        return jsonify({"error": "Not found"}), 404
    officers = [{"username": o["username"], "password": o["demo_password"], "role": o["role"],
                 "district": o["district"], "display_name": o["display_name"]}
                for o in sorted(state.OFFICERS.values(), key=lambda o: (o["district"], o["role"]))]
    citizens = []
    for p in state.PERSONS.values():
        owned = services.owned_parcels(p["person_id"])
        citizens.append({"username": p["username"], "password": p["demo_password"], "name": p["name"],
                         "person_id": p["person_id"], "district": owned[0]["district"] if owned else "—",
                         "parcels": [x["ulpin"] for x in owned]})
    citizens.sort(key=lambda c: (c["district"], c["name"]))
    return jsonify({"officers": officers, "citizens": citizens})
