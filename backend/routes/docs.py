"""Live API documentation."""
from flask import Blueprint, Response, current_app, jsonify

import openapi_gen

bp = Blueprint("docs", __name__)


@bp.route("/api/openapi.json")
def openapi_json():
    """OpenAPI 3.0 specification, generated from the running application."""
    return jsonify(openapi_gen.build_spec(current_app))


@bp.route("/api/docs")
def swagger_ui():
    """Interactive API explorer (Swagger UI)."""
    html = """<!doctype html><html><head><meta charset="utf-8"><title>Land Stack API</title>
<link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css"></head>
<body><div id="ui"></div><noscript>Enable JavaScript, or read /api/openapi.json directly.</noscript>
<script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>SwaggerUIBundle({url:"/api/openapi.json",dom_id:"#ui"});</script></body></html>"""
    return Response(html, mimetype="text/html")
