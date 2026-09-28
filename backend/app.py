"""
Land Stack prototype — application entry point.

    pip install -r requirements.txt
    python app.py                      # then open http://127.0.0.1:5000/citizen  or  /officer

Data persists in backend/data/landstack.db (delete it to re-seed). Demo logins
are written to backend/data/DEMO_LOGINS.txt. Set LANDSTACK_DEMO_MODE=0 to stop
the API returning demo OTPs/passwords.
"""
import os
from datetime import timedelta

from flask import Flask, jsonify, request, send_from_directory
from werkzeug.exceptions import HTTPException

import config
import state


def create_app(db_path=None):
    state.init(db_path)
    app = Flask(__name__, static_folder="../frontend", static_url_path="")
    app.secret_key = state.SECRET_KEY
    app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
                      PERMANENT_SESSION_LIFETIME=timedelta(hours=8), MAX_CONTENT_LENGTH=1024 * 1024)
    # Hosted behind an HTTPS proxy (Render, etc.): trust its forwarding headers, mark the cookie Secure, send HSTS.
    https = os.environ.get("LANDSTACK_HTTPS") == "1"
    if https:
        from werkzeug.middleware.proxy_fix import ProxyFix
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
        app.config["SESSION_COOKIE_SECURE"] = True

    from routes import auth, parcels, deeds, governance, docs
    for m in (auth, parcels, deeds, governance, docs):
        app.register_blueprint(m.bp)

    @app.before_request
    def csrf_guard():
        # A custom header can't be sent cross-site without a CORS preflight, which we never allow.
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and request.path.startswith("/api/"):
            if request.headers.get("X-Requested-With") != "LandStack":
                return jsonify({"error": "Missing X-Requested-With: LandStack header"}), 400

    @app.after_request
    def persist_and_harden(resp):
        if state.has_pending():
            try:
                state.flush()
            except Exception:                                   # never claim success if the save failed
                app.logger.exception("flush failed")
                fail = jsonify({"error": "Could not save your changes"})
                fail.status_code = 500
                resp = fail
        resp.headers["X-Content-Type-Options"] = "nosniff"
        if https:
            resp.headers["Strict-Transport-Security"] = "max-age=31536000"
        resp.headers["X-Frame-Options"] = "DENY"
        # Must still send the site origin cross-origin: OpenStreetMap's tile servers block requests with no Referer.
        resp.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        if request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-store"
        return resp

    @app.errorhandler(HTTPException)
    def http_error(e):
        if request.path.startswith("/api/"):
            return jsonify({"error": e.description or e.name}), e.code
        return e

    @app.errorhandler(Exception)
    def unhandled(e):
        app.logger.exception("unhandled error")
        return jsonify({"error": "Internal server error"}), 500

    def page():
        return send_from_directory(app.static_folder, "index.html")

    for rule in ("/", "/citizen", "/officer"):
        app.add_url_rule(rule, endpoint=f"page{rule.replace('/', '_')}", view_func=page)

    @app.route("/manifest.webmanifest")
    def manifest():
        return send_from_directory(app.static_folder, "manifest.webmanifest", mimetype="application/manifest+json")

    @app.route("/sw.js")
    def service_worker():
        r = send_from_directory(app.static_folder, "sw.js", mimetype="application/javascript")
        r.headers["Service-Worker-Allowed"] = "/"
        r.headers["Cache-Control"] = "no-cache"
        return r

    return app


if __name__ == "__main__":
    first_run = not os.path.exists(config.DB_PATH)
    if first_run:
        print("First run: creating and seeding the database (about 10 seconds, hashing passwords)...")
    application = create_app()
    import bootstrap
    login_file = bootstrap.write_demo_logins()
    host, port = os.environ.get("LANDSTACK_HOST", "127.0.0.1"), int(os.environ.get("PORT", 5000))
    print(f"\nLand Stack running:\n  Citizen portal  http://{host}:{port}/citizen\n  Officer portal  http://{host}:{port}/officer"
          f"\n  API docs        http://{host}:{port}/api/docs")
    print(f"Database: {config.DB_PATH}   Audit chain intact: {state.BOOT_CHAIN_CHECK['valid']}")
    if login_file:
        print(f"All demo logins: {login_file}")
        o = state.OFFICERS.get("reg_coimbatore")
        if o:
            print(f"Try officer  reg_coimbatore / {o['demo_password']}")
    application.run(host=host, port=port, debug=False, threaded=True)
