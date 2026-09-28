"""
OpenAPI 3.0 generator. Paths, methods, summaries and access rules are read
from the LIVE Flask routes (docstrings + the auth decorators), so the
specification cannot drift from the implementation. Request-body and query
schemas for the main endpoints are declared below.
"""
import re

S = lambda t, d="", **kw: {"type": t, "description": d, **kw}
NUM, STR, BOOL = "number", "string", "boolean"
BOUNDARY = {"type": "array", "description": "Polygon vertices as [latitude, longitude] pairs (≥3, not self-intersecting).",
            "items": {"type": "array", "items": {"type": "number"}, "minItems": 2, "maxItems": 2}}

BODIES = {
    ("POST", "/api/login/officer"): ({"username": S(STR), "password": S(STR)}, ["username", "password"]),
    ("POST", "/api/login/citizen"): ({"username": S(STR), "password": S(STR)}, ["username", "password"]),
    ("POST", "/api/login/citizen/verify"): ({"challenge_id": S(STR), "otp": S(STR, "6-digit code")}, ["challenge_id", "otp"]),
    ("POST", "/api/parcels/register"): ({
        "ulpin": S(STR, "14 alphanumeric characters starting with the district prefix; auto-assigned if omitted"),
        "survey_number": S(STR, "unique within the district"), "place_name": S(STR),
        "boundary": BOUNDARY, "designated_use": S(STR), "owner_id": S(STR, "existing person ID"),
        "new_owner": {"type": "object", "description": "create the owner now", "properties": {"name": S(STR), "mobile": S(STR)}},
        "past_owners": {"type": "array", "items": {"type": "string"}}, "rd_no": S(STR), "landmark": S(STR), "notes": S(STR)},
        ["survey_number", "place_name", "boundary"]),
    ("POST", "/api/geo/check-boundary"): ({"boundary": BOUNDARY}, ["boundary"]),
    ("POST", "/api/adapters/normalize"): ({"state": S(STR), "record": {"type": "object", "description": "raw record in the state's own field names"}}, ["record"]),
    ("POST", "/api/persons"): ({"name": S(STR), "mobile": S(STR, "10 digits")}, ["name", "mobile"]),
    ("POST", "/api/deeds"): ({"ulpin": S(STR), "buyer_id": S(STR), "consideration": S(NUM, "agreed price, INR"),
                              "bank_noc": S(BOOL, "required when the parcel is mortgaged"), "notes": S(STR)},
                             ["ulpin", "buyer_id", "consideration"]),
    ("POST", "/api/deeds/{deed_id}/authenticate"): ({"party": S(STR, "seller | buyer", enum=["seller", "buyer"]), "otp": S(STR)}, ["party", "otp"]),
    ("POST", "/api/deeds/{deed_id}/payment"): ({"challan_no": S(STR)}, ["challan_no"]),
    ("POST", "/api/parcel/{ulpin}/service-request"): ({"type": S(STR), "citizen_name": S(STR), "citizen_present": S(BOOL),
                                                        "new_owner_id": S(STR), "notes": S(STR)}, ["citizen_name", "citizen_present"]),
    ("POST", "/api/updates"): ({"title": S(STR), "message": S(STR), "ulpin": S(STR, "optional — target one plot")}, ["title", "message"]),
    ("POST", "/api/parcel/{ulpin}/link-bank"): ({"bank_name": S(STR), "account_number": S(STR, "only the last 4 digits are stored")}, ["bank_name", "account_number"]),
    ("POST", "/api/parcel/{ulpin}/privacy"): ({"public_visible": S(BOOL)}, ["public_visible"]),
}
QUERIES = {
    ("GET", "/api/parcels"): [("context", "region key: village | ward | town | coastal | desert")],
    ("GET", "/api/search"): [("q", "owner name, ULPIN or survey number (min 2 characters)")],
    ("GET", "/api/persons/lookup"): [("q", "name, username, person ID or mobile")],
}
SKIP = {"/api/openapi.json", "/api/docs"}


def _access(auth):
    t = auth.get("type", "public")
    if t == "officer":
        return "officer: " + ", ".join(auth["roles"])
    return {"citizen": "citizen", "any": "any logged-in user", "public": "public"}[t]


def build_spec(app):
    paths = {}
    for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
        if not rule.rule.startswith("/api/") or rule.rule in SKIP:
            continue
        view = app.view_functions[rule.endpoint]
        auth = getattr(view, "_auth", {"type": "public"})
        path = re.sub(r"<(?:[^:>]+:)?([^>]+)>", r"{\1}", rule.rule)
        doc = re.sub(r"\s+", " ", (view.__doc__ or "").strip())
        for method in sorted(rule.methods - {"HEAD", "OPTIONS"}):
            op = {"operationId": rule.endpoint.replace(".", "_"), "tags": [rule.endpoint.split(".")[0]],
                  "summary": (doc.split(". ")[0].rstrip(".") if doc else path), "description": doc,
                  "x-access": _access(auth),
                  "parameters": [{"name": n, "in": "path", "required": True, "schema": {"type": "string"}}
                                 for n in re.findall(r"{([^}]+)}", path)],
                  "responses": {"200": {"description": "OK"}}}
            for name, desc in QUERIES.get((method, path), []):
                op["parameters"].append({"name": name, "in": "query", "description": desc, "schema": {"type": "string"}})
            if auth.get("type") != "public":
                op["security"] = [{"sessionCookie": []}]
                op["responses"]["401"] = {"description": "Not logged in"}
                op["responses"]["403"] = {"description": "Logged in but not permitted (role or district)"}
            if method != "GET":
                op["parameters"].append({"name": "X-Requested-With", "in": "header", "required": True,
                                         "schema": {"type": "string", "enum": ["LandStack"]},
                                         "description": "CSRF guard: must be sent on every state-changing request"})
                op["responses"]["400"] = {"description": "Validation error — body is {\"error\": \"...\"}"}
            body = BODIES.get((method, path))
            if body:
                props, required = body
                op["requestBody"] = {"required": True, "content": {"application/json": {
                    "schema": {"type": "object", "properties": props, "required": required}}}}
            paths.setdefault(path, {})[method.lower()] = op
    return {
        "openapi": "3.0.3",
        "info": {"title": "Land Stack API", "version": "1.0.0",
                 "description": ("Parcel-centric land-governance API. JSON over HTTPS; session-cookie authentication; "
                                 "errors are {\"error\": \"message\"} with a 4xx/5xx status. All state-changing "
                                 "requests must carry `X-Requested-With: LandStack`. Officer access is scoped to the "
                                 "officer's own district; citizen access is scoped to plots they own (by person ID).")},
        "servers": [{"url": "/"}],
        "components": {"securitySchemes": {"sessionCookie": {"type": "apiKey", "in": "cookie", "name": "session"}}},
        "paths": paths,
    }
