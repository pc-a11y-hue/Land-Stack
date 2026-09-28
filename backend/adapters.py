"""
State adapters — the layer that lets one common ("canonical") land schema
serve states that record land very differently.

Land is a State subject in India, so states differ in record names
(Patta/Chitta vs Jamabandi vs Thandaper), area units (cent, guntha, kanal,
bigha…), field layouts and language. Rather than forcing every state into
one format, each state gets an adapter that:

  1. translates canonical field names into that state's local terms
     (in English and the local script) for display,
  2. converts areas to and from that state's local units,
  3. maps a state-format raw record INTO the canonical schema (ingestion).

Local-script terms and translations here were drafted for the prototype and
should be reviewed by native speakers / the state revenue department before
any real use. Unit sizes follow common conventions; some (notably the
bigha) genuinely vary by region within a state, so they are configurable.
"""

SQM_PER = {
    "sqm": 1.0,
    "sqft": 0.09290304,
    "hectare": 10000.0,
    "acre": 4046.8564224,
    "cent": 40.468564224,     # 1/100 acre
    "guntha": 101.17141056,   # 1/40 acre
    "kanal": 505.857,         # Punjab/Chandigarh: 20 marla
    "marla": 25.29285,
    "bigha": 2529.285,        # Rajasthan "pucca" bigha (0.625 acre) — varies regionally
    "biswa": 126.46425,       # 1/20 bigha
}

UNIT_LABELS = {
    "sqm": ("sq.m", "चौ.मी. / ச.மீ."), "acre": ("acre", None), "cent": ("cent", None),
    "guntha": ("guntha", None), "kanal": ("kanal", None), "marla": ("marla", None),
    "bigha": ("bigha", None), "biswa": ("biswa", None), "sqft": ("sq.ft", None),
}

STATE_ADAPTERS = {
    "Tamil Nadu": {
        "code": "TN", "language": "ta",
        "terms": {
            "record_of_rights": {"en": "Patta / Chitta", "local": "பட்டா / சிட்டா"},
            "survey_number": {"en": "Survey / Sub-division No.", "local": "சர்வே / உட்பிரிவு எண்"},
        },
        "units": {"acre": "ஏக்கர்", "cent": "சென்ட்"},
        "primary_unit": "cent",
        "field_map": {"patta_no": "ror_reference", "survey_no": "survey_number",
                      "sub_division": "sub_division", "owner": "owner_name", "village": "place_name"},
        "extent_map": {"extent_acre": "acre", "extent_cent": "cent"},
    },
    "Chandigarh": {
        "code": "CH", "language": "hi",
        "terms": {
            "record_of_rights": {"en": "Jamabandi", "local": "जमाबंदी"},
            "survey_number": {"en": "Khasra No.", "local": "खसरा संख्या"},
        },
        "units": {"kanal": "कनाल", "marla": "मरला"},
        "primary_unit": "marla",
        "field_map": {"jamabandi_no": "ror_reference", "khasra_no": "survey_number",
                      "malik": "owner_name", "sector": "place_name"},
        "extent_map": {"kanal": "kanal", "marla": "marla"},
    },
    "Andhra Pradesh": {
        "code": "AP", "language": "te",
        "terms": {
            "record_of_rights": {"en": "Adangal / Pahani (1-B)", "local": "అడంగల్ / పహాణీ"},
            "survey_number": {"en": "Survey No.", "local": "సర్వే నంబర్"},
        },
        "units": {"acre": "ఎకరం", "guntha": "గుంట"},
        "primary_unit": "guntha",
        "field_map": {"pahani_no": "ror_reference", "survey_no": "survey_number",
                      "pattadar": "owner_name", "village": "place_name"},
        "extent_map": {"acres": "acre", "guntas": "guntha"},
    },
    "Kerala": {
        "code": "KL", "language": "ml",
        "terms": {
            "record_of_rights": {"en": "Thandaper / Basic Tax Register", "local": "തണ്ടപ്പേർ"},
            "survey_number": {"en": "Re-survey No.", "local": "റീസർവേ നമ്പർ"},
        },
        "units": {"acre": "ഏക്കർ", "cent": "സെന്റ്"},
        "primary_unit": "cent",
        "field_map": {"thandaper_no": "ror_reference", "resurvey_no": "survey_number",
                      "owner": "owner_name", "village": "place_name"},
        "extent_map": {"extent_acre": "acre", "extent_cent": "cent"},
    },
    "Rajasthan": {
        "code": "RJ", "language": "hi",
        "terms": {
            "record_of_rights": {"en": "Jamabandi (Nakal)", "local": "जमाबंदी (नकल)"},
            "survey_number": {"en": "Khasra No.", "local": "खसरा संख्या"},
        },
        "units": {"bigha": "बीघा", "biswa": "बिस्वा"},
        "primary_unit": "biswa",
        "field_map": {"jamabandi_no": "ror_reference", "khasra_no": "survey_number",
                      "khatedar": "owner_name", "village": "place_name"},
        "extent_map": {"bigha": "bigha", "biswa": "biswa"},
    },
}

GENERIC = {
    "code": "XX", "language": "en",
    "terms": {"record_of_rights": {"en": "Record of Rights", "local": ""},
              "survey_number": {"en": "Survey / Khasra No.", "local": ""}},
    "units": {"acre": "acre", "sqm": "sq.m"}, "primary_unit": "acre",
    "field_map": {}, "extent_map": {},
}


def get_adapter(state):
    return STATE_ADAPTERS.get(state, GENERIC)


def area_in_units(sqm, state):
    """The area expressed in every unit this state uses, plus sq.m."""
    ad = get_adapter(state)
    out = []
    for unit, local in ad["units"].items():
        out.append({"unit": unit, "local": local, "value": sqm / SQM_PER[unit]})
    return out


def area_display(sqm, state):
    """Human-friendly area for display: primary local unit, the larger unit, and sq.m."""
    ad = get_adapter(state)
    values = area_in_units(sqm, state)
    primary_key = ad["primary_unit"]
    primary = next((v for v in values if v["unit"] == primary_key), values[0])
    others = [v for v in values if v["unit"] != primary["unit"]]
    parts = [f"{primary['value']:.2f} {primary['unit']}"]
    parts += [f"{v['value']:.4f} {v['unit']}" for v in others]
    parts.append(f"{sqm:,.1f} sq.m")
    return {"sqm": round(sqm, 2), "primary_unit": primary["unit"],
            "primary_value": round(primary["value"], 4), "all": values,
            "text": " · ".join(parts)}


def to_sqm(extents):
    """extents: {'acre': 1, 'cent': 12.5} -> square metres."""
    total = 0.0
    for unit, val in extents.items():
        if unit not in SQM_PER:
            raise ValueError(f"unknown unit '{unit}'")
        total += float(val) * SQM_PER[unit]
    return total


def normalize_record(state, raw):
    """
    Map a raw record in a state's own format onto the canonical schema.
    Returns the canonical fields plus a report of what was recognised,
    what wasn't, and what was converted — so an officer can review the
    mapping before anything is written.
    """
    ad = get_adapter(state)
    canonical, recognised, unknown, conversions, warnings = {}, [], [], [], []
    extents = {}
    for key, val in (raw or {}).items():
        if key in ad["field_map"]:
            canonical[ad["field_map"][key]] = val
            recognised.append(key)
        elif key in ad["extent_map"]:
            try:
                extents[ad["extent_map"][key]] = float(val)
            except (TypeError, ValueError):
                warnings.append(f"'{key}' is not a number: {val!r}")
                continue
            recognised.append(key)
        else:
            unknown.append(key)
    if extents:
        sqm = to_sqm(extents)
        canonical["area_sqm"] = round(sqm, 2)
        conversions.append({"from": extents, "to": {"sqm": round(sqm, 2)}})
    else:
        warnings.append("No extent/area fields found — area could not be derived.")
    if "survey_number" not in canonical:
        warnings.append("No survey number found in this record.")
    return {"state": state, "canonical": canonical, "recognised_fields": recognised,
            "unrecognised_fields": unknown, "conversions": conversions, "warnings": warnings}


def parcel_labels(state):
    """Terms for the dossier: canonical concept -> local names."""
    ad = get_adapter(state)
    return {"language": ad["language"], "terms": ad["terms"],
            "primary_unit": ad["primary_unit"], "units": ad["units"]}


def public_adapters():
    """JSON-safe summary of all adapters, for the API and the technical document."""
    return {
        state: {
            "code": ad["code"], "language": ad["language"], "terms": ad["terms"],
            "units": [{"unit": u, "local": lo, "sqm": SQM_PER[u]} for u, lo in ad["units"].items()],
            "primary_unit": ad["primary_unit"],
            "ingestion_fields": {**ad["field_map"], **{k: f"extent:{v}" for k, v in ad["extent_map"].items()}},
        }
        for state, ad in STATE_ADAPTERS.items()
    }
