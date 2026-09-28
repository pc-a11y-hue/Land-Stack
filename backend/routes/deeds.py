"""
Sale-deed workflow and person management.

  DRAFT ──(seller + buyer OTP)──> AUTHENTICATED ──(challan)──> PAID
        ──(Registration Officer registers)──> REGISTERED
        ──(Revenue Officer mutates RoR + tax)──> MUTATED          (or CANCELLED before REGISTERED)

Mirrors the real split of duties: the Registration department registers the
deed; the Revenue department then updates the Record of Rights (mutation).
Until mutation completes, the parcel carries a `pending_mutation` marker so
the registration/RoR gap is visible as a normal lag, not fraud.
"""
import re
import uuid

from flask import Blueprint, jsonify, request, session

import config
import security
import services
import state

bp = Blueprint("deeds", __name__)
ACTIVE = {"DRAFT", "AUTHENTICATED", "PAID", "REGISTERED"}


def _body():
    return request.get_json(silent=True) or {}


def _step(deed, status, note):
    deed["status"] = status
    deed["timeline"].append({"status": status, "at": services.now_iso(), "by": session["username"], "note": note})
    state.touch("deeds", deed["id"])


def _get_deed(deed_id):
    d = state.DEEDS.get(deed_id)
    if not d:
        return None, (jsonify({"error": "Deed not found"}), 404)
    if security.is_officer():
        if session.get("district") != d["district"]:
            return None, (jsonify({"error": "This deed belongs to another district"}), 403)
    elif security.is_citizen():
        if session.get("person_id") not in (d["seller_id"], d["buyer_id"]):
            return None, (jsonify({"error": "You are not a party to this deed"}), 403)
    else:
        return None, (jsonify({"error": "Login required"}), 401)
    return d, None


def _view(d):
    v = {k: val for k, val in d.items()}
    p = state.PARCELS.get(d["ulpin"])
    v["parcel"] = {"survey_number": p["survey_number"], "place_name": p["place_name"],
                   "zone_code": p["zone_code"], "area_sqm": p["record_of_rights"]["area_sqm"]} if p else None
    return v


def _fees(parcel, consideration):
    rates = config.DUTY_RATES.get(parcel["state"], {"stamp_duty_pct": 6.0, "registration_fee_pct": 1.0})
    guideline = services.valuation(parcel)["guideline_value"]
    assessed = max(consideration, guideline)
    stamp = round(assessed * rates["stamp_duty_pct"] / 100, 2)
    reg = round(assessed * rates["registration_fee_pct"] / 100, 2)
    return {"guideline_value": guideline, "assessed_value": assessed, "stamp_duty": stamp,
            "registration_fee": reg, "total_fees": round(stamp + reg, 2),
            "rates": {**rates, "note": config.RATES_DISCLAIMER}}


# ---------------------------------------------------------------- persons
@bp.route("/api/persons/lookup")
@security.login_required(["registration_officer"])
def persons_lookup():
    """Find a person by name, username, person ID or mobile (needed to name a buyer or owner)."""
    q = (request.args.get("q") or "").strip().lower()
    if len(q) < 2:
        return jsonify([])
    out = []
    for p in state.PERSONS.values():
        if q in p["name"].lower() or q in p["username"].lower() or q == p["person_id"].lower() or q in p["mobile"]:
            out.append({**services.public_person(p), "parcels": len(services.owned_parcels(p["person_id"]))})
    return jsonify(out[:25])


@bp.route("/api/persons", methods=["POST"])
@security.login_required(["registration_officer"])
def persons_create():
    """Create a person (identity + citizen login). The password is shown once, here."""
    b = _body()
    name, e1 = security.clean_name(b.get("name"))
    mobile, e2 = security.clean_mobile(b.get("mobile"))
    if e1 or e2:
        return jsonify({"error": e1 or e2}), 400
    person, password = services.create_person(name, mobile, created_by=session["username"])
    state.log_audit(session["username"], "PERSON_CREATED", None, f"Created person {person['person_id']}")
    services.refresh_demo_file()
    return jsonify({"person": services.public_person(person),
                    "credentials": {"username": person["username"], "password": password}}), 201


# ------------------------------------------------------------------ deeds
def _issue_otps(deed):
    demo = {}
    for party in ("seller", "buyer"):
        person = state.PERSONS[deed[f"{party}_id"]]
        otp = security.issue_otp(f"deed:{deed['id']}:{party}")
        state.log_audit(session["username"], "DEED_OTP_SENT", deed["ulpin"],
                        f"OTP for {party} sent to {security.mask_mobile(person['mobile'])}")
        if config.DEMO_MODE:
            demo[party] = {"name": person["name"], "mobile": security.mask_mobile(person["mobile"]), "otp": otp}
    return demo


@bp.route("/api/deeds", methods=["POST"])
@security.login_required(["registration_officer"])
def deeds_create():
    """Draft a sale deed at the counter: names the parcel, the buyer and the agreed price; computes duty; sends OTPs."""
    b = _body()
    parcel = state.PARCELS.get(str(b.get("ulpin") or ""))
    if not parcel:
        return jsonify({"error": "ULPIN not found"}), 404
    err = security.require_own_district(parcel)
    if err:
        return err
    buyer = state.PERSONS.get(str(b.get("buyer_id") or ""))
    if not buyer:
        return jsonify({"error": "buyer_id not found — look the buyer up (or create them) first"}), 400
    seller_id = parcel["record_of_rights"]["owner_id"]
    if seller_id == buyer["person_id"]:
        return jsonify({"error": "Seller and buyer are the same person"}), 400
    try:
        price = float(b.get("consideration"))
    except (TypeError, ValueError):
        return jsonify({"error": "consideration (sale price in INR) must be a number"}), 400
    if price <= 0:
        return jsonify({"error": "consideration must be greater than zero"}), 400
    if any(d["ulpin"] == parcel["ulpin"] and d["status"] in ACTIVE for d in state.DEEDS.values()):
        return jsonify({"error": "This parcel already has a deed in progress"}), 409
    noc = bool(b.get("bank_noc"))
    if parcel["encumbrance"]["has_encumbrance"] and not noc:
        return jsonify({"error": "This parcel has an active encumbrance/mortgage. A bank NOC is required before a "
                                 "sale deed can be drafted (set bank_noc once the NOC is on file)."}), 409

    seller = state.PERSONS[seller_id]
    deed_id = "DEED-" + uuid.uuid4().hex[:8].upper()
    deed = {
        "id": deed_id, "deed_no": None, "ulpin": parcel["ulpin"], "district": parcel["district"],
        "state": parcel["state"], "seller_id": seller_id, "seller_name": seller["name"],
        "buyer_id": buyer["person_id"], "buyer_name": buyer["name"], "consideration": round(price, 2),
        **_fees(parcel, price),
        "encumbrance_check": {"has_encumbrance": parcel["encumbrance"]["has_encumbrance"], "bank_noc": noc},
        "auth": {"seller": {"verified": False, "at": None}, "buyer": {"verified": False, "at": None}},
        "payment": None, "registered": None, "mutation": None, "status": "DRAFT",
        "timeline": [], "created_by": session["username"], "created_at": services.now_iso(),
        "notes": security.clean_text(b.get("notes"), 500),
    }
    state.DEEDS[deed_id] = deed
    _step(deed, "DRAFT", "Deed drafted at the counter")
    demo = _issue_otps(deed)
    state.log_audit(session["username"], "DEED_DRAFTED", parcel["ulpin"],
                    f"Deed {deed_id}: {seller['person_id']} -> {buyer['person_id']}, consideration {price:,.0f}")
    resp = {"deed": _view(deed)}
    if config.DEMO_MODE:
        resp["demo_otps"] = demo
        resp["demo_note"] = "Demo mode: in production each OTP is sent by SMS to that party's mobile only."
    return jsonify(resp), 201


@bp.route("/api/deeds")
@security.any_login_required
def deeds_list():
    """Officers: deeds in their own district. Citizens: deeds where they are the seller or the buyer."""
    if security.is_officer():
        rows = [d for d in state.DEEDS.values() if d["district"] == session["district"]]
    else:
        pid = session["person_id"]
        rows = [d for d in state.DEEDS.values() if pid in (d["seller_id"], d["buyer_id"])]
    return jsonify([_view(d) for d in sorted(rows, key=lambda d: d["created_at"], reverse=True)])


@bp.route("/api/deeds/<deed_id>")
@security.any_login_required
def deeds_get(deed_id):
    """One deed with its full timeline."""
    d, err = _get_deed(deed_id)
    return err if err else jsonify(_view(d))


@bp.route("/api/deeds/<deed_id>/resend-otp", methods=["POST"])
@security.login_required(["registration_officer"])
def deeds_resend(deed_id):
    """Re-issue the OTPs for parties who haven't authenticated yet."""
    d, err = _get_deed(deed_id)
    if err:
        return err
    if d["status"] != "DRAFT":
        return jsonify({"error": "OTPs can only be re-sent while the deed is in DRAFT"}), 409
    demo = {k: v for k, v in _issue_otps(d).items() if not d["auth"][k]["verified"]}
    return jsonify({"ok": True, **({"demo_otps": demo} if config.DEMO_MODE else {})})


@bp.route("/api/deeds/<deed_id>/authenticate", methods=["POST"])
@security.login_required(["registration_officer"])
def deeds_authenticate(deed_id):
    """The seller or buyer, present at the counter, reads out the OTP received on their mobile."""
    d, err = _get_deed(deed_id)
    if err:
        return err
    b = _body()
    party = b.get("party")
    if party not in ("seller", "buyer"):
        return jsonify({"error": "party must be 'seller' or 'buyer'"}), 400
    if d["status"] != "DRAFT":
        return jsonify({"error": f"Deed is {d['status']}; authentication only applies in DRAFT"}), 409
    if d["auth"][party]["verified"]:
        return jsonify({"error": f"The {party} is already authenticated"}), 409
    ok, reason = security.verify_otp(f"deed:{deed_id}:{party}", b.get("otp"))
    if not ok:
        state.log_audit(session["username"], "DEED_AUTH_FAILED", d["ulpin"], f"{party} OTP rejected on {deed_id}")
        return jsonify({"error": reason}), 400
    d["auth"][party] = {"verified": True, "at": services.now_iso()}
    state.touch("deeds", deed_id)
    state.log_audit(session["username"], "DEED_PARTY_AUTHENTICATED", d["ulpin"], f"{party} authenticated on {deed_id}")
    if d["auth"]["seller"]["verified"] and d["auth"]["buyer"]["verified"]:
        _step(d, "AUTHENTICATED", "Seller and buyer both authenticated by OTP")
    return jsonify(_view(d))


@bp.route("/api/deeds/<deed_id>/payment", methods=["POST"])
@security.login_required(["registration_officer"])
def deeds_payment(deed_id):
    """Record the stamp-duty + registration-fee challan (payment gateway is simulated)."""
    d, err = _get_deed(deed_id)
    if err:
        return err
    if d["status"] != "AUTHENTICATED":
        return jsonify({"error": f"Deed is {d['status']}; payment is recorded after both parties authenticate"}), 409
    challan = security.clean_text(_body().get("challan_no"), 40)
    if not re.match(r"^[A-Za-z0-9\-/]{3,40}$", challan):
        return jsonify({"error": "challan_no must be 3–40 letters, digits, '-' or '/'"}), 400
    d["payment"] = {"challan_no": challan, "amount": d["total_fees"], "paid_at": services.now_iso(),
                    "recorded_by": session["username"]}
    _step(d, "PAID", f"Challan {challan} recorded for INR {d['total_fees']:,.2f}")
    state.log_audit(session["username"], "DEED_PAYMENT_RECORDED", d["ulpin"], f"{deed_id} challan {challan}")
    return jsonify(_view(d))


@bp.route("/api/deeds/<deed_id>/register", methods=["POST"])
@security.login_required(["registration_officer"])
def deeds_register(deed_id):
    """Registration Officer registers the deed. Ownership in the RoR does NOT change yet — that is the Revenue
    department's mutation step."""
    d, err = _get_deed(deed_id)
    if err:
        return err
    if d["status"] != "PAID":
        return jsonify({"error": f"Deed is {d['status']}; it can be registered once fees are paid"}), 409
    p = state.PARCELS[d["ulpin"]]
    if p["record_of_rights"]["owner_id"] != d["seller_id"]:
        return jsonify({"error": "Ownership of this parcel changed after the deed was drafted — cancel and redraft"}), 409
    if p["encumbrance"]["has_encumbrance"] and not d["encumbrance_check"]["bank_noc"]:
        return jsonify({"error": "An encumbrance appeared after drafting and no bank NOC is on file"}), 409

    year = services.today()[:4]
    n = 1 + sum(1 for x in state.DEEDS.values() if x["district"] == d["district"] and x["deed_no"])
    prefix = services.ulpin_prefix(config.REGIONS[session["region"]])
    d["deed_no"] = f"{prefix}-{year}-{n:05d}"
    d["registered"] = {"by": session["username"], "at": services.now_iso(), "deed_no": d["deed_no"]}
    p["registration"].update({"latest_owner_name": d["buyer_name"], "transaction_type": "Sale Deed",
                              "registration_no": d["deed_no"], "last_transaction_date": services.today()})
    p["pending_mutation"] = {"deed_id": deed_id, "deed_no": d["deed_no"], "buyer_id": d["buyer_id"],
                             "buyer_name": d["buyer_name"], "since": services.now_iso()}
    state.touch("parcels", p["ulpin"])
    _step(d, "REGISTERED", f"Deed registered as {d['deed_no']}; mutation task raised for the Revenue department")
    state.log_audit(session["username"], "DEED_REGISTERED", d["ulpin"], f"{deed_id} registered as {d['deed_no']}")
    return jsonify(_view(d))


@bp.route("/api/deeds/<deed_id>/mutate", methods=["POST"])
@security.login_required(["revenue_officer"])
def deeds_mutate(deed_id):
    """Revenue Officer completes the mutation: RoR, ownership history and property-tax assessee move to the buyer."""
    d, err = _get_deed(deed_id)
    if err:
        return err
    if d["status"] != "REGISTERED":
        return jsonify({"error": f"Deed is {d['status']}; mutation follows registration"}), 409
    p = state.PARCELS[d["ulpin"]]
    buyer = state.PERSONS[d["buyer_id"]]
    services.apply_ownership_transfer(p, buyer, f"Sale deed {d['deed_no']}", deed_id=deed_id, transaction_type="Sale Deed")
    p.pop("pending_mutation", None)
    d["mutation"] = {"by": session["username"], "at": services.now_iso()}
    _step(d, "MUTATED", "Record of Rights, ownership history and tax assessee updated")
    state.log_audit(session["username"], "DEED_MUTATED", d["ulpin"], f"{deed_id}: RoR now {buyer['person_id']}")
    return jsonify({"deed": _view(d), "parcel_owner": buyer["name"]})


@bp.route("/api/deeds/<deed_id>/cancel", methods=["POST"])
@security.login_required(["registration_officer"])
def deeds_cancel(deed_id):
    """Cancel a deed before it is registered."""
    d, err = _get_deed(deed_id)
    if err:
        return err
    if d["status"] not in ("DRAFT", "AUTHENTICATED", "PAID"):
        return jsonify({"error": f"A {d['status']} deed can no longer be cancelled"}), 409
    note = "Cancelled" + (" (fees to be refunded)" if d["status"] == "PAID" else "")
    _step(d, "CANCELLED", note)
    state.log_audit(session["username"], "DEED_CANCELLED", d["ulpin"], f"{deed_id} cancelled")
    return jsonify(_view(d))
