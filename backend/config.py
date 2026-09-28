"""
Central configuration: regions/districts, jurisdiction radii, illustrative
valuation and stamp-duty tables, and runtime switches.

All rates and values below are ILLUSTRATIVE placeholders for the prototype.
Real guideline values and stamp duty are set by each state government and
change over time — they must be loaded from an official notification feed
in production, never hard-coded.
"""
import os

DEMO_MODE = os.environ.get("LANDSTACK_DEMO_MODE", "1") != "0"   # shows demo OTPs and passwords in responses
DB_PATH = os.environ.get("LANDSTACK_DB", os.path.join(os.path.dirname(__file__), "data", "landstack.db"))

# ---------------------------------------------------------------------------
# Regions. "district" is the unit officer accounts are scoped to.
# Seed-data parameters are in metres so parcel sizes and spacing are realistic.
# jurisdiction_km is a circular stand-in for the real district boundary
# polygon (production would use the official boundary).
# ---------------------------------------------------------------------------
REGIONS = {
    "village": {
        "label": "Kannampalayam Village (Tamil Nadu) - Rural", "district": "Coimbatore",
        "state": "Tamil Nadu", "center": (11.1085, 77.0004), "count": 22,
        "area_range": (1500, 6000), "radius_m": (120, 480), "min_dist_m": 115, "jurisdiction_km": 45,
    },
    "ward": {
        "label": "Sector 22 (Chandigarh) - Urban", "district": "Chandigarh",
        "state": "Chandigarh", "center": (30.7333, 76.7794), "count": 18,
        "area_range": (150, 1200), "radius_m": (60, 260), "min_dist_m": 58, "jurisdiction_km": 8,
    },
    "town": {
        "label": "Anantapur Town (Andhra Pradesh) - Semi-Urban", "district": "Anantapur",
        "state": "Andhra Pradesh", "center": (14.6819, 77.6006), "count": 16,
        "area_range": (200, 1500), "radius_m": (70, 300), "min_dist_m": 65, "jurisdiction_km": 45,
    },
    "coastal": {
        "label": "Kochi (Kerala) - Coastal Urban", "district": "Ernakulam",
        "state": "Kerala", "center": (9.9312, 76.2673), "count": 18,
        "area_range": (150, 1200), "radius_m": (60, 260), "min_dist_m": 58, "jurisdiction_km": 30,
    },
    "desert": {
        "label": "Jaipur (Rajasthan) - Urban", "district": "Jaipur",
        "state": "Rajasthan", "center": (26.9124, 75.7873), "count": 18,
        "area_range": (200, 1500), "radius_m": (70, 300), "min_dist_m": 65, "jurisdiction_km": 55,
    },
}

STATE_CODES = {"Tamil Nadu": "TN", "Chandigarh": "CH", "Andhra Pradesh": "AP",
               "Kerala": "KL", "Rajasthan": "RJ"}

ZONING_TYPES = ["Residential", "Agricultural", "Commercial", "Mixed Use", "Institutional"]
LAND_USE_RURAL = ["Agricultural - Irrigated", "Agricultural - Rainfed", "Homestead", "Fallow"]
ALL_ZONING_OPTIONS = ZONING_TYPES + [z for z in LAND_USE_RURAL if z not in ZONING_TYPES]

BANK_NAMES = ["State Bank of India", "HDFC Bank", "ICICI Bank", "Punjab National Bank",
              "Canara Bank", "Axis Bank", "Bank of Baroda"]

# Illustrative guideline ("circle rate") values, INR per square metre, by state and zone code.
GUIDELINE_VALUE_PER_SQM = {
    "Tamil Nadu":     {"A": 450,  "R": 1200, "U": 7500,  "C": 15000},
    "Chandigarh":     {"A": 2500, "R": 6000, "U": 45000, "C": 90000},
    "Andhra Pradesh": {"A": 500,  "R": 1400, "U": 6500,  "C": 13000},
    "Kerala":         {"A": 900,  "R": 2500, "U": 12000, "C": 26000},
    "Rajasthan":      {"A": 400,  "R": 1100, "U": 9000,  "C": 20000},
}

# Illustrative stamp duty / registration fee, percent of assessed value.
DUTY_RATES = {
    "Tamil Nadu":     {"stamp_duty_pct": 7.0, "registration_fee_pct": 2.0},
    "Chandigarh":     {"stamp_duty_pct": 6.0, "registration_fee_pct": 1.0},
    "Andhra Pradesh": {"stamp_duty_pct": 7.5, "registration_fee_pct": 0.5},
    "Kerala":         {"stamp_duty_pct": 8.0, "registration_fee_pct": 2.0},
    "Rajasthan":      {"stamp_duty_pct": 5.0, "registration_fee_pct": 1.0},
}
RATES_DISCLAIMER = ("Illustrative prototype rates — real guideline values and duty are notified by each "
                    "state and must be loaded from an official source in production.")

# Deed workflow
DEED_STATUSES = ["DRAFT", "AUTHENTICATED", "PAID", "REGISTERED", "MUTATED", "CANCELLED"]

# Geometry limits
MIN_PARCEL_SQM = 5
MAX_PARCEL_SQM = 2_000_000


def zone_code(designated_use, context):
    """A = Agriculture, C = Commercial, U = Urban, R = Rural."""
    du = (designated_use or "").lower()
    if "agricult" in du:
        return "A"
    if du == "commercial":
        return "C"
    if context in ("ward", "town", "coastal", "desert"):
        return "U"
    return "R"

# Password hashing (stored hashes only). Tests set LANDSTACK_HASH to a fast method.
HASH_METHOD = os.environ.get("LANDSTACK_HASH", "pbkdf2:sha256:310000")
OTP_TTL_SECONDS = 300
MAX_FAILED_LOGINS = 5
LOCKOUT_SECONDS = 300
