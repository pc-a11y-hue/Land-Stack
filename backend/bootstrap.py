"""First-run seeding and the demo credentials file."""
import os

from werkzeug.security import generate_password_hash

import config
import mock_data
import state

ROLE_DEFS = [("revenue_officer", "rev", "Revenue Officer"),
             ("registration_officer", "reg", "Registration Officer"),
             ("planning_officer", "plan", "Planning Officer")]


def _slug(text):
    return "".join(ch for ch in text.lower() if ch.isalnum())


def seed():
    import services
    parcels, persons = mock_data.generate_dataset()
    for spec in sorted(persons, key=lambda p: (p["name"], p["person_id"])):
        services.create_person(spec["name"], spec["mobile"], created_by="seed", person_id=spec["person_id"])
    for ulpin, parcel in parcels.items():
        state.PARCELS[ulpin] = parcel
        state.touch("parcels", ulpin)
    for ctx, region in config.REGIONS.items():
        code = _slug(region["district"])
        for role, prefix, label in ROLE_DEFS:
            username, password = f"{prefix}_{code}", f"{prefix}{code}123"
            state.OFFICERS[username] = {
                "username": username, "role": role, "region": ctx, "district": region["district"],
                "state": region["state"], "display_name": f"{label} — {region['district']} District",
                "password_hash": generate_password_hash(password, method=config.HASH_METHOD),
                "demo_password": password if config.DEMO_MODE else None,
            }
            state.touch("officers", username)
    state.log_audit("system", "SEED", None, f"Seeded {len(parcels)} parcels, {len(persons)} people, "
                    f"{len(state.OFFICERS)} officer accounts")
    state.DB.meta_set("seeded", "1")
    state.flush()


def write_demo_logins(path=None):
    """Writes every demo login to a text file (demo mode only)."""
    if not config.DEMO_MODE:
        return None
    path = path or os.path.join(os.path.dirname(os.path.abspath(config.DB_PATH)), "DEMO_LOGINS.txt")
    lines = ["LAND STACK PROTOTYPE — DEMO LOGIN DIRECTORY",
             "(synthetic data only; regenerated on start and when accounts are created)",
             "Citizens: log in with username + password, then enter the OTP shown on screen (demo mode).",
             "", "=== OFFICER LOGINS (open /officer) ==="]
    for o in sorted(state.OFFICERS.values(), key=lambda o: (o["district"], o["role"])):
        lines.append(f"{o['username']:20s} / {str(o['demo_password']):22s} -> {o['display_name']} ({o['state']})")
    lines += ["", "=== CITIZEN LOGINS (open /citizen) ==="]
    for p in sorted(state.PERSONS.values(), key=lambda p: (p["username"][:-1].rstrip("0123456789"), int("".join(c for c in p["username"] if c.isdigit()) or 0))):
        owned = [x for x in state.PARCELS.values() if x["record_of_rights"]["owner_id"] == p["person_id"]]
        parcels = ", ".join(x["ulpin"] for x in owned) or "(no land yet)"
        lines.append(f"{p['username']:14s} / {str(p['demo_password']):12s} -> {p['name']:20s} {p['person_id']}  "
                     f"mobile {p['mobile']}  | {parcels}")
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return path
    except OSError:
        return None
