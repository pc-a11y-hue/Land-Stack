# Land Stack — v10 (Team GeoVault, SIH 2026)

A parcel-centric, GIS-based land-governance prototype: citizen and officer portals, state adapters,
drawn-boundary registration, a full sale-deed workflow, explainable risk analytics, and a tamper-evident audit trail.
All data is **synthetic**.

## Run it (Windows PowerShell)

```powershell
cd land-stack-prototype\backend
py -m pip install -r requirements.txt
py app.py
```

The **first start takes ~10 seconds** (it creates the database and hashes passwords). Then open:

| Page | URL |
|---|---|
| Citizen portal | http://127.0.0.1:5000/citizen |
| Officer portal | http://127.0.0.1:5000/officer |
| Public map | http://127.0.0.1:5000/ |
| API explorer | http://127.0.0.1:5000/api/docs |

You need an internet connection in the browser for the map library and map tiles.

**Logging in.** Each login screen has a **"Try a demo account"** picker. Officers use username + password.
Citizens use username + password, then a one-time code — in demo mode the code is shown on screen and pre-filled.
Every account is also listed in `backend/data/DEMO_LOGINS.txt`. Example: `reg_coimbatore` / `regcoimbatore123`.

**Reset the data:** stop the server and delete `backend/data/landstack.db`; the next start re-seeds it.
**Turn demo mode off:** set `LANDSTACK_DEMO_MODE=0` (OTPs and demo logins are then never returned by the API).

## What's in v10

| Area | What you get |
|---|---|
| Identity | Access keyed on a unique **person ID**, never a name (two different "Rajesh Kumar"s are seeded to prove it). Citizen login = password + OTP. |
| Persistence | SQLite database; data survives restarts. |
| State adapters | Local record terms, area units and language per state (Patta/Chitta, Jamabandi, Thandaper…; cent, guntha, kanal, bigha…) + an import preview that maps a state-format record to the common schema. |
| Registration | Officers **draw the plot boundary**; the server computes the area and rejects self-crossing shapes, out-of-district plots and overlaps. Live checks as you draw. |
| Sale deeds | Draft → seller & buyer OTP → fees → registered → mutated by a *separate* Revenue officer. Encumbered plots need a bank NOC. |
| Map | Base / essential / additional layer toggles; ownership-history timeline in the dossier. |
| Risk analytics | Rule score + a learned model (numpy) with per-plot explanations and a model card. **Trained on synthetic labels — see the model card.** |
| Audit | SHA-256 hash-chained log with a **Verify integrity** button. |
| Mobile | Responsive layout, installable PWA with offline shell, 5 interface languages. |
| Docs | `docs/Land_Stack_Technical_Document.docx` (20 pages) and a live OpenAPI spec. |

## Put it online
See **DEPLOY.md** — free hosting on Render in about 10 minutes, no command line (`render.yaml` is included).

## Tests

```powershell
cd land-stack-prototype
py -m unittest discover -s tests -p "test_*.py"
```
53 tests: 45 API/logic and 8 real-browser tests (the browser tests need `pip install playwright` and
`playwright install chromium`; they skip themselves if Playwright isn't installed).
The browser tests use a stand-in for the map library, so **real map rendering is not covered** — check it by eye.

## Layout

```
backend/   app.py (entry) · routes/ · services · geo · adapters · store · audit · risk_model · satellite
frontend/  index.html · app.js · i18n.js · sw.js · manifest.webmanifest · icons/
tests/     unit, workflow and browser tests
tools/     regenerate the technical document (export_doc_data.py, make_diagrams.py, build_tech_doc.js)
docs/      Land_Stack_Technical_Document.docx
```

## Be upfront about these (judges will ask)

* Everything is synthetic; guideline values and stamp-duty rates are **illustrative**.
* The risk model's labels are synthetic — its scores show the pipeline, not real-world accuracy.
* OTP, payment, bank and satellite are **simulated**; no real e-KYC.
* Translations need review by native speakers.
* No TLS / at-rest encryption yet (see Technical Document §7 and §11).
* Base map: OpenStreetMap shows disputed borders (e.g. J&K) in its neutral international style. To follow the official
  map of India, switch `MAP_TILES` in `frontend/app.js` to an authorised provider (Bhuvan / Mappls; own API key).
