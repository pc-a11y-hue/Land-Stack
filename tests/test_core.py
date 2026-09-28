import os
import unittest

from helpers import Base, Client, state, create_app, security
import geo


class TestSeedAndPersistence(Base):
    def test_seed_shape(self):
        self.assertEqual(sum(1 for p in state.PARCELS.values() if p["registered_by"] == "seed-data"), 92)
        for p in state.PARCELS.values():
            self.assertEqual(len(p["ulpin"]), 14)
            area = geo.polygon_area_sqm(p["geometry"]["coordinates"][0])
            self.assertAlmostEqual(area, p["record_of_rights"]["area_sqm"], delta=0.6)

    def test_no_seed_overlaps(self):
        ps = self.parcels("Jaipur")
        for i, a in enumerate(ps):
            for b in ps[i + 1:]:
                self.assertFalse(geo.overlap_info(a["geometry"]["coordinates"][0], b["geometry"]["coordinates"][0])["overlaps"])


class TestIdentity(Base):
    def test_homonyms_are_different_people(self):
        rk = [p for p in state.PERSONS.values() if p["name"] == "Rajesh Kumar"]
        self.assertEqual(len(rk), 2)
        self.assertNotEqual(rk[0]["person_id"], rk[1]["person_id"])
        mine = next(p for p in state.PARCELS.values() if p["record_of_rights"]["owner_id"] == rk[0]["person_id"])
        other = next(p for p in state.PARCELS.values() if p["record_of_rights"]["owner_id"] == rk[1]["person_id"])
        self.assertEqual(mine["record_of_rights"]["owner_name"], other["record_of_rights"]["owner_name"])
        self.assertEqual(self.c.citizen(rk[0]["username"]).status_code, 200)
        self.assertNotIn("restricted", self.c.get(f"/api/parcel/{mine['ulpin']}").get_json())
        self.assertTrue(self.c.get(f"/api/parcel/{other['ulpin']}").get_json()["restricted"])   # same NAME, different person

    def test_login_needs_otp(self):
        u = next(iter(state.USERNAMES))
        pw = state.PERSONS[state.USERNAMES[u]]["demo_password"]
        r = self.c.post("/api/login/citizen", {"username": u, "password": pw}).get_json()
        self.assertTrue(r["otp_required"])
        self.assertFalse(self.c.get("/api/me").get_json()["logged_in"])          # password alone is not enough
        bad = self.c.post("/api/login/citizen/verify", {"challenge_id": r["challenge_id"], "otp": "000000"})
        self.assertEqual(bad.status_code, 400)
        good = self.c.post("/api/login/citizen/verify", {"challenge_id": r["challenge_id"], "otp": r["demo_otp"]})
        self.assertEqual(good.status_code, 200)
        self.assertTrue(self.c.get("/api/me").get_json()["logged_in"])

    def test_otp_single_use_and_attempt_limit(self):
        u = next(iter(state.USERNAMES))
        pw = state.PERSONS[state.USERNAMES[u]]["demo_password"]
        r = self.c.post("/api/login/citizen", {"username": u, "password": pw}).get_json()
        for _ in range(5):
            self.c.post("/api/login/citizen/verify", {"challenge_id": r["challenge_id"], "otp": "111111"})
        late = self.c.post("/api/login/citizen/verify", {"challenge_id": r["challenge_id"], "otp": r["demo_otp"]})
        self.assertEqual(late.status_code, 400)                                    # locked out even with the right OTP

    def test_password_lockout(self):
        security.reset_lockouts()
        for _ in range(5):
            self.c.post("/api/login/officer", {"username": "plan_jaipur", "password": "wrong"})
        r = self.c.post("/api/login/officer", {"username": "plan_jaipur", "password": state.OFFICERS["plan_jaipur"]["demo_password"]})
        self.assertEqual(r.status_code, 429)
        security.reset_lockouts()

    def test_passwords_stored_hashed(self):
        for p in state.PERSONS.values():
            self.assertTrue(p["password_hash"].startswith("pbkdf2:"))
            self.assertNotEqual(p["password_hash"], p["demo_password"])


class TestAccessControl(Base):
    def test_csrf_header_required(self):
        r = self.c.raw_post("/api/login/officer", {"username": "reg_jaipur", "password": "x"})
        self.assertEqual(r.status_code, 400)

    def test_referrer_policy_lets_map_tiles_load(self):
        # OSM blocks tile requests that carry no Referer; 'same-origin' / 'no-referrer' would strip it.
        pol = self.c.get("/").headers["Referrer-Policy"]
        self.assertNotIn(pol, ("same-origin", "no-referrer", "origin-when-cross-origin-none"))
        self.assertEqual(pol, "strict-origin-when-cross-origin")

    def test_anonymous_restricted(self):
        p = self.parcels("Jaipur")[0]
        d = self.c.get(f"/api/parcel/{p['ulpin']}").get_json()
        self.assertTrue(d["restricted"])
        self.assertNotIn("record_of_rights", d)

    def test_officer_cannot_view_or_act_outside_district(self):
        self.c.officer("reg_coimbatore")
        chd = self.parcels("Chandigarh")[0]
        self.assertTrue(self.c.get(f"/api/parcel/{chd['ulpin']}").get_json()["restricted"])
        r = self.c.post(f"/api/parcel/{chd['ulpin']}/service-request",
                        {"type": "Name / Detail Correction", "citizen_name": "Some Body", "citizen_present": True})
        self.assertEqual(r.status_code, 403)
        feats = {f["properties"]["ulpin"]: f["properties"] for f in self.c.get("/api/parcels").get_json()["features"]}
        self.assertNotIn("tax_status", feats[chd["ulpin"]])

    def test_bank_details_owner_only(self):
        p = next(x for x in self.parcels("Coimbatore") if x["encumbrance"]["has_encumbrance"])
        user = self.owner_login(p)
        self.c.citizen(user)
        self.assertEqual(self.c.post(f"/api/parcel/{p['ulpin']}/link-bank",
                                     {"bank_name": "SBI", "account_number": "123456789012"}).status_code, 200)
        self.assertNotIn("123456789012", str(state.PARCELS[p["ulpin"]]))            # full number never stored
        self.assertTrue(self.c.get(f"/api/parcel/{p['ulpin']}/bank").get_json()["loan_summary"]["has_loan"])
        self.c.logout()
        self.c.officer("reg_coimbatore")
        self.assertIn(self.c.get(f"/api/parcel/{p['ulpin']}/bank").status_code, (401, 403))
        self.assertTrue(self.c.get(f"/api/parcel/{p['ulpin']}").get_json()["bank_link"]["restricted"])

    def test_privacy_toggle(self):
        p = self.parcels("Ernakulam")[3]
        name = p["record_of_rights"]["owner_name"]
        self.c.citizen(self.owner_login(p))
        self.assertEqual(self.c.post(f"/api/parcel/{p['ulpin']}/privacy", {"public_visible": False}).status_code, 200)
        self.c.logout()
        self.assertIsNone(self.c.get(f"/api/parcel/{p['ulpin']}").get_json()["owner_name"])
        feats = {f["properties"]["ulpin"]: f["properties"] for f in self.c.get("/api/parcels").get_json()["features"]}
        self.assertIsNone(feats[p["ulpin"]]["owner_name"])
        found = [r for r in self.c.get("/api/search?q=" + name.split()[0]).get_json() if r["ulpin"] == p["ulpin"] and r["owner_name"]]
        self.assertEqual(found, [])
        self.c.officer("reg_ernakulam")                                              # the district officer still sees it
        self.assertEqual(self.c.get(f"/api/parcel/{p['ulpin']}").get_json()["record_of_rights"]["owner_name"], name)

    def test_audit_officer_only(self):
        self.assertEqual(self.c.get("/api/audit-log").status_code, 401)
        self.c.citizen(next(iter(state.USERNAMES)))
        self.assertEqual(self.c.get("/api/audit-log").status_code, 401)
        self.c.logout()
        self.c.officer("rev_jaipur")
        self.assertEqual(self.c.get("/api/audit-log").status_code, 200)

    def test_analytics_officer_only_and_scoped(self):
        self.assertEqual(self.c.get("/api/anomalies").status_code, 401)
        self.c.officer("reg_jaipur")
        for row in self.c.get("/api/anomalies").get_json():
            self.assertEqual(row["district"], "Jaipur")
        self.assertEqual(self.c.get("/api/reports").get_json()["district"], "Jaipur")


class TestDemoMode(Base):
    def test_demo_logins_gated_by_flag(self):
        import config
        j = self.c.get("/api/demo/logins").get_json()
        self.assertEqual(len(j["officers"]), 15)
        self.assertTrue(all(c["password"] for c in j["citizens"]))
        config.DEMO_MODE = False
        try:
            self.assertEqual(self.c.get("/api/demo/logins").status_code, 404)
        finally:
            config.DEMO_MODE = True


class TestHostedHttps(unittest.TestCase):
    """LANDSTACK_HTTPS=1 (set on the host) must make cookies Secure, send HSTS and honour the proxy's scheme."""
    def test_https_mode(self):
        import tempfile
        os.environ["LANDSTACK_HTTPS"] = "1"
        try:
            c = Client(create_app(os.path.join(tempfile.mkdtemp(), "h.db")))
            r = c.officer("reg_jaipur", state.OFFICERS["reg_jaipur"]["demo_password"])
            self.assertEqual(r.status_code, 200)
            self.assertIn("Secure", r.headers.get("Set-Cookie", ""))
            self.assertIn("max-age", r.headers.get("Strict-Transport-Security", ""))
        finally:
            del os.environ["LANDSTACK_HTTPS"]

    def test_wsgi_entrypoint_imports(self):
        import importlib, tempfile
        os.environ["LANDSTACK_DB"] = os.path.join(tempfile.mkdtemp(), "w.db")
        import config
        config.DB_PATH = os.environ["LANDSTACK_DB"]
        m = importlib.import_module("wsgi")
        self.assertTrue(callable(m.application))


class TestZPersistence(unittest.TestCase):
    """Own database + app so restarting it cannot disturb the other tests."""
    def test_data_survives_restart(self):
        import tempfile
        db = os.path.join(tempfile.mkdtemp(), "p.db")
        app = create_app(db)
        c = Client(app)
        c.officer("reg_jaipur")
        import config
        lat, lon = geo.offset_point(*config.REGIONS["desert"]["center"], 600, 600)
        ring = geo.square_around(lat, lon, 400)
        r = c.post("/api/parcels/register", {
            "survey_number": "PERSIST-1", "place_name": "Test", "boundary": [[q[1], q[0]] for q in ring[:-1]],
            "new_owner": {"name": "Persist Person", "mobile": "5555500001"}})
        self.assertEqual(r.status_code, 201, r.get_json())
        ulpin = r.get_json()["parcel"]["ulpin"]
        create_app(db)                                   # simulate a restart on the same file
        self.assertIn(ulpin, state.PARCELS)
        self.assertEqual(state.PARCELS[ulpin]["survey_number"], "PERSIST-1")
        self.assertTrue(any(p["name"] == "Persist Person" for p in state.PERSONS.values()))
        self.assertEqual(sum(1 for e in state.AUDIT if e["action"] == "SEED"), 1)     # not re-seeded
        self.assertTrue(state.BOOT_CHAIN_CHECK["valid"])


if __name__ == "__main__":
    unittest.main()
