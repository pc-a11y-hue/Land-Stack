"""
Browser tests: real Chromium, the real Flask server on loopback, the real front-end code.
Only Leaflet is replaced by fake_leaflet.js (the sandbox can't reach the CDN), so map RENDERING is not
exercised here — everything else (DOM, events, fetch + CSRF header, escaping, i18n, PWA) is.
Skipped automatically if Playwright / Chromium isn't available.
"""
import os
import re
import threading
import unittest

from helpers import Base, state, create_app, security
import config
import geo

try:
    from playwright.sync_api import sync_playwright
    HAVE_PW = True
except Exception:                                             # pragma: no cover
    HAVE_PW = False

HERE = os.path.dirname(os.path.abspath(__file__))
FAKE = open(os.path.join(HERE, "fake_leaflet.js"), encoding="utf-8").read()


@unittest.skipUnless(HAVE_PW, "playwright not installed")
class TestBrowser(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import tempfile
        from werkzeug.serving import make_server
        security.reset_lockouts()
        cls.app = create_app(os.path.join(tempfile.mkdtemp(), "ui.db"))
        cls.srv = make_server("127.0.0.1", 0, cls.app, threaded=True)
        cls.base = f"http://127.0.0.1:{cls.srv.server_port}"
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()
        cls.pw = sync_playwright().start()
        cls.browser = cls.pw.chromium.launch()

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.pw.stop()
        cls.srv.shutdown()

    def new_page(self, block_sw=True, **ctx_kw):
        ctx = self.browser.new_context(service_workers="block" if block_sw else "allow", **ctx_kw)
        ctx.route("https://unpkg.com/leaflet@1.9.4/dist/leaflet.js", lambda r: r.fulfill(body=FAKE, content_type="application/javascript"))
        ctx.route("https://unpkg.com/leaflet@1.9.4/dist/leaflet.css", lambda r: r.fulfill(body="", content_type="text/css"))
        page = ctx.new_page()
        page.errors = []
        page.on("pageerror", lambda e: page.errors.append(str(e)))
        page.on("console", lambda m: page.errors.append(m.text) if m.type == "error" else None)
        page.set_default_timeout(8000)
        return page

    def login(self, page, path, username, citizen=False):
        page.goto(self.base + path)
        page.wait_for_selector("#demoSel")
        pw = (state.PERSONS[state.USERNAMES[username]]["demo_password"] if citizen else state.OFFICERS[username]["demo_password"])
        page.select_option("#demoSel", value=f"{username}|{pw}")
        page.click("#lgGo")
        if citizen:
            page.wait_for_selector("#otpIn")
            self.assertRegex(page.input_value("#otpIn"), r"^\d{6}$")          # demo OTP pre-filled
            page.click("#otpGo")
        page.wait_for_selector("#userChip:not(.hidden)")
        page.wait_for_function("S.geo && S.geo.features.length > 0")

    def tab(self, page, name):
        page.click(f"#tabs button[data-tab={name}]")

    # ------------------------------------------------------------------ public
    def test_1_public_view_language_and_restricted_dossier(self):
        page = self.new_page()
        page.goto(self.base + "/")
        page.wait_for_function("S.geo && S.geo.features.length >= 92")
        self.assertEqual(page.eval_on_selector_all("#tabs button", "els => els.map(e => e.textContent)"), ["Map", "Search"])
        self.assertGreaterEqual(page.evaluate("Object.keys(S.polys).length"), 92)
        page.evaluate("S.polys[Object.keys(S.polys)[0]].fire('click')")
        page.wait_for_selector("#detailPanel .badge:has-text('Restricted view')")
        page.select_option("#langSel", "ta")
        self.assertEqual(page.inner_text("#tabs button[data-tab=map]"), "வரைபடம்")
        page.select_option("#langSel", "hi")
        self.assertEqual(page.inner_text("#tabs button[data-tab=search]"), "खोजें")
        page.select_option("#langSel", "en")
        page.click("#tabs button[data-tab=search]")
        page.fill("#searchQ", "Kumar")
        page.click("#searchBtn")
        page.wait_for_selector("#searchResults table")
        self.assertEqual(page.errors, [])

    # ------------------------------------------------------------------ citizen
    def test_2_citizen_login_otp_and_dossier(self):
        p = next(x for x in state.PARCELS.values() if x["district"] == "Coimbatore" and not x["encumbrance"]["has_encumbrance"])
        user = state.PERSONS[p["record_of_rights"]["owner_id"]]["username"]
        page = self.new_page()
        self.login(page, "/citizen", user, citizen=True)
        tabs = page.eval_on_selector_all("#tabs button", "els => els.map(e => e.dataset.tab)")
        self.assertIn("myland", tabs)
        self.assertIn("txn", tabs)
        self.assertNotIn("register", tabs)
        self.tab(page, "myland")
        page.wait_for_selector("#mylandList .card")
        self.assertIn(p["ulpin"], page.inner_text("#mylandList"))
        page.click(f"#mylandList [data-open='{p['ulpin']}']")
        page.wait_for_selector("#detailPanel:has-text('Record of Rights')")
        text = page.inner_text("#detailPanel")
        self.assertIn("Patta / Chitta", text)                  # state-adapter term
        self.assertIn("பட்டா", text)                             # local script
        self.assertIn("cent", text)                            # local unit
        self.assertIn("Ownership history", text)
        self.assertTrue(page.is_visible("#privChk"))
        page.uncheck("#privChk")
        page.wait_for_timeout(500)
        self.assertFalse(state.PARCELS[p["ulpin"]]["privacy"]["public_visible"])
        state.PARCELS[p["ulpin"]]["privacy"]["public_visible"] = True
        self.assertEqual(page.errors, [])

    def test_3_wrong_credentials_and_wrong_otp(self):
        page = self.new_page()
        page.goto(self.base + "/citizen")
        page.wait_for_selector("#lgUser")
        page.fill("#lgUser", "nobody1"); page.fill("#lgPass", "bad")
        page.click("#lgGo")
        page.wait_for_selector("#loginErr .banner.err")
        u = next(iter(state.USERNAMES))
        page.fill("#lgUser", u); page.fill("#lgPass", state.PERSONS[state.USERNAMES[u]]["demo_password"])
        page.click("#lgGo")
        page.wait_for_selector("#otpIn")
        page.fill("#otpIn", "000000")
        page.click("#otpGo")
        page.wait_for_selector("#otpErr .banner.err")
        self.assertTrue(page.is_hidden("#userChip"))

    # ------------------------------------------------------------------ officer: register, XSS, overlap
    def test_4_officer_registers_by_drawing_and_html_is_escaped(self):
        page = self.new_page()
        self.login(page, "/officer", "reg_coimbatore")
        self.tab(page, "register")
        page.wait_for_function("S.regMap && S.regDefaults")
        self.assertRegex(page.input_value("#rgUlpin"), r"^TNCOI\d{9}$")
        before = page.evaluate("S.geo.features.length")

        # 1. overlap: draw over an existing plot -> flagged, cannot submit
        existing = next(x for x in state.PARCELS.values() if x["district"] == "Coimbatore")
        for lon, lat in existing["geometry"]["coordinates"][0][:-1]:
            page.evaluate("([a, b]) => S.regMap.click(a, b)", [lat, lon])
        page.wait_for_selector("#rgCheck .chk.no:has-text('Overlaps')")
        page.check("input[name=ownMode][value=new]")
        page.fill("#rgNewName", "Ui Owner"); page.fill("#rgNewMobile", "5555512345")
        self.assertTrue(page.is_disabled("#rgSubmit"))
        page.click("#rgClear")

        # 2. valid free plot
        lat0, lon0 = geo.offset_point(*config.REGIONS["village"]["center"], 800, -800)
        ring = geo.square_around(lat0, lon0, 900)
        for lon, lat in ring[:-1]:
            page.evaluate("([a, b]) => S.regMap.click(a, b)", [lat, lon])
        page.wait_for_selector("#rgCheck .chk.ok:has-text('No overlap')")
        self.assertIn("cent", page.inner_text("#rgCheck"))                                 # area shown in Tamil Nadu units
        evil = '<img src=x onerror="window.__xss=1">Zone'
        page.fill("#rgSurvey", "UI-1"); page.fill("#rgPlace", evil)
        page.wait_for_function("!document.getElementById('rgSubmit').disabled")
        page.click("#rgSubmit")
        page.wait_for_selector("#rgResult .banner.ok")
        self.assertIn("New citizen account", page.inner_text("#rgResult"))
        page.wait_for_function(f"S.geo.features.length === {before + 1}")          # map layer refreshes after the banner
        new_ulpin = re.search(r"TNCOI\d{9}", page.inner_text("#rgResult")).group(0)
        self.assertAlmostEqual(state.PARCELS[new_ulpin]["record_of_rights"]["area_sqm"], 900.0, delta=1.0)

        # 3. the hostile place name is shown as text, never executed
        page.click("#rgView")
        page.wait_for_selector("#detailPanel:has-text('Record of Rights')")
        self.assertIn("<img src=x", page.inner_text("#detailPanel"))
        self.assertIsNone(page.evaluate("window.__xss"))
        self.assertEqual(page.errors, [])

    def test_5_sale_deed_end_to_end_through_the_ui(self):
        p = next(x for x in state.PARCELS.values() if x["district"] == "Coimbatore" and not x["encumbrance"]["has_encumbrance"]
                 and not x.get("pending_mutation") and not any(d["ulpin"] == x["ulpin"] for d in state.DEEDS.values()))
        seller_id = p["record_of_rights"]["owner_id"]
        buyer = next(x for x in state.PERSONS.values() if x["person_id"] != seller_id and x["username"].endswith("1") and len(x["username"]) < 10)
        page = self.new_page()
        self.login(page, "/officer", "reg_coimbatore")
        self.tab(page, "deeds")
        page.wait_for_selector("#deedFormBox:not(.hidden)")
        page.fill("#dUlpin", p["ulpin"]); page.fill("#dPrice", "1500000")
        page.fill("#dBuyerQ", buyer["username"])
        page.click(f"#dBuyerResults [data-pid='{buyer['person_id']}']")
        page.click("#dCreate")
        page.wait_for_selector(".sms")
        sms = page.inner_text(".sms")
        codes = {m.group(1): m.group(2) for m in re.finditer(r"(seller|buyer) \([^)]*\): (\d{6})", sms)}
        self.assertEqual(set(codes), {"seller", "buyer"})          # read each code by its label, like a human would
        # wrong OTP first
        page.fill("input[data-otp=seller]", "000000")
        page.click("button[data-act=auth][data-party=seller]")
        page.wait_for_selector("#toast:has-text('Incorrect OTP')")
        for party, otp in ((k, codes[k]) for k in ("seller", "buyer")):
            page.fill(f"input[data-otp={party}]", otp)
            page.click(f"button[data-act=auth][data-party={party}]")
            if party == "seller":
                page.wait_for_selector(".chk.ok:has-text('seller')")      # buyer is last: the card moves straight to payment
        page.wait_for_selector("input[data-challan]")
        page.fill("input[data-challan]", "CH-UI-001")
        page.click("button[data-act=pay]")
        page.wait_for_selector("button[data-act=register]")
        page.click("button[data-act=register]")
        page.wait_for_selector(".banner.info:has-text('Waiting for the Revenue Officer')")
        deed = next(d for d in state.DEEDS.values() if d["ulpin"] == p["ulpin"])
        self.assertEqual(deed["status"], "REGISTERED")
        self.assertEqual(state.PARCELS[p["ulpin"]]["record_of_rights"]["owner_id"], seller_id)     # RoR not changed yet

        # risk + audit views while here
        self.tab(page, "risk")
        page.wait_for_selector("#riskTable table")
        page.click("#modelCardBtn")
        page.wait_for_selector("#modelCard .kpi")
        self.assertIn("synthetic", page.inner_text("#modelCard").lower())
        self.tab(page, "audit")
        page.click("#auditVerifyBtn")
        page.wait_for_selector("#auditVerifyOut .banner.ok:has-text('Chain intact')")

        # revenue officer completes mutation
        page.click("#logoutBtn")
        page.wait_for_selector("#userChip.hidden", state="attached")
        page.goto(self.base + "/officer")
        page.wait_for_selector("#demoSel")
        pw = state.OFFICERS["rev_coimbatore"]["demo_password"]
        page.select_option("#demoSel", value=f"rev_coimbatore|{pw}")
        page.click("#lgGo")
        page.wait_for_selector("#userChip:not(.hidden)")
        self.tab(page, "deeds")
        page.wait_for_selector("button[data-act=mutate]")
        page.click("button[data-act=mutate]")
        page.wait_for_selector(".step.done:has-text('Mutated')")
        self.assertEqual(state.PARCELS[p["ulpin"]]["record_of_rights"]["owner_id"], buyer["person_id"])
        self.assertEqual([e for e in page.errors if '400 (BAD REQUEST)' not in e], [])   # the one deliberate wrong OTP

    def test_6_layer_toggles_change_styling(self):
        p = next(x for x in state.PARCELS.values() if x["district"] == "Jaipur" and x["encumbrance"]["has_encumbrance"])
        page = self.new_page()
        self.login(page, "/officer", "plan_jaipur")
        page.evaluate("document.getElementById('layerPanel').classList.remove('collapsed')")
        fill = lambda: page.evaluate(f"S.polys['{p['ulpin']}'].style.fillColor")
        zone_fill = fill()
        page.check("input[name=colorBy][value=encumbrance]")
        self.assertEqual(fill(), "#e5484d")                       # encumbered -> red
        self.assertNotEqual(fill(), zone_fill)
        page.check("input[name=colorBy][value=zoning]")
        self.assertEqual(fill(), zone_fill)
        page.check("#lyTax")
        self.assertIn(page.evaluate(f"S.polys['{p['ulpin']}'].style.color"), ("#c62828", "#2e7d32"))
        other = next(x for x in state.PARCELS.values() if x["district"] == "Chandigarh")
        page.check("input[name=colorBy][value=encumbrance]")
        self.assertEqual(page.evaluate(f"S.polys['{other['ulpin']}'].style.fillColor"), "#c5ccd4")   # no detail outside your district
        self.assertEqual(page.errors, [])

    # ------------------------------------------------------------------ mobile + PWA
    def test_7_mobile_layout_has_no_horizontal_overflow(self):
        page = self.new_page(viewport={"width": 390, "height": 844}, is_mobile=True, has_touch=True)
        page.goto(self.base + "/")
        page.wait_for_function("S.geo && S.geo.features.length > 0")
        self.assertTrue(page.is_visible("#layersBtn"))
        self.assertTrue(page.is_hidden("#layerPanel"))
        page.click("#layersBtn")
        self.assertTrue(page.is_visible("#layerPanel"))
        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 391)
        self.assertGreaterEqual(page.evaluate("document.getElementById('layersBtn').getBoundingClientRect().height"), 40)   # tap targets
        page.select_option("#langSel", "ml")
        self.assertLessEqual(page.evaluate("document.documentElement.scrollWidth"), 391)
        self.assertEqual(page.errors, [])

    def test_8_pwa_installable_and_offline_shell(self):
        page = self.new_page(block_sw=False)
        page.goto(self.base + "/")
        page.wait_for_function("S.geo && S.geo.features.length > 0")
        page.wait_for_function("navigator.serviceWorker.ready.then(() => true)", timeout=15000)
        self.assertTrue(page.evaluate("navigator.serviceWorker.ready.then(r => !!r.active)"))
        m = page.request.get(self.base + "/manifest.webmanifest")
        self.assertIn("manifest+json", m.headers["content-type"])
        j = m.json()
        self.assertEqual(j["display"], "standalone")
        self.assertTrue(any(i.get("purpose") == "maskable" for i in j["icons"]))
        for icon in j["icons"]:
            self.assertEqual(page.request.get(self.base + icon["src"]).status, 200)
        sw = page.request.get(self.base + "/sw.js")
        self.assertIn("javascript", sw.headers["content-type"])
        self.assertEqual(sw.headers.get("service-worker-allowed"), "/")
        # API responses must never be cached by the service worker
        page.evaluate("fetch('/api/parcels').then(r => r.json())")
        page.wait_for_timeout(300)
        cached = page.evaluate("caches.keys().then(async ks => { const out = []; for (const k of ks) { const c = await caches.open(k); (await c.keys()).forEach(r => out.push(r.url)); } return out; })")
        self.assertTrue(cached)
        self.assertFalse([u for u in cached if "/api/" in u], cached)
        # offline: the shell still opens
        page.context.set_offline(True)
        page.goto(self.base + "/citizen")
        self.assertIn("Land Stack", page.title())
        page.context.set_offline(False)


if __name__ == "__main__":
    unittest.main()
