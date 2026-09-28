import os
import sys
import tempfile
import unittest

os.environ.setdefault("LANDSTACK_HASH", "pbkdf2:sha256:1000")     # fast hashing for tests only
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))

import security  # noqa: E402
import state  # noqa: E402
from app import create_app  # noqa: E402

HDR = {"X-Requested-With": "LandStack"}


class Client:
    """Thin wrapper over Flask's test client that adds the CSRF header to writes."""
    def __init__(self, app):
        self.c = app.test_client()

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, json=None, **kw):
        return self.c.post(url, json=json if json is not None else {}, headers=HDR, **kw)

    def raw_post(self, url, json=None):
        return self.c.post(url, json=json or {})

    def officer(self, username, password=None):
        pw = password or state.OFFICERS[username]["demo_password"]
        return self.post("/api/login/officer", {"username": username, "password": pw})

    def citizen(self, username, password=None):
        pw = password or state.PERSONS[state.USERNAMES[username]]["demo_password"]
        r = self.post("/api/login/citizen", {"username": username, "password": pw})
        if r.status_code != 200:
            return r
        j = r.get_json()
        return self.post("/api/login/citizen/verify", {"challenge_id": j["challenge_id"], "otp": j["demo_otp"]})

    def logout(self):
        return self.post("/api/logout")


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.mkdtemp()
        cls.db = os.path.join(cls.dir, "t.db")
        cls.app = create_app(cls.db)
        security.reset_lockouts()
        cls.c = Client(cls.app)

    def setUp(self):
        self.c.logout()

    # -- fixtures
    @staticmethod
    def parcels(district=None, pred=None):
        return [p for p in state.PARCELS.values()
                if (district is None or p["district"] == district) and (pred is None or pred(p))]

    @staticmethod
    def owner_login(parcel):
        return state.PERSONS[parcel["record_of_rights"]["owner_id"]]["username"]

    @staticmethod
    def square(lat, lon, side_m=20.0):
        import geo
        ring = geo.square_around(lat, lon, side_m * side_m)
        return [[p[1], p[0]] for p in ring[:-1]]

    def free_spot(self, district):
        """A spot a few hundred metres from any seeded parcel, inside the district."""
        import config
        import geo
        region = next(r for r in config.REGIONS.values() if r["district"] == district)
        return geo.offset_point(region["center"][0], region["center"][1], 600, 600)
