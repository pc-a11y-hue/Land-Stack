import os
import tempfile
import unittest

from helpers import Base, Client, state, create_app, security
import config
import geo


def square_at(lat, lon, side=20.0, angle=0):
    ring = geo.square_around(lat, lon, side * side, angle)
    return [[q[1], q[0]] for q in ring[:-1]]


class TestRegistration(Base):
    def setUp(self):
        super().setUp()
        self.c.officer("reg_coimbatore")
        self.region = config.REGIONS["village"]

    def spot(self, n=0):
        return geo.offset_point(*self.region["center"], 700 + n * 60, 700)

    def reg(self, **over):
        lat, lon = self.spot(over.pop("slot", 0))
        body = {"survey_number": over.pop("survey", f"S-{len(state.PARCELS)}"), "place_name": "Kannampalayam",
                "boundary": square_at(lat, lon), "new_owner": {"name": "New Owner", "mobile": "5555509999"}}
        body.update(over)
        return self.c.post("/api/parcels/register", body)

    def test_happy_path_computes_area_and_ulpin(self):
        r = self.reg(survey="HP-1", slot=0)
        self.assertEqual(r.status_code, 201, r.get_json())
        j = r.get_json()
        p = j["parcel"]
        self.assertAlmostEqual(p["record_of_rights"]["area_sqm"], 400.0, delta=1.0)     # 20m x 20m, from the polygon
        self.assertEqual(len(p["ulpin"]), 14)
        self.assertTrue(p["ulpin"].startswith("TNCOI"))
        self.assertIn("cent", j["area"]["text"])                                        # Tamil Nadu local unit
        self.assertIn("new_citizen_account", j)
        creds = j["new_citizen_account"]
        self.c.logout()
        self.assertEqual(self.c.citizen(creds["username"], creds["password"]).status_code, 200)
        self.assertEqual(self.c.get("/api/my-properties").get_json()[0]["ulpin"], p["ulpin"])

    def test_overlap_rejected_and_reported(self):
        existing = self.parcels("Coimbatore")[0]
        ring = existing["geometry"]["coordinates"][0]
        shifted = [[q[1] + 0.00002, q[0]] for q in ring[:-1]]                            # ~2 m nudge — mostly on top
        r = self.reg(boundary=shifted, survey="OV-1")
        self.assertEqual(r.status_code, 400)
        self.assertIn(existing["ulpin"], r.get_json()["error"])
        chk = self.c.post("/api/geo/check-boundary", {"boundary": shifted}).get_json()
        self.assertFalse(chk["valid"])
        self.assertEqual(chk["overlaps"][0]["ulpin"], existing["ulpin"])

    def test_adjacent_plots_allowed(self):
        lat, lon = geo.offset_point(*self.region["center"], -700, -700)
        a = square_at(lat, lon)
        lat2, lon2 = geo.offset_point(lat, lon, 0, 20.0)                                 # shares one edge
        b = square_at(lat2, lon2)
        self.assertEqual(self.reg(boundary=a, survey="ADJ-A").status_code, 201)
        self.assertEqual(self.reg(boundary=b, survey="ADJ-B").status_code, 201)

    def test_invalid_shapes(self):
        lat, lon = self.spot(5)
        bow = [[lat, lon], [lat, lon + 0.0004], [lat + 0.0004, lon], [lat + 0.0004, lon + 0.0004]]
        self.assertEqual(self.reg(boundary=bow, survey="BOW").status_code, 400)
        self.assertEqual(self.reg(boundary=[[lat, lon], [lat, lon + 0.0001]], survey="TWO").status_code, 400)
        tiny = square_at(lat, lon, side=0.5)
        self.assertEqual(self.reg(boundary=tiny, survey="TINY").status_code, 400)
        self.assertEqual(self.reg(boundary="nonsense", survey="BAD").status_code, 400)

    def test_outside_jurisdiction_rejected(self):
        far_lat, far_lon = geo.offset_point(*self.region["center"], 120_000, 0)          # 120 km away
        r = self.reg(boundary=square_at(far_lat, far_lon), survey="FAR")
        self.assertEqual(r.status_code, 400)
        self.assertIn("jurisdiction", r.get_json()["error"])

    def test_ulpin_rules(self):
        self.assertEqual(self.reg(ulpin="KLERN0000000001", survey="U1", slot=8).status_code, 400)   # wrong district prefix
        self.assertEqual(self.reg(ulpin="TNCOI000000001", survey="U2", slot=9).status_code, 400)    # taken (also 14 chars)
        self.assertEqual(self.reg(ulpin="TNCOI1", survey="U3", slot=10).status_code, 400)          # wrong length
        self.assertEqual(self.reg(ulpin="tncoi000000777", survey="U4", slot=11).status_code, 201)  # normalised to upper case
        self.assertIn("TNCOI000000777", state.PARCELS)

    def test_survey_unique_per_district_only(self):
        self.assertEqual(self.reg(survey="DUP-1", slot=12).status_code, 201)
        self.assertEqual(self.reg(survey="dup-1", slot=13).status_code, 400)
        self.c.logout()
        self.c.officer("reg_jaipur")
        lat, lon = geo.offset_point(*config.REGIONS["desert"]["center"], 900, 900)
        r = self.c.post("/api/parcels/register", {"survey_number": "DUP-1", "place_name": "Jaipur",
                        "boundary": square_at(lat, lon), "new_owner": {"name": "Jaipur Owner", "mobile": "5555508888"}})
        self.assertEqual(r.status_code, 201, r.get_json())

    def test_hostile_names_rejected(self):
        r = self.reg(survey="XSS", slot=14, new_owner={"name": "<script>alert(1)</script>", "mobile": "5555507777"})
        self.assertEqual(r.status_code, 400)
        r = self.reg(survey="XSS2", slot=15, past_owners="<img src=x onerror=alert(1)>")
        self.assertEqual(r.status_code, 400)

    def test_history_and_existing_owner(self):
        person = next(iter(state.PERSONS.values()))
        r = self.reg(survey="EXIST", slot=16, owner_id=person["person_id"], new_owner=None, past_owners="Old Owner One, Old Owner Two")
        self.assertEqual(r.status_code, 201, r.get_json())
        p = r.get_json()["parcel"]
        self.assertEqual(p["record_of_rights"]["past_owners"], ["Old Owner One", "Old Owner Two"])
        self.assertEqual(len(p["ownership_history"]), 3)
        self.assertNotIn("new_citizen_account", r.get_json())

    def test_role_and_login_gates(self):
        self.c.logout()
        self.assertEqual(self.reg(survey="G1").status_code, 401)
        self.c.officer("rev_coimbatore")
        self.assertEqual(self.reg(survey="G2").status_code, 403)                         # revenue officer can't register
        self.c.logout()
        self.c.citizen(next(iter(state.USERNAMES)))
        self.assertEqual(self.reg(survey="G3").status_code, 401)

    def test_defaults_advance(self):
        before = self.c.get("/api/parcels/district-defaults").get_json()["ulpin_suggestion"]
        self.reg(survey="ADV", slot=17)
        after = self.c.get("/api/parcels/district-defaults").get_json()["ulpin_suggestion"]
        self.assertEqual(int(after[5:]), int(before[5:]) + 1)


class TestDeeds(Base):
    def setUp(self):
        super().setUp()
        self.c.officer("reg_coimbatore")

    def clean_parcel(self):
        for p in self.parcels("Coimbatore", lambda p: not p["encumbrance"]["has_encumbrance"]
                              and not p.get("pending_mutation")
                              and not any(d["ulpin"] == p["ulpin"] and d["status"] in ("DRAFT", "AUTHENTICATED", "PAID", "REGISTERED")
                                          for d in state.DEEDS.values())):
            return p

    def buyer_for(self, parcel):
        return next(x for x in state.PERSONS.values() if x["person_id"] != parcel["record_of_rights"]["owner_id"])

    def draft(self, parcel=None, price=1_000_000, **kw):
        parcel = parcel or self.clean_parcel()
        r = self.c.post("/api/deeds", {"ulpin": parcel["ulpin"], "buyer_id": self.buyer_for(parcel)["person_id"],
                                       "consideration": price, **kw})
        return parcel, r

    def test_full_lifecycle(self):
        parcel, r = self.draft()
        self.assertEqual(r.status_code, 201, r.get_json())
        j = r.get_json()
        d, otps = j["deed"], j["demo_otps"]
        seller_id, buyer_id = d["seller_id"], d["buyer_id"]
        self.assertEqual(d["status"], "DRAFT")
        # fees: TN illustrative 7% + 2% on max(price, guideline)
        assessed = max(1_000_000, d["guideline_value"])
        self.assertAlmostEqual(d["stamp_duty"], assessed * 0.07, places=1)
        self.assertAlmostEqual(d["registration_fee"], assessed * 0.02, places=1)
        did = d["id"]
        # gates: cannot skip ahead
        self.assertEqual(self.c.post(f"/api/deeds/{did}/payment", {"challan_no": "CH-1"}).status_code, 409)
        self.assertEqual(self.c.post(f"/api/deeds/{did}/register").status_code, 409)
        # wrong then right OTPs
        self.assertEqual(self.c.post(f"/api/deeds/{did}/authenticate", {"party": "seller", "otp": "000000"}).status_code, 400)
        self.assertEqual(self.c.post(f"/api/deeds/{did}/authenticate", {"party": "seller", "otp": otps["seller"]["otp"]}).status_code, 200)
        self.assertEqual(state.DEEDS[did]["status"], "DRAFT")                             # buyer still pending
        self.assertEqual(self.c.post(f"/api/deeds/{did}/authenticate", {"party": "buyer", "otp": otps["buyer"]["otp"]}).get_json()["status"], "AUTHENTICATED")
        self.assertEqual(self.c.post(f"/api/deeds/{did}/payment", {"challan_no": "CH-2026-001"}).get_json()["status"], "PAID")
        reg = self.c.post(f"/api/deeds/{did}/register").get_json()
        self.assertEqual(reg["status"], "REGISTERED")
        self.assertTrue(reg["deed_no"].startswith("TNCOI-"))
        # registered but NOT mutated: RoR unchanged, pending marker set, not flagged as fraud
        p = state.PARCELS[parcel["ulpin"]]
        self.assertEqual(p["record_of_rights"]["owner_id"], seller_id)
        self.assertEqual(p["pending_mutation"]["buyer_id"], buyer_id)
        rows = {r["ulpin"]: r for r in self.c.get("/api/anomalies").get_json()}
        if parcel["ulpin"] in rows:
            self.assertTrue(any("Mutation pending" in i for i in rows[parcel["ulpin"]]["issues"]))
        self.assertEqual(self.c.post(f"/api/deeds/{did}/mutate").status_code, 403)          # registration officer can't mutate
        # bank link belongs to the seller and must not carry across
        p["bank_link"].update({"linked": True, "bank_name": "SBI", "account_last4": "1234"})
        self.c.logout()
        self.c.officer("rev_chandigarh")
        self.assertEqual(self.c.post(f"/api/deeds/{did}/mutate").status_code, 403)          # wrong district
        self.c.logout()
        self.c.officer("rev_coimbatore")
        done = self.c.post(f"/api/deeds/{did}/mutate").get_json()
        self.assertEqual(done["deed"]["status"], "MUTATED")
        p = state.PARCELS[parcel["ulpin"]]
        self.assertEqual(p["record_of_rights"]["owner_id"], buyer_id)
        self.assertEqual(p["registration"]["latest_owner_name"], state.PERSONS[buyer_id]["name"])
        self.assertEqual(p["property_tax"]["assessee_name"], state.PERSONS[buyer_id]["name"])
        self.assertIn(state.PERSONS[seller_id]["name"], p["record_of_rights"]["past_owners"])
        self.assertEqual(len(p["ownership_history"]), 2)
        self.assertIsNotNone(p["ownership_history"][0]["to_date"])
        self.assertFalse(p["bank_link"]["linked"])
        self.assertNotIn("pending_mutation", p)
        # new owner sees full dossier; old owner is now just the public
        self.c.logout()
        self.c.citizen(state.PERSONS[buyer_id]["username"])
        self.assertNotIn("restricted", self.c.get(f"/api/parcel/{p['ulpin']}").get_json())
        self.assertTrue(any(x["id"] == did for x in self.c.get("/api/deeds").get_json()))
        self.c.logout()
        self.c.citizen(state.PERSONS[seller_id]["username"])
        self.assertTrue(self.c.get(f"/api/parcel/{p['ulpin']}").get_json()["restricted"])
        self.assertTrue(any(x["id"] == did for x in self.c.get("/api/deeds").get_json()))    # still sees the deed
        self.assertTrue(state.BOOT_CHAIN_CHECK["valid"])

    def test_encumbrance_blocks_without_noc(self):
        p = next(x for x in self.parcels("Coimbatore") if x["encumbrance"]["has_encumbrance"])
        _, r = self.draft(p)
        self.assertEqual(r.status_code, 409)
        self.assertIn("NOC", r.get_json()["error"])
        _, r = self.draft(p, bank_noc=True)
        self.assertEqual(r.status_code, 201)

    def test_draft_validation(self):
        p = self.clean_parcel()
        owner = p["record_of_rights"]["owner_id"]
        self.assertEqual(self.c.post("/api/deeds", {"ulpin": p["ulpin"], "buyer_id": owner, "consideration": 5}).status_code, 400)
        self.assertEqual(self.c.post("/api/deeds", {"ulpin": p["ulpin"], "buyer_id": "CID-99999999", "consideration": 5}).status_code, 400)
        b = self.buyer_for(p)["person_id"]
        self.assertEqual(self.c.post("/api/deeds", {"ulpin": p["ulpin"], "buyer_id": b, "consideration": -1}).status_code, 400)
        self.assertEqual(self.c.post("/api/deeds", {"ulpin": p["ulpin"], "buyer_id": b, "consideration": "abc"}).status_code, 400)
        self.assertEqual(self.c.post("/api/deeds", {"ulpin": "NOPE", "buyer_id": b, "consideration": 5}).status_code, 404)
        chd = self.parcels("Chandigarh")[0]
        self.assertEqual(self.c.post("/api/deeds", {"ulpin": chd["ulpin"], "buyer_id": b, "consideration": 5}).status_code, 403)

    def test_one_active_deed_per_parcel_and_cancel(self):
        p, r = self.draft()
        self.assertEqual(r.status_code, 201)
        did = r.get_json()["deed"]["id"]
        _, again = self.draft(p)
        self.assertEqual(again.status_code, 409)
        self.assertEqual(self.c.post(f"/api/deeds/{did}/cancel").get_json()["status"], "CANCELLED")
        _, third = self.draft(p)
        self.assertEqual(third.status_code, 201)

    def test_registered_deed_cannot_be_cancelled(self):
        p, r = self.draft()
        did, otps = r.get_json()["deed"]["id"], r.get_json()["demo_otps"]
        for party in ("seller", "buyer"):
            self.c.post(f"/api/deeds/{did}/authenticate", {"party": party, "otp": otps[party]["otp"]})
        self.c.post(f"/api/deeds/{did}/payment", {"challan_no": "CH-9"})
        self.c.post(f"/api/deeds/{did}/register")
        self.assertEqual(self.c.post(f"/api/deeds/{did}/cancel").status_code, 409)
        state.PARCELS[p["ulpin"]].pop("pending_mutation", None)                       # leave the fixture tidy

    def test_stale_ownership_blocks_registration(self):
        p, r = self.draft()
        did, otps = r.get_json()["deed"]["id"], r.get_json()["demo_otps"]
        for party in ("seller", "buyer"):
            self.c.post(f"/api/deeds/{did}/authenticate", {"party": party, "otp": otps[party]["otp"]})
        self.c.post(f"/api/deeds/{did}/payment", {"challan_no": "CH-8"})
        state.PARCELS[p["ulpin"]]["record_of_rights"]["owner_id"] = "CID-00000999"          # ownership changed under us
        self.assertEqual(self.c.post(f"/api/deeds/{did}/register").status_code, 409)

    def test_third_party_cannot_see_deed(self):
        p, r = self.draft()
        did = r.get_json()["deed"]["id"]
        seller, buyer = r.get_json()["deed"]["seller_id"], r.get_json()["deed"]["buyer_id"]
        other = next(x for x in state.PERSONS.values() if x["person_id"] not in (seller, buyer))
        self.c.logout()
        self.c.citizen(other["username"])
        self.assertEqual(self.c.get(f"/api/deeds/{did}").status_code, 403)
        self.assertFalse(any(x["id"] == did for x in self.c.get("/api/deeds").get_json()))
        self.assertEqual(self.c.post(f"/api/deeds/{did}/cancel").status_code, 401)        # citizens can't drive the workflow


class TestRequestsAndUpdates(Base):
    def test_succession_flow_and_gates(self):
        p = self.parcels("Ernakulam")[0]
        heir = next(x for x in state.PERSONS.values() if x["person_id"] != p["record_of_rights"]["owner_id"])
        self.c.officer("rev_ernakulam")
        base = {"citizen_name": "Heir Person", "citizen_present": True}
        self.assertEqual(self.c.post(f"/api/parcel/{p['ulpin']}/service-request", {**base, "type": "Mutation / Ownership Transfer"}).status_code, 400)
        self.assertEqual(self.c.post(f"/api/parcel/{p['ulpin']}/service-request", {**base, "type": "Succession / Inheritance"}).status_code, 400)   # heir missing
        self.assertEqual(self.c.post(f"/api/parcel/{p['ulpin']}/service-request", {"type": "Name / Detail Correction", "citizen_name": "X Y"}).status_code, 400)  # not present
        r = self.c.post(f"/api/parcel/{p['ulpin']}/service-request", {**base, "type": "Succession / Inheritance", "new_owner_id": heir["person_id"]})
        self.assertEqual(r.status_code, 201, r.get_json())
        rid = r.get_json()["id"]
        self.assertEqual(self.c.post(f"/api/requests/{rid}/approve").status_code, 403)     # revenue can't approve
        self.c.logout()
        self.c.officer("reg_coimbatore")
        self.assertEqual(self.c.post(f"/api/requests/{rid}/approve").status_code, 403)     # other district
        self.c.logout()
        self.c.officer("reg_ernakulam")
        out = self.c.post(f"/api/requests/{rid}/approve").get_json()
        self.assertEqual(out["parcel"]["record_of_rights"]["owner_id"], heir["person_id"])
        self.assertEqual(state.PARCELS[p["ulpin"]]["ownership_history"][-1]["basis"], f"Succession (request {rid})")

    def test_updates_scoping(self):
        p = self.parcels("Anantapur")[0]
        stranger = self.parcels("Jaipur")[0]
        self.c.officer("plan_anantapur")
        self.assertEqual(self.c.post("/api/updates", {"title": "District notice", "message": "Hello"}).status_code, 201)
        self.assertEqual(self.c.post("/api/updates", {"title": "Plot notice", "message": "Just you", "ulpin": p["ulpin"]}).status_code, 201)
        self.assertEqual(self.c.post("/api/updates", {"title": "Nope", "message": "x", "ulpin": stranger["ulpin"]}).status_code, 403)
        self.c.logout()
        self.c.citizen(self.owner_login(p))
        titles = {u["title"] for u in self.c.get("/api/updates").get_json()}
        self.assertEqual(titles, {"District notice", "Plot notice"})
        self.c.logout()
        self.c.citizen(self.owner_login(stranger))
        self.assertEqual(self.c.get("/api/updates").get_json(), [])


class TestAdaptersAndRisk(Base):
    def test_adapters_endpoint_and_units(self):
        ad = self.c.get("/api/adapters").get_json()
        self.assertEqual(set(ad), {"Tamil Nadu", "Chandigarh", "Andhra Pradesh", "Kerala", "Rajasthan"})
        self.assertIn("பட்டா", ad["Tamil Nadu"]["terms"]["record_of_rights"]["local"])
        for district, unit in [("Coimbatore", "cent"), ("Chandigarh", "marla"), ("Anantapur", "guntha"),
                               ("Ernakulam", "cent"), ("Jaipur", "biswa")]:
            self.c.officer({"Coimbatore": "reg_coimbatore", "Chandigarh": "reg_chandigarh", "Anantapur": "reg_anantapur",
                            "Ernakulam": "reg_ernakulam", "Jaipur": "reg_jaipur"}[district])
            p = self.parcels(district)[0]
            d = self.c.get(f"/api/parcel/{p['ulpin']}").get_json()
            self.assertIn(unit, d["derived"]["area"]["text"])
            self.assertEqual(d["derived"]["labels"]["primary_unit"], unit)
            self.assertGreater(d["derived"]["valuation"]["guideline_value"], 0)
            self.c.logout()

    def test_normalize(self):
        self.c.officer("reg_jaipur")
        r = self.c.post("/api/adapters/normalize", {"record": {"khasra_no": "45/2", "khatedar": "Ram Singh", "bigha": 1, "biswa": 10}}).get_json()
        self.assertEqual(r["canonical"]["survey_number"], "45/2")
        self.assertAlmostEqual(r["canonical"]["area_sqm"], 2529.285 + 10 * 126.46425, places=1)
        r = self.c.post("/api/adapters/normalize", {"state": "Nowhere", "record": {}})
        self.assertEqual(r.status_code, 400)

    def test_risk_model(self):
        m = state.MODEL
        base = {"area_log": 6.2}
        risky = {**base, "reg_owner_mismatch": 1, "tax_owner_mismatch": 1, "has_encumbrance": 1, "ownership_changes": 3}
        self.assertGreater(m.predict(risky)["risk"], m.predict(base)["risk"] + 0.3)
        self.assertTrue(m.predict(risky)["factors"])
        self.assertGreater(m.card["auc_test"], 0.6)
        self.assertIn("synthetic", " ".join(m.card["limitations"]).lower())

    def test_anomalies_include_ml(self):
        self.c.officer("plan_ernakulam")
        rows = self.c.get("/api/anomalies").get_json()
        self.assertTrue(rows)
        self.assertEqual([r["ml_risk"] for r in rows], sorted([r["ml_risk"] for r in rows], reverse=True))
        self.assertTrue(all("top_factors" in r for r in rows))
        self.assertEqual(self.c.get("/api/ml/model-card").status_code, 200)
        self.c.logout()
        self.assertEqual(self.c.get("/api/ml/model-card").status_code, 401)


class TestOpenAPI(Base):
    def test_spec_covers_all_routes(self):
        spec = self.c.get("/api/openapi.json").get_json()
        routes = {r.rule.replace("<", "{").replace(">", "}") for r in self.app.url_map.iter_rules()
                  if r.rule.startswith("/api/") and r.rule not in ("/api/openapi.json", "/api/docs")}
        import re
        routes = {re.sub(r"\{[^:}]+:", "{", x) for x in routes}
        self.assertEqual(set(spec["paths"]), routes)
        for path, ops in spec["paths"].items():
            for method, op in ops.items():
                self.assertTrue(op["description"], f"{method} {path} has no docstring")
                self.assertIn("x-access", op)
        reg = spec["paths"]["/api/parcels/register"]["post"]
        self.assertIn("boundary", reg["requestBody"]["content"]["application/json"]["schema"]["required"])
        self.assertEqual(spec["paths"]["/api/deeds/{deed_id}/mutate"]["post"]["x-access"], "officer: revenue_officer")


class TestZAuditChain(unittest.TestCase):
    def test_tamper_detection(self):
        db = os.path.join(tempfile.mkdtemp(), "a.db")
        app = create_app(db)
        c = Client(app)
        c.officer("reg_jaipur")
        for ulpin in list(state.PARCELS)[:3]:
            c.get(f"/api/parcel/{ulpin}")
        j = c.get("/api/audit-log/verify").get_json()
        self.assertTrue(j["valid"])
        self.assertGreater(j["entries"], 3)
        head = j["head_hash"]
        # 1. in-memory edit is caught and located
        original = state.AUDIT[2]["actor"]
        state.AUDIT[2]["actor"] = "someone-else"
        bad = c.get("/api/audit-log/verify").get_json()
        self.assertFalse(bad["valid"])
        self.assertEqual(bad["first_bad_seq"], 3)
        state.AUDIT[2]["actor"] = original
        self.assertEqual(c.get("/api/audit-log/verify").get_json()["head_hash"], head)
        # 2. deleting a middle entry is caught
        removed = state.AUDIT.pop(1)
        self.assertFalse(c.get("/api/audit-log/verify").get_json()["valid"])
        state.AUDIT.insert(1, removed)
        # 3. tampering directly in the database file is caught on the next boot
        state.DB.conn.execute("UPDATE audit SET entry = replace(entry, 'SEED', 'XXXX') WHERE seq = 1")
        create_app(db)
        self.assertFalse(state.BOOT_CHAIN_CHECK["valid"])
        self.assertEqual(state.BOOT_CHAIN_CHECK["first_bad_seq"], 1)


if __name__ == "__main__":
    unittest.main()
