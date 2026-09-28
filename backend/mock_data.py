"""
Seed dataset for the Land Stack prototype (synthetic — no real records).

Generates parcels across five districts with:
  * realistic plot sizes: each parcel's polygon has EXACTLY the recorded area
  * organic scatter (rotated, non-overlapping) rather than a rigid grid, kept
    away from the district reference point (often a junction/main road)
  * structured 14-character ULPINs:  <state 2><district 3><sequence 9>
    (illustrative — modelled on the "14-character alphanumeric" idea, not
    the official ULPIN structure)
  * ownership by PERSON ID; two different people deliberately share the name
    "Rajesh Kumar" (in different districts) to prove access never keys on names
  * ~20% of parcels seeded with owner-name mismatches across RoR /
    registration / tax so anomaly detection has something to find

Returns (parcels, persons). Credentials are created by the app, not here.
"""
import math
import random

import geo
from config import REGIONS, STATE_CODES, ZONING_TYPES, LAND_USE_RURAL, BANK_NAMES, zone_code

FIRST_NAMES = ["Ravi", "Priya", "Muthu", "Lakshmi", "Arjun", "Deepa", "Suresh",
               "Kavya", "Karthik", "Meena", "Manoj", "Anita", "Vikram", "Geeta",
               "Sanjay", "Pooja", "Ramesh", "Anjali", "Harpreet", "Simran",
               "Rajesh", "Divya", "Ajay", "Nithya", "Vinod", "Shalini"]
LAST_NAMES = ["Kumar", "Selvam", "Raman", "Iyer", "Singh", "Kaur", "Pillai",
              "Naidu", "Reddy", "Sharma", "Gowda", "Chandran", "Menon", "Nair"]

HOMONYM_NAME = "Rajesh Kumar"
HOMONYM_PARCEL_INDEXES = (5, 47)     # different districts


def make_ulpin(state, district, seq):
    return f"{STATE_CODES.get(state, state[:2].upper())}{district[:3].upper()}{seq:09d}"


def _scatter(count, radius_m, min_dist_m, rnd):
    pts, attempts = [], 0
    while len(pts) < count and attempts < count * 600:
        attempts += 1
        ang = rnd.uniform(0, 2 * math.pi)
        r = rnd.uniform(*radius_m)
        n, e = r * math.cos(ang), r * math.sin(ang)
        if all(math.hypot(n - p[0], e - p[1]) >= min_dist_m for p in pts):
            pts.append((n, e))
    if len(pts) < count:
        raise RuntimeError("could not place all seed parcels; widen the radius")
    return pts


def generate_dataset():
    random.seed(42)
    rnd_name = random.Random("names")
    parcels, persons = {}, []
    person_by_name = {}

    def new_person(name):
        p = {"person_id": f"CID-{len(persons) + 1:08d}", "name": name,
             "mobile": f"555550{len(persons) + 1:04d}"}      # deliberately not a valid Indian mobile
        persons.append(p)
        return p

    def person_for(name, force_new=False):
        if force_new or name not in person_by_name:
            p = new_person(name)
            if not force_new:
                person_by_name[name] = p
            return p
        return person_by_name[name]

    def random_name():
        while True:
            name = f"{rnd_name.choice(FIRST_NAMES)} {rnd_name.choice(LAST_NAMES)}"
            if name != HOMONYM_NAME:          # the homonym pair is deliberate; never produce it by chance
                return name

    idx = 0
    for loc_key, loc in REGIONS.items():
        lat_c, lon_c = loc["center"]
        rnd = random.Random(f"scatter-{loc_key}")
        points = _scatter(loc["count"], loc["radius_m"], loc["min_dist_m"], rnd)

        for n in range(loc["count"]):
            seq = n + 1
            north_m, east_m = points[n]
            lat, lon = geo.offset_point(lat_c, lon_c, north_m, east_m)
            rotation = rnd.uniform(-25, 25)
            area = round(rnd.uniform(*loc["area_range"]), 1)
            ulpin = make_ulpin(loc["state"], loc["district"], seq)

            ror_name = random_name()
            homonym = idx in HOMONYM_PARCEL_INDEXES
            if homonym:
                ror_name = HOMONYM_NAME
            owner = person_for(ror_name, force_new=homonym)

            mismatch = random.random() < 0.2
            reg_name = ror_name if not mismatch else random_name()
            tax_name = ror_name if not (mismatch and random.random() < 0.5) else random_name()

            has_enc = random.random() < 0.25
            zoning = random.choice(ZONING_TYPES) if loc_key != "village" else random.choice(LAND_USE_RURAL)
            tax_due = round(area * random.uniform(2.5, 9.0), 2)
            under_watch = random.random() < 0.15
            unauthorized = under_watch and random.random() < 0.5 and zoning not in ("Residential", "Commercial")
            bank = random.choice(BANK_NAMES) if has_enc else None
            reg_date = "2026-02-18" if mismatch else "2024-06-02"

            ring = geo.square_around(lat, lon, area, rotation)
            survey = f"{loc_key[:1].upper()}-{100 + seq}"
            parcels[ulpin] = {
                "ulpin": ulpin, "context": loc_key, "location_label": loc["label"],
                "district": loc["district"], "state": loc["state"],
                "survey_number": survey, "place_name": loc["label"].split(" (")[0],
                "rd_no": f"RD-{loc['district'][:3].upper()}-{100 + seq}", "landmark": None,
                "privacy": {"public_visible": True, "updated_by": None, "updated_at": None},
                "geometry": {"type": "Polygon", "coordinates": [ring]},
                "centroid": [round(lon, 7), round(lat, 7)],
                "latitude": round(lat, 6), "longitude": round(lon, 6),
                "zone_code": zone_code(zoning, loc_key),
                "registered_by": "seed-data", "registered_at": "2025-11-14",
                "record_of_rights": {
                    "owner_id": owner["person_id"], "owner_name": ror_name, "past_owners": [],
                    "khasra_or_plot_no": survey, "area_sqm": area, "ror_last_updated": "2025-11-14",
                },
                "ownership_history": [{
                    "owner_id": owner["person_id"], "owner_name": ror_name, "from_date": reg_date,
                    "to_date": None, "basis": "Seed record", "deed_id": None,
                }],
                "registration": {
                    "latest_owner_name": reg_name, "last_transaction_date": reg_date,
                    "transaction_type": "Sale Deed" if mismatch else "Inherited",
                    "registration_no": f"REG-2024-{1000 + idx}",
                },
                "building_permission": {"status": random.choice(["Approved", "Not Applicable", "Pending"]),
                                        "sanctioned_use": zoning},
                "encumbrance": {"has_encumbrance": has_enc,
                                "details": f"Bank mortgage - {bank}" if has_enc else None},
                "land_use_zoning": {"designated_use": zoning, "master_plan_ref": f"MP-{loc_key.upper()}-2025"},
                "property_tax": {"assessee_name": tax_name, "annual_tax_due": tax_due,
                                 "last_paid": "2025-04-01",
                                 "status": "Paid" if random.random() < 0.7 else "Due"},
                "utilities": {"water_connection": random.random() < 0.85,
                              "electricity_connection": random.random() < 0.9,
                              "nearest_utility_line_m": random.randint(5, 120)},
                "bank_link": {
                    "linked": False, "bank_name": None, "account_last4": None, "linked_by": None, "linked_at": None,
                    "_mock_loan": {
                        "has_loan": has_enc, "bank_name": bank,
                        "loan_amount": round(area * random.uniform(8, 22), 2) if has_enc else 0,
                        "emi": round(area * random.uniform(0.15, 0.4), 2) if has_enc else 0,
                        "status": "Active" if has_enc else "No Dues",
                        "mortgage_status": "Mortgaged" if has_enc else "Clear",
                    },
                },
                "satellite_watch": {"under_watch": under_watch, "seed_unauthorized_change": unauthorized},
                "notes": "",
            }
            idx += 1
    return parcels, persons
