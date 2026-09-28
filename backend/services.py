"""Domain services shared by the route modules."""
import copy
import re
from datetime import date, datetime, timezone

from werkzeug.security import generate_password_hash

import adapters
import config
import risk_model
import satellite
import security
import state


def today():
    return date.today().isoformat()


def now_iso():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _slug(text):
    return re.sub(r"[^a-z0-9]", "", text.lower())


# ---------------------------------------------------------------- persons
def create_person(name, mobile, created_by="system", person_id=None):
    """
    Creates a citizen identity with a unique person ID and login. Access to
    land is always keyed on the person ID, so two people who share a name
    are different people. Username = first name + number, password =
    number + first name (the demo credential pattern); citizen logins also
    require a one-time password.
    """
    first = _slug(name.split()[0]) or "user"
    n = 1
    while f"{first}{n}" in state.USERNAMES:
        n += 1
    username, password = f"{first}{n}", f"{n}{first}"
    if person_id is None:
        nums = [int(p[4:]) for p in state.PERSONS if p.startswith("CID-") and p[4:].isdigit()]
        person_id = f"CID-{(max(nums) + 1 if nums else 1):08d}"
    person = {
        "person_id": person_id, "name": name, "mobile": mobile, "username": username,
        "password_hash": generate_password_hash(password, method=config.HASH_METHOD),
        "demo_password": password if config.DEMO_MODE else None,
        "created_at": now_iso(), "created_by": created_by,
    }
    state.PERSONS[person_id] = person
    state.USERNAMES[username] = person_id
    state.touch("persons", person_id)
    return person, password


def public_person(p, mask=True):
    return {"person_id": p["person_id"], "name": p["name"],
            "mobile": security.mask_mobile(p["mobile"]) if mask else p["mobile"], "username": p["username"]}


def owned_parcels(person_id):
    return [p for p in state.PARCELS.values() if p["record_of_rights"]["owner_id"] == person_id]


# -------------------------------------------------------------- valuation
def valuation(parcel):
    table = config.GUIDELINE_VALUE_PER_SQM.get(parcel["state"], {})
    per_sqm = table.get(parcel["zone_code"], 0)
    area = parcel["record_of_rights"]["area_sqm"]
    return {"guideline_per_sqm": per_sqm, "guideline_value": round(per_sqm * area, 2),
            "note": config.RATES_DISCLAIMER}


# ---------------------------------------------------------------- views
def dossier(parcel):
    """Full dossier. Bank/loan data only ever reaches the owning citizen."""
    p = copy.deepcopy(parcel)
    if security.is_owning_citizen(parcel):
        p["bank_link"] = {k: v for k, v in p["bank_link"].items() if not k.startswith("_")}
    else:
        p["bank_link"] = {"restricted": True, "message": "Bank and loan details are private to the landowner only."}
    area = parcel["record_of_rights"]["area_sqm"]
    p["derived"] = {"area": adapters.area_display(area, parcel["state"]),
                    "labels": adapters.parcel_labels(parcel["state"]),
                    "valuation": valuation(parcel)}
    return p


def restricted_view(parcel):
    private = not parcel["privacy"]["public_visible"]
    hide_owner = private and not security.has_full_access(parcel)
    if hide_owner:
        msg = ("This owner has chosen not to make their land ownership publicly visible. "
               "Only the owner, or an officer in this parcel's own district, can view it.")
    else:
        msg = ("Only the owner name, survey number, and zone type are visible for this plot. "
               "Log in as its owner, or as an officer in this parcel's own district, to view full details.")
    return {"ulpin": parcel["ulpin"], "context": parcel["context"], "location_label": parcel["location_label"],
            "district": parcel["district"], "zone_code": parcel["zone_code"],
            "survey_number": parcel["survey_number"],
            "owner_name": None if hide_owner else parcel["record_of_rights"]["owner_name"],
            "is_private": private, "restricted": True, "message": msg}


# ----------------------------------------------------------- ownership
def apply_ownership_transfer(parcel, new_person, basis, deed_id=None, transaction_type="Mutation"):
    """Single place where ownership changes — RoR, history, registration and tax move together."""
    ror = parcel["record_of_rights"]
    old_name, old_id = ror["owner_name"], ror["owner_id"]
    when = today()
    if old_id != new_person["person_id"]:
        if old_name not in ror["past_owners"]:
            ror["past_owners"].append(old_name)
        hist = parcel.setdefault("ownership_history", [])
        if hist and hist[-1].get("to_date") is None:
            hist[-1]["to_date"] = when
        hist.append({"owner_id": new_person["person_id"], "owner_name": new_person["name"],
                     "from_date": when, "to_date": None, "basis": basis, "deed_id": deed_id})
        # a bank account link belongs to the previous owner — never carry it across
        parcel["bank_link"].update({"linked": False, "bank_name": None, "account_last4": None,
                                    "linked_by": None, "linked_at": None})
    ror.update({"owner_id": new_person["person_id"], "owner_name": new_person["name"], "ror_last_updated": when})
    parcel["registration"].update({"latest_owner_name": new_person["name"],
                                   "transaction_type": transaction_type, "last_transaction_date": when})
    parcel["property_tax"]["assessee_name"] = new_person["name"]
    state.touch("parcels", parcel["ulpin"])


# ------------------------------------------------------------ analytics
def satellite_flag(parcel):
    w = parcel["satellite_watch"]
    if not w["under_watch"]:
        return False
    return satellite.get_satellite_analysis(parcel["ulpin"], w["seed_unauthorized_change"],
                                            parcel["land_use_zoning"]["designated_use"])["flag"]


def rule_assessment(parcel):
    """Transparent rule baseline. A registration/RoR gap explained by a pending mutation is a normal lag."""
    ror = parcel["record_of_rights"]["owner_name"]
    reg = parcel["registration"]["latest_owner_name"]
    tax = parcel["property_tax"]["assessee_name"]
    pending = parcel.get("pending_mutation")
    issues, score, real = [], 0, False
    if ror != reg:
        if pending and reg == pending["buyer_name"]:
            issues.append(f"Mutation pending for deed {pending['deed_no']} (expected registration-to-RoR lag)")
            score += 10
        else:
            issues.append("RoR vs Registration owner mismatch")
            score += 40
            real = True
    if ror != tax:
        issues.append("RoR vs Property Tax assessee mismatch")
        score += 30
        real = True
    if parcel["encumbrance"]["has_encumbrance"] and issues:
        score += 15
    return {"issues": issues, "score": min(score, 100), "anomalous": real}


def risk_assessment(parcel):
    feats = risk_model.features_from_parcel(parcel, satellite_flag(parcel))
    pm = parcel.get("pending_mutation")
    if pm and parcel["registration"]["latest_owner_name"] == pm["buyer_name"]:
        feats["reg_owner_mismatch"] = 0
    return state.MODEL.predict(feats)


def refresh_demo_file():
    import bootstrap
    bootstrap.write_demo_logins()


# ------------------------------------------------- registration suggestions
def ulpin_prefix(region):
    import config as c
    return f"{c.STATE_CODES.get(region['state'], region['state'][:2].upper())}{region['district'][:3].upper()}"


def next_ulpin(region):
    """Next free 14-character ULPIN for a district: state(2) + district(3) + 9-digit sequence."""
    prefix = ulpin_prefix(region)
    nums = [int(u[len(prefix):]) for u in state.PARCELS if u.startswith(prefix) and u[len(prefix):].isdigit()]
    return f"{prefix}{(max(nums) + 1 if nums else 1):09d}"


def next_survey_number(region_key, district):
    prefix = region_key[:1].upper()
    nums = []
    for p in state.PARCELS.values():
        if p["district"] == district and p["survey_number"].startswith(prefix + "-"):
            tail = p["survey_number"].split("-", 1)[1]
            if tail.isdigit():
                nums.append(int(tail))
    return f"{prefix}-{(max(nums) + 1) if nums else 101}"


def next_rd_no(district):
    prefix = f"RD-{district[:3].upper()}-"
    nums = []
    for p in state.PARCELS.values():
        rd = p.get("rd_no") or ""
        if p["district"] == district and rd.startswith(prefix) and rd[len(prefix):].isdigit():
            nums.append(int(rd[len(prefix):]))
    return f"{prefix}{(max(nums) + 1) if nums else 101}"
