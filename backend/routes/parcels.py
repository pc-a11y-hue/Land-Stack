"""Parcels: map layer, dossier, search, registration (polygon), adapters, bank link, privacy."""
from flask import Blueprint, jsonify, request, session

import adapters
import config
import geo
import security
import services
import state

bp = Blueprint("parcels", __name__)


def _body():
    return request.get_json(silent=True) or {}


def _ring(parcel):
    return parcel["geometry"]["coordinates"][0]


# --------------------------------------------------------------- map layer
@bp.route("/api/parcels")
def api_parcels():
    """GeoJSON FeatureCollection of parcels (base layer). Detail properties (essential/additional layers) are
    included only for parcels the viewer has full access to."""
    context = request.args.get("context")
    feats = []
    for p in state.PARCELS.values():
        if context and p["context"] != context:
            continue
        full = security.has_full_access(p)
        hide_owner = (not p["privacy"]["public_visible"]) and not full
        props = {"ulpin": p["ulpin"], "context": p["context"], "district": p["district"],
                 "zone_code": p["zone_code"],
                 "owner_name": None if hide_owner else p["record_of_rights"]["owner_name"],
                 "is_private": not p["privacy"]["public_visible"],
                 "is_mine": bool(full and security.is_citizen()), "detail": bool(full)}
        if full:
            props.update({"designated_use": p["land_use_zoning"]["designated_use"],
                          "has_encumbrance": p["encumbrance"]["has_encumbrance"],
                          "tax_status": p["property_tax"]["status"],
                          "under_watch": p["satellite_watch"]["under_watch"],
                          "building_status": p["building_permission"]["status"],
                          "water": p["utilities"]["water_connection"],
                          "electricity": p["utilities"]["electricity_connection"],
                          "area_sqm": p["record_of_rights"]["area_sqm"],
                          "has_pending_mutation": bool(p.get("pending_mutation"))})
        feats.append({"type": "Feature", "geometry": p["geometry"], "properties": props})
    return jsonify({"type": "FeatureCollection", "features": feats})


@bp.route("/api/parcel/<ulpin>")
def api_parcel_detail(ulpin):
    """Full dossier for the owner or the district's officer; owner-name-only view for everyone else."""
    p = state.PARCELS.get(ulpin)
    if not p:
        return jsonify({"error": "ULPIN not found"}), 404
    actor = session.get("username", "anonymous")
    if security.has_full_access(p):
        state.log_audit(actor, "VIEW_PARCEL_FULL", ulpin, "Full dossier viewed")
        return jsonify(services.dossier(p))
    state.log_audit(actor, "VIEW_PARCEL_RESTRICTED", ulpin, "Restricted (owner-name-only) view")
    return jsonify(services.restricted_view(p))


@bp.route("/api/my-properties")
@security.citizen_login_required
def api_my_properties():
    """Every parcel registered to the logged-in citizen, across all districts."""
    out = []
    for p in services.owned_parcels(session["person_id"]):
        out.append({"ulpin": p["ulpin"], "location_label": p["location_label"], "district": p["district"],
                    "zone_code": p["zone_code"], "latitude": p["latitude"], "longitude": p["longitude"],
                    "area": adapters.area_display(p["record_of_rights"]["area_sqm"], p["state"])})
    return jsonify(out)


@bp.route("/api/search")
def api_search():
    """Search by owner name, ULPIN or survey number. Private owners never surface through a name search."""
    q = (request.args.get("q") or "").strip().lower()
    if len(q) < 2:
        return jsonify([])
    out = []
    for p in state.PARCELS.values():
        full = security.has_full_access(p)
        private = not p["privacy"]["public_visible"]
        by_owner = q in p["record_of_rights"]["owner_name"].lower()
        by_id = q in p["ulpin"].lower() or q in p["survey_number"].lower()
        if not (by_owner or by_id):
            continue
        if by_owner and not by_id and private and not full:
            continue
        hide = private and not full
        out.append({"ulpin": p["ulpin"], "owner_name": None if hide else p["record_of_rights"]["owner_name"],
                    "is_private": private, "context": p["context"], "location_label": p["location_label"],
                    "district": p["district"], "zone_code": p["zone_code"], "survey_number": p["survey_number"]})
    return jsonify(out[:100])


# -------------------------------------------------------------- adapters
@bp.route("/api/adapters")
def api_adapters():
    """State adapters: local record terms, area units and ingestion field mappings."""
    return jsonify(adapters.public_adapters())


@bp.route("/api/adapters/normalize", methods=["POST"])
@security.login_required()
def api_normalize():
    """Preview mapping a raw state-format record onto the canonical schema (nothing is saved)."""
    b = _body()
    st = b.get("state") or state.OFFICERS[session["username"]]["state"]
    if st not in adapters.STATE_ADAPTERS:
        return jsonify({"error": f"No adapter for state '{st}'"}), 400
    if not isinstance(b.get("record"), dict):
        return jsonify({"error": "record (object) is required"}), 400
    return jsonify(adapters.normalize_record(st, b["record"]))


# ---------------------------------------------- registration support + live checks
@bp.route("/api/parcels/district-defaults")
@security.login_required(["registration_officer"])
def district_defaults():
    """Suggested values for the registration form — everything that repeats across a district."""
    key = session["region"]
    region = config.REGIONS[key]
    district = region["district"]
    scoped = [p for p in state.PARCELS.values() if p["district"] == district]
    counts = {}
    for p in scoped:
        if p.get("place_name"):
            counts[p["place_name"]] = counts.get(p["place_name"], 0) + 1
    place = max(counts, key=counts.get) if counts else region["label"].split(" (")[0]
    return jsonify({
        "district": district, "state": region["state"], "place_name": place,
        "rd_no_suggestion": services.next_rd_no(district),
        "survey_number_suggestion": services.next_survey_number(key, district),
        "ulpin_suggestion": services.next_ulpin(region),
        "ulpin_prefix": services.ulpin_prefix(region),
        "landmarks": sorted({p["landmark"] for p in scoped if p.get("landmark")}),
        "center_latitude": region["center"][0], "center_longitude": region["center"][1],
        "jurisdiction_km": region["jurisdiction_km"],
        "zoning_options": config.ALL_ZONING_OPTIONS,
        "adapter": adapters.parcel_labels(region["state"]),
    })


def _overlaps(ring, exclude=None):
    hits = []
    for other in state.PARCELS.values():
        if other["ulpin"] == exclude:
            continue
        info = geo.overlap_info(ring, _ring(other))
        if info["overlaps"]:
            hits.append({"ulpin": other["ulpin"], "survey_number": other["survey_number"],
                         "district": other["district"], "fraction": info["fraction"]})
    return hits


@bp.route("/api/geo/check-boundary", methods=["POST"])
@security.login_required(["registration_officer"])
def check_boundary():
    """Live validation for the drawing tool: shape, area, jurisdiction and overlap with registered plots."""
    region = config.REGIONS[session["region"]]
    ring, area, errors = geo.validate_boundary(_body().get("boundary"), config.MIN_PARCEL_SQM, config.MAX_PARCEL_SQM)
    result = {"valid": False, "area": None, "within_jurisdiction": None, "overlaps": [], "errors": errors}
    if ring is None and not area:
        return jsonify(result)
    result["area"] = adapters.area_display(area, region["state"])
    if ring is not None:
        result["within_jurisdiction"] = geo.within_radius(ring, region["center"], region["jurisdiction_km"])
        if not result["within_jurisdiction"]:
            errors.append(f"The plot lies outside {region['district']} District's jurisdiction.")
        result["overlaps"] = _overlaps(ring)
        for h in result["overlaps"]:
            errors.append(f"Overlaps registered plot {h['ulpin']} (survey {h['survey_number']}) by about "
                          f"{h['fraction'] * 100:.0f}% of the smaller plot.")
    result["valid"] = ring is not None and not errors
    return jsonify(result)


def _person_names(raw):
    items = raw if isinstance(raw, list) else [x for x in str(raw or "").split(",")]
    names = []
    for item in items:
        if not str(item).strip():
            continue
        name, err = security.clean_name(item)
        if err:
            return None, f"Past owner '{item}': {err}"
        names.append(name)
    return names, None


@bp.route("/api/parcels/register", methods=["POST"])
@security.login_required(["registration_officer"])
def register_parcel():
    """
    Register a new parcel from a DRAWN boundary. The server computes the area from the polygon, checks the shape,
    the jurisdiction and overlap with existing plots, assigns/validates the ULPIN, and links the owner by person ID.
    """
    b = _body()
    key = session["region"]
    region = config.REGIONS[key]
    district = region["district"]

    survey = security.clean_text(b.get("survey_number"), 40)
    place = security.clean_text(b.get("place_name"), 80)
    use = str(b.get("designated_use") or "Residential").strip()
    if not survey or not place:
        return jsonify({"error": "Survey number and place/location are required"}), 400
    if use not in config.ALL_ZONING_OPTIONS:
        return jsonify({"error": f"designated_use must be one of {config.ALL_ZONING_OPTIONS}"}), 400

    prefix = services.ulpin_prefix(region)
    raw_ulpin = "".join(ch for ch in str(b.get("ulpin") or "").upper() if ch.isalnum())
    ulpin = raw_ulpin or services.next_ulpin(region)
    if not security.ULPIN_RE.match(ulpin):
        return jsonify({"error": "ULPIN must be exactly 14 letters/digits"}), 400
    if not ulpin.startswith(prefix):
        return jsonify({"error": f"A {district} ULPIN must start with {prefix} (state + district code)"}), 400
    if ulpin in state.PARCELS:
        return jsonify({"error": f"ULPIN {ulpin} is already registered to another plot"}), 400

    dup = next((p for p in state.PARCELS.values()
                if p["district"] == district and p["survey_number"].strip().lower() == survey.lower()), None)
    if dup:
        return jsonify({"error": f"Survey number '{survey}' is already registered in {district} District "
                                 f"(ULPIN {dup['ulpin']}). Survey numbers must be unique within a district."}), 400

    ring, area, errs = geo.validate_boundary(b.get("boundary"), config.MIN_PARCEL_SQM, config.MAX_PARCEL_SQM)
    if ring is None:
        return jsonify({"error": " ".join(errs) or "Invalid boundary"}), 400
    if not geo.within_radius(ring, region["center"], region["jurisdiction_km"]):
        return jsonify({"error": f"The plot lies outside {district} District's jurisdiction."}), 400
    hits = _overlaps(ring)
    if hits:
        h = hits[0]
        return jsonify({"error": f"The boundary overlaps registered plot {h['ulpin']} (survey {h['survey_number']}) "
                                 f"by about {h['fraction'] * 100:.0f}% — adjust it so plots don't overlap.",
                        "overlaps": hits}), 400

    past, err = _person_names(b.get("past_owners"))
    if err:
        return jsonify({"error": err}), 400

    person, creds = None, None
    if b.get("owner_id"):
        person = state.PERSONS.get(str(b["owner_id"]))
        if not person:
            return jsonify({"error": "owner_id not found — look the person up first or create them"}), 400
    elif isinstance(b.get("new_owner"), dict):
        name, e1 = security.clean_name(b["new_owner"].get("name"))
        mobile, e2 = security.clean_mobile(b["new_owner"].get("mobile"))
        if e1 or e2:
            return jsonify({"error": e1 or e2}), 400
    else:
        return jsonify({"error": "Provide owner_id (existing person) or new_owner {name, mobile}"}), 400

    if person is None:                       # all validation passed — now mutate
        person, password = services.create_person(name, mobile, created_by=session["username"])
        creds = {"username": person["username"], "password": password}

    lat, lon = geo.polygon_centroid(ring)
    now, officer = services.today(), session["username"]
    history = [{"owner_id": None, "owner_name": n, "from_date": None, "to_date": None,
                "basis": "Prior owner recorded at registration", "deed_id": None} for n in past]
    history.append({"owner_id": person["person_id"], "owner_name": person["name"], "from_date": now,
                    "to_date": None, "basis": "Fresh registration", "deed_id": None})
    parcel = {
        "ulpin": ulpin, "context": key, "location_label": region["label"], "district": district,
        "state": region["state"], "survey_number": survey, "place_name": place,
        "rd_no": security.clean_text(b.get("rd_no"), 40) or None,
        "landmark": security.clean_text(b.get("landmark"), 120) or None,
        "privacy": {"public_visible": True, "updated_by": None, "updated_at": None},
        "geometry": {"type": "Polygon", "coordinates": [ring]},
        "centroid": [round(lon, 7), round(lat, 7)], "latitude": round(lat, 6), "longitude": round(lon, 6),
        "zone_code": config.zone_code(use, key), "registered_by": officer, "registered_at": now,
        "record_of_rights": {"owner_id": person["person_id"], "owner_name": person["name"], "past_owners": past,
                             "khasra_or_plot_no": survey, "area_sqm": round(area, 1), "ror_last_updated": now},
        "ownership_history": history,
        "registration": {"latest_owner_name": person["name"], "last_transaction_date": now,
                         "transaction_type": "Fresh Registration",
                         "registration_no": f"REG-{now[:4]}-{ulpin[-6:]}"},
        "building_permission": {"status": "Not Applicable", "sanctioned_use": use},
        "encumbrance": {"has_encumbrance": False, "details": None},
        "land_use_zoning": {"designated_use": use, "master_plan_ref": f"MP-{key.upper()}-2025"},
        "property_tax": {"assessee_name": person["name"], "annual_tax_due": round(area * 4.5, 2),
                         "last_paid": None, "status": "Due"},
        "utilities": {"water_connection": False, "electricity_connection": False, "nearest_utility_line_m": None},
        "bank_link": {"linked": False, "bank_name": None, "account_last4": None, "linked_by": None, "linked_at": None,
                      "_mock_loan": {"has_loan": False, "bank_name": None, "loan_amount": 0, "emi": 0,
                                     "status": "No Dues", "mortgage_status": "Clear"}},
        "satellite_watch": {"under_watch": False, "seed_unauthorized_change": False},
        "notes": security.clean_text(b.get("notes"), 500),
    }
    state.PARCELS[ulpin] = parcel
    state.touch("parcels", ulpin)
    state.log_audit(officer, "PARCEL_REGISTERED", ulpin,
                    f"Registered by {officer}: survey {survey}, {place}, {area:.1f} sq.m (computed from drawn boundary), "
                    f"owner {person['person_id']}")
    if creds:
        services.refresh_demo_file()

    resp = {"parcel": services.dossier(parcel), "area": adapters.area_display(area, region["state"]),
            "person": services.public_person(person)}
    if creds:
        resp["new_citizen_account"] = {**creds, "person_id": person["person_id"], "mobile": person["mobile"],
                                       "note": "Share these with the landowner now. Citizen logins also need an OTP "
                                               "sent to the registered mobile."}
    return jsonify(resp), 201


# ------------------------------------------------- bank link (owner only)
@bp.route("/api/parcel/<ulpin>/bank")
@security.citizen_login_required
def api_parcel_bank(ulpin):
    """Bank/loan details — visible to the owning citizen ONLY (not even the district officer)."""
    p = state.PARCELS.get(ulpin)
    if not p:
        return jsonify({"error": "ULPIN not found"}), 404
    if not security.is_owning_citizen(p):
        return jsonify({"error": "Bank and loan details are private to the landowner only"}), 403
    link = p["bank_link"]
    if not link["linked"]:
        return jsonify({"linked": False})
    m = link["_mock_loan"]
    return jsonify({"linked": True, "bank_name": link["bank_name"], "account_last4": link["account_last4"],
                    "linked_at": link["linked_at"],
                    "loan_summary": {"has_loan": m["has_loan"], "bank_name": m["bank_name"] or link["bank_name"],
                                     "loan_amount": m["loan_amount"], "emi": m["emi"], "status": m["status"],
                                     "mortgage_status": m["mortgage_status"]}})


@bp.route("/api/parcel/<ulpin>/link-bank", methods=["POST"])
@security.citizen_login_required
def api_link_bank(ulpin):
    """Owner links a bank account (simulated verification). Only the last 4 digits are ever stored."""
    p = state.PARCELS.get(ulpin)
    if not p:
        return jsonify({"error": "ULPIN not found"}), 404
    if not security.is_owning_citizen(p):
        return jsonify({"error": "You can only link a bank account to a plot you own"}), 403
    b = _body()
    bank = security.clean_text(b.get("bank_name"), 60)
    number = "".join(ch for ch in str(b.get("account_number") or "") if ch.isdigit())
    if not bank or len(number) < 6:
        return jsonify({"error": "Bank name and a valid account number are required"}), 400
    p["bank_link"].update({"linked": True, "bank_name": bank, "account_last4": number[-4:],
                           "linked_by": session["username"], "linked_at": services.now_iso()})
    state.touch("parcels", ulpin)
    state.log_audit(session["username"], "BANK_ACCOUNT_LINKED", ulpin,
                    f"Linked {bank} account ending {number[-4:]} to check loan/mortgage status")
    return api_parcel_bank(ulpin)


@bp.route("/api/parcel/<ulpin>/unlink-bank", methods=["POST"])
@security.citizen_login_required
def api_unlink_bank(ulpin):
    """Owner removes the bank link."""
    p = state.PARCELS.get(ulpin)
    if not p:
        return jsonify({"error": "ULPIN not found"}), 404
    if not security.is_owning_citizen(p):
        return jsonify({"error": "You can only unlink a bank account from a plot you own"}), 403
    p["bank_link"].update({"linked": False, "bank_name": None, "account_last4": None,
                           "linked_by": None, "linked_at": None})
    state.touch("parcels", ulpin)
    state.log_audit(session["username"], "BANK_ACCOUNT_UNLINKED", ulpin, "Bank account unlinked")
    return jsonify({"linked": False})


@bp.route("/api/parcel/<ulpin>/privacy", methods=["POST"])
@security.citizen_login_required
def api_set_privacy(ulpin):
    """Owner chooses whether their name is publicly shown against this plot."""
    p = state.PARCELS.get(ulpin)
    if not p:
        return jsonify({"error": "ULPIN not found"}), 404
    if not security.is_owning_citizen(p):
        return jsonify({"error": "You can only change privacy settings for a plot you own"}), 403
    b = _body()
    if not isinstance(b.get("public_visible"), bool):
        return jsonify({"error": "public_visible (true/false) is required"}), 400
    p["privacy"].update({"public_visible": b["public_visible"], "updated_by": session["username"],
                         "updated_at": services.now_iso()})
    state.touch("parcels", ulpin)
    state.log_audit(session["username"], "PRIVACY_SETTING_CHANGED", ulpin,
                    f"Public visibility set to {b['public_visible']}")
    return jsonify(p["privacy"])
