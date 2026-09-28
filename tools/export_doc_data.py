"""Dumps facts from the LIVE application for the technical document (endpoints, adapters, model card, counts)."""
import json
import os
import sys
import tempfile

os.environ.setdefault("LANDSTACK_HASH", "pbkdf2:sha256:1000")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "backend"))
import adapters, config, openapi_gen, state  # noqa: E402
from app import create_app  # noqa: E402

app = create_app(os.path.join(tempfile.mkdtemp(), "doc.db"))
spec = openapi_gen.build_spec(app)
groups = {"auth": "Authentication", "parcels": "Parcels & geometry", "deeds": "Sale deeds & people",
          "governance": "Governance & analytics", "docs": "Documentation"}
endpoints = []
for path, ops in spec["paths"].items():
    for method, op in ops.items():
        endpoints.append({"group": groups.get(op["tags"][0], op["tags"][0]), "method": method.upper(), "path": path,
                          "access": op["x-access"], "summary": op["summary"]})
order = list(groups.values())
endpoints.sort(key=lambda e: (order.index(e["group"]), e["path"], e["method"]))
out = {
    "endpoints": endpoints, "adapters": adapters.public_adapters(), "model_card": state.MODEL.card,
    "regions": {k: {"district": v["district"], "state": v["state"], "jurisdiction_km": v["jurisdiction_km"], "parcels": v["count"]} for k, v in config.REGIONS.items()},
    "duty": config.DUTY_RATES, "guideline": config.GUIDELINE_VALUE_PER_SQM,
    "counts": {"parcels": len(state.PARCELS), "persons": len(state.PERSONS), "officers": len(state.OFFICERS), "endpoints": len(endpoints)},
}
dest = os.path.join(os.path.dirname(os.path.abspath(__file__)), "doc_data.json")
json.dump(out, open(dest, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
print("wrote", dest, out["counts"])
