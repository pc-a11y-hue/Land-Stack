// Builds "Land Stack — Standard Technical Document" (.docx) from live application data.
// Run:  python tools/export_doc_data.py && python tools/make_diagrams.py && node tools/build_tech_doc.js
const fs = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, Table, TableRow, TableCell, WidthType, ShadingType,
  BorderStyle, AlignmentType, ImageRun, Footer, Header, PageNumber, TableOfContents, LevelFormat, PageBreak
} = require('docx');

const D = JSON.parse(fs.readFileSync(path.join(__dirname, 'doc_data.json'), 'utf8'));
const DIA = p => fs.readFileSync(path.join(__dirname, 'diagrams', p));
const OUT = process.argv[2] || path.join(__dirname, 'Land_Stack_Technical_Document.docx');

const BLUE = '0F4C81', AMBER = 'E08A00', GREY = 'EEF1F5', MUTED = '5B6B7B';
const W = 9638; // A4 (11906) minus 2 x 1134 margins, in DXA

// ---------- helpers ----------
function runs(text, base = {}) {
  // **bold** and `code` inline markup
  const out = [];
  text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(Boolean).forEach(part => {
    if (part.startsWith('**')) out.push(new TextRun({ ...base, text: part.slice(2, -2), bold: true }));
    else if (part.startsWith('`')) out.push(new TextRun({ ...base, text: part.slice(1, -1), font: 'Consolas', size: (base.size || 21) - 2 }));
    else out.push(new TextRun({ ...base, text: part }));
  });
  return out;
}
const P = (text, opts = {}) => new Paragraph({ spacing: { after: 110, line: 288 }, ...opts, children: runs(text, opts.run || {}) });
const H1 = text => new Paragraph({ heading: HeadingLevel.HEADING_1, pageBreakBefore: true, children: [new TextRun(text)] });
const H1nb = text => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(text)] });
const H2 = text => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(text)] });
const H3 = text => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(text)] });
const bullets = items => items.map(t => new Paragraph({ numbering: { reference: 'bul', level: 0 }, spacing: { after: 60, line: 276 }, children: runs(t) }));
const note = (label, text, color = AMBER) => new Paragraph({
  spacing: { before: 100, after: 160, line: 276 }, indent: { left: 200 },
  border: { left: { style: BorderStyle.SINGLE, size: 24, color, space: 8 } },
  shading: { type: ShadingType.CLEAR, fill: 'F7F9FB' },
  children: [new TextRun({ text: label + ' ', bold: true, color }), ...runs(text)]
});
const caption = t => new Paragraph({ alignment: AlignmentType.CENTER, spacing: { after: 200 }, children: [new TextRun({ text: t, italics: true, size: 18, color: MUTED })] });
const img = (file, wPx, hPx) => new Paragraph({ alignment: AlignmentType.CENTER, spacing: { before: 120, after: 60 }, children: [new ImageRun({ type: 'png', data: DIA(file), transformation: { width: wPx, height: hPx }, altText: { title: file, description: file, name: file } })] });

const thin = { style: BorderStyle.SINGLE, size: 4, color: 'C9D2DC' };
const borders = { top: thin, bottom: thin, left: thin, right: thin };
function table(headers, rows, widths, opts = {}) {
  const total = widths.reduce((a, b) => a + b, 0);
  const cell = (txt, w, head, shade) => new TableCell({
    width: { size: w, type: WidthType.DXA }, borders,
    shading: head ? { type: ShadingType.CLEAR, fill: BLUE } : shade ? { type: ShadingType.CLEAR, fill: 'F7F9FB' } : undefined,
    margins: { top: 60, bottom: 60, left: 100, right: 100 },
    children: String(txt).split('\n').map(line => new Paragraph({ spacing: { after: 20 }, children: runs(line, head ? { bold: true, color: 'FFFFFF', size: opts.size || 18 } : { size: opts.size || 18 }) }))
  });
  return new Table({
    width: { size: total, type: WidthType.DXA }, columnWidths: widths,
    rows: [new TableRow({ tableHeader: true, children: headers.map((h, i) => cell(h, widths[i], true)) }),
      ...rows.map((r, ri) => new TableRow({ cantSplit: true, children: r.map((c, i) => cell(c, widths[i], false, ri % 2 === 1)) }))]
  });
}
const gap = () => new Paragraph({ spacing: { after: 120 }, children: [] });

// ---------- content ----------
const c = [];

// Cover
c.push(new Paragraph({ spacing: { before: 2200, after: 120 }, children: [new TextRun({ text: 'LAND STACK', bold: true, size: 64, color: BLUE })] }));
c.push(new Paragraph({ spacing: { after: 240 }, border: { bottom: { style: BorderStyle.SINGLE, size: 18, color: AMBER, space: 6 } }, children: [new TextRun({ text: 'Standard Technical Document', size: 40, color: '26384A' })] }));
c.push(P('A unified, parcel-centric, GIS-based platform for Indian land governance', { run: { size: 26, color: MUTED } }));
c.push(gap());
c.push(P('**Smart India Hackathon 2026  ·  Team GeoVault**'));
c.push(P('Document version 1.0  ·  September 2026'));
c.push(P(`Describes the working prototype: ${D.counts.parcels} synthetic parcels, ${Object.keys(D.regions).length} districts in ${new Set(Object.values(D.regions).map(r => r.state)).size} states, ${D.counts.endpoints} documented API operations.`));
c.push(gap());
c.push(note('How to read this document.', 'Every section separates what is **implemented and tested in the prototype** from what is a **proposed production design**. Endpoint tables, state-adapter mappings and model metrics are generated from the running code, so they match the software. Nothing here claims a legal or security certification.', BLUE));
c.push(new Paragraph({ children: [new PageBreak()] }));
c.push(new Paragraph({ spacing: { after: 160 }, children: [new TextRun({ text: 'Contents', bold: true, size: 32, color: BLUE })] }));
c.push(new TableOfContents('Contents', { hyperlink: true, headingStyleRange: '1-2' }));
c.push(P('If the contents list appears empty, right-click it in Word and choose Update Field.', { run: { size: 17, color: MUTED } }));

// 1
c.push(H1('1. Purpose and scope'));
c.push(P('Land records in India are held by different departments (revenue, registration, survey, planning, municipal) under different state laws, in different formats and languages. The result is disputes, delays and duplicated effort. Land Stack demonstrates a single, parcel-centric platform that links those records through one identifier, respects state differences instead of erasing them, and gives citizens and officers the right level of access.'));
c.push(H2('1.1 What the prototype demonstrates'));
c.push(...bullets([
  '**One parcel, one identifier.** Every plot has a 14-character ULPIN; all layers of information hang off it.',
  '**Three data tiers.** Base (cadastral geometry and identity), essential (Record of Rights, registration, encumbrance, land use, building permission) and additional (tax, utilities, valuation, satellite monitoring).',
  '**State adapters.** Local record names, area units and languages per state, plus ingestion mappings from each state\'s own field names to a common schema.',
  '**Drawn boundaries.** Plots are registered by drawing a polygon; the server computes the area and rejects self-crossing, out-of-jurisdiction or overlapping shapes.',
  '**A complete sale-deed workflow** with OTP authentication of both parties, duty computation, registration and a separate revenue-department mutation.',
  '**Real citizen identity.** Access is keyed on a unique person ID plus OTP, never on a name.',
  '**Explainable risk analytics** and a **tamper-evident audit trail**.',
  '**Mobile-first delivery** as an installable, offline-capable web app in five languages.'
]));
c.push(H2('1.2 Out of scope for the prototype'));
c.push(P('Real Aadhaar/DigiLocker e-KYC, real payment gateways, real SMS delivery, live integrations with state land-record systems, live satellite imagery and legal-grade digital signatures are represented by simulations or documented interfaces only. All data is synthetic.'));

// 2
c.push(H1('2. System architecture'));
c.push(img('architecture.png', 600, 385));
c.push(caption('Figure 1 — Logical architecture. Solid = implemented; dashed = production path.'));
c.push(table(['Layer', 'Component', 'Responsibility'], [
  ['Presentation', 'Single-page web app (plain JavaScript, Leaflet)', 'Citizen and officer portals, map with layer toggles, drawing tool, sale-deed screens, five UI languages, installable PWA with an offline shell.'],
  ['API', 'Flask application, five blueprints', `${D.counts.endpoints} operations. Session authentication, citizen OTP, CSRF header guard, role and district authorisation, security headers, generated OpenAPI 3 spec.`],
  ['Domain', '`adapters`, `geo`, `services`, `routes/deeds`', 'State terms/units/ingestion, geometry validation and overlap, ownership transfer, valuation, deed state machine.'],
  ['Analytics', '`risk_model`, rules, `satellite`', 'Logistic-regression risk score with per-parcel explanations, transparent rule baseline, synthetic change-detection demo.'],
  ['Integrity', '`audit`', 'SHA-256 hash-chained audit log with a verification endpoint.'],
  ['Data', '`store` (SQLite)', 'Persistent JSON documents with an indexed district column and an append-only audit table. Written in one transaction per request.']
], [1500, 2900, 5238]));
c.push(gap());
c.push(H2('2.1 Technology choices'));
c.push(table(['Concern', 'Prototype', 'Why', 'Production direction'], [
  ['Language / framework', 'Python 3, Flask', 'Fast to build and read; wide talent pool.', 'Same code behind gunicorn/uWSGI; services extractable per state.'],
  ['Persistence', 'SQLite (WAL)', 'Zero-install, survives restarts.', 'PostgreSQL + PostGIS with spatial indexes and row-level security.'],
  ['Geometry', 'Pure-Python module', 'No GIS install needed on a laptop.', 'PostGIS / GEOS topology functions.'],
  ['Front end', 'Vanilla JS, Leaflet', 'No build step; runs anywhere.', 'Same, or a framework if the team prefers.'],
  ['ML', 'numpy logistic regression', 'Explainable by construction; tiny.', 'Same model family first; gradient-boosted trees only if they beat it on real data.']
], [1700, 1900, 2800, 3238]));

// 3
c.push(H1('3. Data model and schemas'));
c.push(H2('3.1 Data layers'));
c.push(table(['Tier', 'Layer', 'Prototype content', 'Visible to'], [
  ['Base', 'Cadastral geometry, ULPIN, zone code, owner name', 'Polygon (GeoJSON), 14-char ULPIN, A/C/U/R zone, name unless the owner chose privacy', 'Everyone'],
  ['Essential', 'Record of Rights; registration; encumbrance; land-use/zoning; building permission', 'Owner ID and name, area, survey no., ownership history, registration record, mortgage flag, designated use, permit status', 'Owner; officers of that district'],
  ['Additional', 'Property tax; utilities; valuation; satellite watch; bank/loan', 'Tax status and dues, water/power flags, guideline value, change-detection result; bank and loan for the owner only', 'Owner; district officers (bank/loan: owner only)']
], [1100, 2400, 3900, 2238]));
c.push(gap());
c.push(H2('3.2 Canonical parcel schema (abridged)'));
c.push(table(['Field', 'Type', 'Notes'], [
  ['`ulpin`', 'string(14)', '`<state 2><district 3><sequence 9>`, e.g. `TNCOI000000001`. Illustrative structure, not the official ULPIN layout. Must carry the district prefix of the registering officer.'],
  ['`geometry`', 'GeoJSON Polygon', 'WGS-84 (EPSG:4326), RFC 7946 order [lon, lat]. Area is derived from it, never typed in.'],
  ['`record_of_rights`', 'object', '`owner_id` (person ID), `owner_name`, `past_owners[]`, `area_sqm`, `khasra_or_plot_no`, `ror_last_updated`.'],
  ['`ownership_history[]`', 'array', 'Each entry: owner ID/name, `from_date`, `to_date`, `basis` (fresh registration, sale deed no., succession request), `deed_id`.'],
  ['`registration`', 'object', 'Latest owner name, transaction type/date, registration number.'],
  ['`encumbrance`', 'object', '`has_encumbrance`, details. A mortgaged plot needs a bank NOC before a sale deed can be drafted.'],
  ['`land_use_zoning`, `building_permission`', 'objects', 'Designated use, master-plan reference, permit status.'],
  ['`property_tax`, `utilities`', 'objects', 'Assessee, dues, status; water and power connections.'],
  ['`bank_link`', 'object', 'Only the last four digits of an account are ever stored; readable by the owning citizen only.'],
  ['`privacy`', 'object', '`public_visible` toggled by the owner; officers of the district still see the name.'],
  ['`pending_mutation`', 'object (optional)', 'Set between deed registration and mutation so the temporary registration/RoR gap is shown as a normal lag.']
], [2400, 1500, 5738]));
c.push(gap());
c.push(H2('3.3 Identity'));
c.push(P('Each person has an immutable **person ID** (`CID-########`), a name, a mobile number and a login. Parcels reference `owner_id`, never a name. The seed data deliberately contains two different people called "Rajesh Kumar" in different districts; an automated test proves that neither can open the other\'s plot. Earlier prototype versions matched by name, which is unsafe — this was the most important design correction.'));
c.push(note('Production note.', 'The person ID is a prototype stand-in. A real deployment would bind identity to a verified credential (e.g. Aadhaar-based e-KYC or DigiLocker) under the applicable legal framework, and would never rely on a mobile number alone.'));

// 4
c.push(H1('4. State adapter layer'));
c.push(P('Land is a State subject. Record names, units, field layouts and languages differ, so forcing one format nationally would lose meaning and invite resistance. Each state therefore has an **adapter** that (1) supplies local terms in English and the local script, (2) converts areas to that state\'s units, and (3) maps a raw record in the state\'s own field names onto the canonical schema.'));
const A = D.adapters;
c.push(table(['State', 'Record of Rights', 'Survey term', 'Area units (primary first)', 'UI language'],
  Object.entries(A).map(([s, a]) => [s, `${a.terms.record_of_rights.en}\n${a.terms.record_of_rights.local}`, `${a.terms.survey_number.en}\n${a.terms.survey_number.local}`,
    [a.primary_unit, ...a.units.map(u => u.unit).filter(u => u !== a.primary_unit)].join(', '), a.language])
  , [1500, 2500, 2300, 2138, 1200]));
c.push(gap());
c.push(H2('4.1 Ingestion mapping'));
c.push(P('An officer can paste a state-format record and preview how it maps before anything is saved (`POST /api/adapters/normalize`). Fields the adapter does not recognise are reported, not silently dropped; extents in local units are converted to square metres.'));
c.push(table(['State', 'Raw field → canonical field'],
  Object.entries(A).map(([s, a]) => [s, Object.entries(a.ingestion_fields).map(([k, v]) => `\`${k}\` → \`${v}\``).join('   ')]), [1500, 8138], { size: 17 }));
c.push(gap());
c.push(note('Caveat.', 'Local-script terms and UI translations were drafted for the prototype and must be reviewed by native speakers and the state revenue departments. Some units (notably the Rajasthan bigha) vary by region; the unit sizes are configuration, not law.'));

// 5
c.push(H1('5. API standards'));
c.push(table(['Topic', 'Standard used'], [
  ['Style', 'REST over HTTP, JSON bodies, resource-oriented paths under `/api/`.'],
  ['Specification', 'OpenAPI 3.0.3, generated from the live routes at `/api/openapi.json`; interactive explorer at `/api/docs`. Access rules come from the same decorators that enforce them.'],
  ['Authentication', 'Server-side session in an HttpOnly, SameSite=Lax cookie. Officers: password. Citizens: password then a one-time password sent to the registered mobile.'],
  ['CSRF', 'Every state-changing request must carry `X-Requested-With: LandStack`; a cross-site page cannot send it without a CORS pre-flight, which is never granted.'],
  ['Authorisation', 'Role (revenue / registration / planning officer, citizen) plus scope: officers act only inside their district; citizens only on plots they own by person ID.'],
  ['Errors', 'Non-2xx responses carry `{"error": "human-readable message"}`; 400 validation, 401 not logged in, 403 not permitted, 404 unknown, 409 workflow conflict, 429 lock-out.'],
  ['Geospatial output', 'GeoJSON FeatureCollection (RFC 7946) at `/api/parcels`, structured so it can be wrapped as an OGC API – Features collection (not implemented).'],
  ['Versioning', 'Not yet versioned. Production should add a `/v1/` prefix and a deprecation policy before external systems integrate.'],
  ['Idempotency / pagination', 'Not implemented; list endpoints are small in the prototype. Production needs cursor pagination and idempotency keys on payments.']
], [2100, 7538]));
c.push(gap());
c.push(P(`The full endpoint list (${D.counts.endpoints} operations) is in Appendix A.`));

// 6
c.push(H1('6. GIS standards and geometry rules'));
c.push(table(['Rule', 'Implementation'], [
  ['Coordinate system', 'WGS-84 (EPSG:4326) for storage and exchange. Production should compute areas in the official projected CRS for each state.'],
  ['Area', 'Computed server-side from the polygon in a local equirectangular projection around its centroid, then the shoelace formula. Accurate to well under 0.1% at plot scale. The seeded data is checked so each polygon\'s area equals its recorded area.'],
  ['Shape validity', 'At least three distinct points; edges must not cross (bow-ties rejected); area between 5 m² and 2,000,000 m².'],
  ['Overlap', 'A new plot is compared with every registered plot. It is rejected if more than 0.5% of the smaller plot lies inside the other or a vertex penetrates more than 0.5 m. Shared boundaries and GPS-level slivers are allowed, so neighbouring plots register cleanly.'],
  ['Jurisdiction', 'All vertices must lie within the district\'s radius (a circular stand-in for the official district polygon).'],
  ['Live feedback', '`POST /api/geo/check-boundary` is called as the officer draws and reports validity, area in local units, jurisdiction and overlapping plots, so mistakes are caught before submission.'],
  ['Base maps', 'Tile source is a single constant (`MAP_TILES`). The default OpenStreetMap tiles show disputed borders using a neutral international convention; deployments that must follow the official map of India should switch to an authorised provider such as Bhuvan or Mappls (own API key required).']
], [2100, 7538]));
c.push(gap());
c.push(H2('6.1 Alignment with land-administration standards'));
c.push(P('The model maps naturally onto **ISO 19152 (LADM)**: a person is a Party; the Record of Rights, encumbrance and registration are Rights, Restrictions and Responsibilities; a parcel is a Basic Administrative Unit with a Spatial Unit. This is a conceptual alignment for discussion, not a conformance claim.'));
c.push(P('**Limits of the prototype geometry:** it uses a circular jurisdiction test, a sampled overlap estimate and no topology store. These are adequate for demonstration; PostGIS with a GiST index would replace them at scale.'));

// 7
c.push(H1('7. Security framework'));
c.push(H2('7.1 Access model'));
c.push(table(['Capability', 'Public', 'Citizen (owner)', 'Revenue', 'Registration', 'Planning'], [
  ['View owner name, survey no., zone', 'Yes*', 'Yes', 'Yes', 'Yes', 'Yes'],
  ['Full dossier of a plot', 'No', 'Own plots', 'Own district', 'Own district', 'Own district'],
  ['Bank and loan details', 'No', 'Own plots only', 'No', 'No', 'No'],
  ['Hide own name publicly', 'No', 'Yes', 'No', 'No', 'No'],
  ['Register a parcel', 'No', 'No', 'No', 'Own district', 'No'],
  ['Draft / authenticate / register a deed', 'No', 'No', 'No', 'Own district', 'No'],
  ['Complete mutation', 'No', 'No', 'Own district', 'No', 'No'],
  ['Approve record-update requests', 'No', 'No', 'No', 'Own district', 'No'],
  ['Post updates, view risk/reports/audit', 'No', 'Updates: read', 'Own district', 'Own district', 'Own district']
], [3000, 900, 1400, 1400, 1500, 1438], { size: 17 }));
c.push(P('* Unless the owner has chosen privacy, in which case only that district\'s officers and the owner see the name.', { run: { size: 17, color: MUTED } }));
c.push(H2('7.2 Controls implemented'));
c.push(...bullets([
  '**Passwords** stored only as salted PBKDF2-SHA256 hashes (310,000 iterations). Five failures lock the account for five minutes.',
  '**Citizen OTP.** Six digits, five-minute expiry, single use, five attempts, stored hashed. In demo mode the API returns the OTP on screen; with `LANDSTACK_DEMO_MODE=0` it is never returned.',
  '**Deed authentication.** The seller and the buyer each verify a separate OTP before fees can be recorded.',
  '**District isolation** on both viewing and acting; tests confirm an officer cannot read or change another district\'s plot.',
  '**Input handling.** Names are validated against an allow-list; all dynamic output in the front end is HTML-escaped. A browser test registers a plot whose place name contains an `<img onerror>` payload and confirms it renders as text and never runs.',
  '**Data minimisation.** Only the last four digits of a bank account are kept; a bank link is dropped on change of ownership.',
  '**Session hygiene.** Session cleared on login; HttpOnly + SameSite cookie; eight-hour lifetime; `nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy` headers; API responses are `no-store` and never cached by the service worker.',
  '**Tamper-evident audit trail** (7.3).'
]));
c.push(H2('7.3 Audit hash chain'));
c.push(P('Every action is appended to an audit log. Each entry stores the SHA-256 of the previous entry combined with its own contents. `GET /api/audit-log/verify` recomputes the chain and reports the first broken entry. Tests confirm that editing an entry, deleting an entry, or editing the database file directly are all detected.'));
c.push(note('What this does not do.', 'It makes silent changes **detectable**, not impossible. Someone with full control of the database could rewrite the whole chain, and deleting the newest entries is invisible unless the head hash was recorded elsewhere. Production should publish the head hash periodically to a store the database administrator cannot alter.'));
c.push(H2('7.4 Threat model (summary)'));
c.push(table(['Threat', 'Mitigation in prototype', 'Residual risk'], [
  ['Credential guessing', 'Lock-out, hashed passwords, citizen OTP', 'Officers use a single factor'],
  ['OTP brute force', 'Expiry, five attempts, single use', 'OTP state is in memory (lost on restart, not shared across workers)'],
  ['Citizen reads another\'s land', 'Access by person ID; homonym test', 'Depends on real identity proofing'],
  ['Officer overreach', 'District scoping on read and write; role separation between registration and mutation', 'Insider collusion across roles'],
  ['CSRF / XSS', 'Custom header + SameSite; input allow-list + output escaping', 'No Content-Security-Policy yet'],
  ['Record tampering', 'Hash-chained audit', 'Needs external anchoring'],
  ['Bank data exposure', 'Owner-only, last four digits', 'Mock data only'],
  ['Data at rest / in transit', '—', '**Not encrypted; plain HTTP on localhost. TLS and disk encryption are mandatory in production.**']
], [2300, 3800, 3538], { size: 17 }));
c.push(gap());
c.push(note('Privacy law.', 'Owner-controlled visibility, data minimisation and an audit trail follow the spirit of India\'s Digital Personal Data Protection Act, 2023. No legal review has been done and this document makes no compliance claim.'));

// 8
c.push(H1('8. Sale-deed workflow'));
c.push(img('deed_states.png', 610, 216));
c.push(caption('Figure 2 — Deed states. Registration and mutation are deliberately separate departments.'));
c.push(table(['Step', 'Actor', 'Checks', 'Effect'], [
  ['Draft', 'Registration Officer, in the presence of both parties', 'Plot in officer\'s district; buyer exists and differs from seller; price > 0; no other active deed; encumbered plots need a bank NOC', 'Computes guideline value, stamp duty, registration fee; sends an OTP to seller and to buyer'],
  ['Authenticate', 'Registration Officer records each party\'s OTP', 'Correct, unexpired, unused OTP', 'Both verified → AUTHENTICATED'],
  ['Pay', 'Registration Officer', 'Both parties authenticated; valid challan reference', 'PAID'],
  ['Register', 'Registration Officer', 'Fees paid; owner still the seller; encumbrance unchanged', 'Deed number issued; registration layer updated; plot marked "mutation pending"'],
  ['Mutate', 'Revenue Officer (same district)', 'Deed registered', 'Record of Rights, ownership history, tax assessee move to the buyer; seller\'s bank link is removed'],
  ['Cancel', 'Registration Officer', 'Only before REGISTERED', 'CANCELLED (fees flagged for refund)']
], [1000, 2200, 3500, 2938], { size: 17 }));
c.push(gap());
c.push(P('Duty is calculated on the **higher** of the declared price and the guideline value. Rates in the prototype are illustrative placeholders:'));
c.push(table(['State', 'Stamp duty', 'Registration fee'], Object.entries(D.duty).map(([s, r]) => [s, r.stamp_duty_pct + '%', r.registration_fee_pct + '%']), [3800, 2900, 2938]));
c.push(gap());
c.push(P('Both the citizen portal ("My Transactions") and the officer portal show the same status stepper and a full timeline of who did what and when.'));

// 9
c.push(H1('9. AI/ML and monitoring'));
c.push(H2('9.1 Dispute-risk analytics'));
c.push(P('Two signals are shown side by side. The **rule score** flags owner-name mismatches between the Record of Rights, the registration layer and the tax layer — fully transparent. The **learned score** is an L2-regularised logistic regression over nine record features (mismatches, encumbrance, ownership churn, recent transactions, unpaid tax, satellite flag, plot size, land use). Each score comes with its top contributing factors, so an officer can see why.'));
const M = D.model_card;
c.push(table(['Measure', 'Value'], [
  ['Training data', M.training_data], ['Held-out test data', M.test_data], ['Base rate of "dispute" label', (M.dispute_base_rate * 100).toFixed(1) + '%'],
  ['AUC (learned model)', String(M.auc_test)], ['AUC (rule baseline)', String(M.auc_rule_baseline)],
  ['Precision / recall in top 10% of scores', `${(M.precision_top_decile * 100).toFixed(0)}% / ${(M.recall_top_decile * 100).toFixed(0)}%`]
], [3800, 5838]));
c.push(gap());
c.push(note('Honesty note.', 'No public dataset links these features to real land-dispute outcomes. The model is trained on **synthetic** records whose labels come from a documented generating process plus noise. The metrics therefore show the pipeline works and recovers that process — they are **not** evidence of real-world accuracy. The pipeline is designed so real, court-derived labels can replace the synthetic ones. Scores support an officer\'s judgement and never trigger automatic action.', 'B3261E'));
c.push(...bullets(M.limitations.map(l => l)));
c.push(H2('9.2 Satellite change detection'));
c.push(P('Watched plots show a before/after pair and a change percentage, flagging possible unauthorised construction on agricultural or non-building land. In the prototype the imagery is **synthetic**; production would take real multi-date imagery and compare it with the permitted-use layer.'));

// 10
c.push(H1('10. UI/UX guidelines'));
c.push(H2('10.1 Portals and navigation'));
c.push(P('The citizen portal (`/citizen`) offers Map, Search, My Land, My Transactions and Updates. The officer portal (`/officer`) adds Register Land, Sale Deeds, Record Updates, Risk & Anomalies, Satellite, Reports and Audit Log, filtered by the officer\'s role. The public page (`/`) offers Map and Search only.'));
c.push(H2('10.2 Map layers'));
c.push(P('A layer panel exposes the three tiers: **Base** (parcel boundaries, zone labels), **Essential** (colour by zoning, encumbrance or building permission) and **Additional** (tax-status outline, satellite watch, utility gaps). Detail layers colour only the plots the viewer may see in full; everything else stays neutral grey, so the map never leaks restricted data.'));
c.push(H2('10.3 Design tokens'));
c.push(table(['Token', 'Value', 'Use'], [
  ['Primary', '`#0F4C81`', 'Header, primary actions, headings'], ['Accent', '`#E08A00`', 'Active tab, call-to-action, "my plots" outline'],
  ['Success / danger', '`#1B7A43` / `#B3261E`', 'Verified, clear, paid / errors, encumbered, due'],
  ['Zone A / C / U / R', '`#4CAF50` `#F59E0B` `#2F80ED` `#8D6E63`', 'Agriculture, Commercial, Urban, Rural'],
  ['Background / card / border', '`#F4F6F9` `#FFFFFF` `#D9E0E8`', 'Surfaces'],
  ['Type', 'System UI stack with Noto Sans fallbacks for Devanagari, Tamil, Telugu, Malayalam', 'All text; base 15 px']
], [2500, 3900, 3238]));
c.push(gap());
c.push(H2('10.4 Accessibility, language and mobile'));
c.push(...bullets([
  'Colour is never the only signal: statuses carry text badges, and the map shows zone letters and a legend.',
  'Visible focus outlines, labelled controls, ARIA roles on tabs and the map, live regions for detail panels, reduced-motion respected, minimum 44 px tap targets on phones.',
  'Layout collapses to one column below 900 px; the layer panel becomes a toggle; tables scroll inside their own container (automatically tested: no horizontal page overflow at 390 px in Malayalam).',
  'Five interface languages (English, Hindi, Tamil, Telugu, Malayalam) for navigation, login, map layers and dossier labels; record names and units come from the state adapter. Officer form text is currently English only.',
  'Installable Progressive Web App with an offline application shell. Land data and OTPs are never cached; offline mode says so plainly.'
]));
c.push(note('Not yet done.', 'No screen-reader audit, no formal WCAG conformance test, and translations are unreviewed. These are prerequisites for a public launch.'));

// 11
c.push(H1('11. Deployment and scalability'));
c.push(H2('11.1 Running the prototype'));
c.push(P('`pip install -r requirements.txt`, then `python backend/app.py`. The first start creates and seeds `backend/data/landstack.db` (about ten seconds because passwords are hashed); later starts load it. Deleting the file re-seeds. Demo logins are listed in `backend/data/DEMO_LOGINS.txt` and in the login screen\'s demo-account picker.'));
c.push(H2('11.2 Proposed production architecture'));
c.push(table(['Concern', 'Prototype', 'Production design'], [
  ['Web tier', 'Single Flask process', 'Stateless app servers behind a load balancer with TLS termination; horizontal scaling.'],
  ['Database', 'SQLite, single writer', 'PostgreSQL + PostGIS, replicas for reads, point-in-time backup; row-level security by district.'],
  ['Sessions, OTPs, lock-outs', 'Process memory', 'Redis (shared, expiring), so any worker can serve any request.'],
  ['Spatial queries', 'Linear scan of parcels', 'GiST index; overlap and jurisdiction as SQL predicates.'],
  ['Multi-state rollout', 'Adapters in one codebase', 'Each state runs its own instance with its adapter; a national index resolves a ULPIN to the owning state (federated, matching State-subject ownership of land).'],
  ['Integrations', 'Simulated OTP, payment, bank, satellite', 'SMS gateway, payment gateway, bank/account-aggregator APIs, e-KYC, satellite imagery provider, behind an integration layer with retries and audit.'],
  ['Audit anchoring', 'Hash chain in the same database', 'Periodic head-hash publication to an independent write-once store.'],
  ['Observability', 'Server log', 'Structured logs, metrics, alerting, tracing.'],
  ['Security hardening', 'See 7.4 gaps', 'TLS everywhere, encryption at rest, MFA for officers, CSP, rate limiting by IP, penetration test, secrets management.']
], [1900, 2500, 5238], { size: 17 }));
c.push(gap());
c.push(note('Performance.', 'No load testing has been done and no throughput figures are claimed. The prototype holds 92 parcels; scaling behaviour beyond that is a design argument, not a measurement.'));

// 12
c.push(H1('12. Testing and quality'));
c.push(table(['Suite', 'Scope', 'Tests'], [
  ['Core', 'Seed integrity, persistence across restart, homonym identity, OTP rules, lock-out, hashed passwords, CSRF, district isolation, bank privacy, privacy toggle, audit access, demo-mode gating, Referer policy for map tiles, hosted-HTTPS mode', '19'],
  ['Workflows', 'Polygon registration (area, overlap, adjacency, bow-tie, jurisdiction, ULPIN rules, hostile input), full deed lifecycle and gates, succession, updates scoping, adapters, risk model, OpenAPI coverage, audit tamper detection', '26'],
  ['Browser', 'Real Chromium against the real server: public view and language switching, citizen OTP login and dossier, wrong credentials, drawing a plot with live checks, XSS escaping, complete sale deed through the UI, layer toggles, mobile layout, PWA install and offline shell', '8']
], [1200, 7638, 800]));
c.push(gap());
c.push(P('**Total: 53 automated tests**, all passing. Browser tests replace Leaflet with a small stand-in (the test environment cannot reach the map CDN), so map rendering against real Leaflet and tiles is **not** covered by the automated tests and should be checked by hand on a networked machine.'));

// 13
c.push(H1('13. Known limitations and roadmap'));
c.push(table(['Area', 'Limitation', 'Next step'], [
  ['Identity', 'Person IDs and mobile numbers are simulated', 'Verified credential / e-KYC integration'],
  ['Data', 'All records are synthetic; illustrative rates and guideline values', 'Ingest real state data through the adapters; load official rate notifications'],
  ['ML', 'Trained on synthetic labels', 'Court/revenue dispute data; re-evaluate against the rule baseline'],
  ['Satellite', 'Synthetic imagery', 'Real imagery provider and permitted-use comparison'],
  ['Security', 'No TLS or at-rest encryption; officers single-factor', 'See Section 11 hardening list'],
  ['Scale', 'SQLite, in-memory OTP/lock-out state', 'PostGIS + Redis'],
  ['Languages', 'Unreviewed translations; officer forms English only', 'Native-speaker review; full localisation'],
  ['Documents', 'No PDF deed or encumbrance certificate', 'Generate signed documents'],
  ['Standards', 'No API versioning or OGC API wrapper', '`/v1/`, OGC API – Features']
], [1500, 4300, 3838], { size: 17 }));

// Appendix A
c.push(H1('Appendix A — API endpoint reference'));
c.push(P('Generated from the running application. "Access" is enforced by the same decorators that produce this table. Every non-GET request also requires the `X-Requested-With: LandStack` header.'));
let grp = '';
const rows = [];
D.endpoints.forEach(e => { rows.push([e.method, '`' + e.path + '`', e.access, e.summary]); });
c.push(table(['Method', 'Path', 'Access', 'Summary'], rows, [800, 3300, 2000, 3538], { size: 15 }));

// ---------- document ----------
const doc = new Document({
  creator: 'Team GeoVault', title: 'Land Stack — Standard Technical Document', description: 'SIH 2026 technical document',
  features: { updateFields: true },
  styles: {
    default: { document: { run: { font: 'Arial', size: 21 } } },
    paragraphStyles: [
      { id: 'Heading1', name: 'Heading 1', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { size: 34, bold: true, font: 'Arial', color: BLUE },
        paragraph: { spacing: { before: 120, after: 200 }, outlineLevel: 0, border: { bottom: { style: BorderStyle.SINGLE, size: 12, color: AMBER, space: 4 } } } },
      { id: 'Heading2', name: 'Heading 2', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { size: 26, bold: true, font: 'Arial', color: '26384A' },
        paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 1 } },
      { id: 'Heading3', name: 'Heading 3', basedOn: 'Normal', next: 'Normal', quickFormat: true, run: { size: 22, bold: true, font: 'Arial', color: MUTED },
        paragraph: { spacing: { before: 160, after: 80 }, outlineLevel: 2 } }
    ]
  },
  numbering: { config: [{ reference: 'bul', levels: [{ level: 0, format: LevelFormat.BULLET, text: '•', alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 540, hanging: 270 } } } }] }] },
  sections: [{
    properties: { page: { size: { width: 11906, height: 16838 }, margin: { top: 1134, bottom: 1134, left: 1134, right: 1134 } } },
    headers: { default: new Header({ children: [new Paragraph({ alignment: AlignmentType.RIGHT, children: [new TextRun({ text: 'Land Stack · Standard Technical Document · Team GeoVault', size: 16, color: MUTED })] })] }) },
    footers: { default: new Footer({ children: [new Paragraph({ alignment: AlignmentType.CENTER, children: [new TextRun({ text: 'Page ', size: 16, color: MUTED }), new TextRun({ children: [PageNumber.CURRENT], size: 16, color: MUTED })] })] }) },
    children: c
  }]
});
Packer.toBuffer(doc).then(buf => { fs.writeFileSync(OUT, buf); console.log('wrote', OUT, (buf.length / 1024).toFixed(0) + ' KB'); });
