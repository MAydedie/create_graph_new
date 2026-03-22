#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Flask application entrypoint.
Creates the app and registers Blueprints; all business logic lives in app/services.
"""

import os
from flask import Flask
from dotenv import load_dotenv

# Ensure environment variables are loaded for local runs
load_dotenv()


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["JSON_AS_ASCII"] = False

    @app.after_request
    def apply_cross_origin_isolation_headers(response):
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Embedder-Policy", "require-corp")
        return response

    # Register Blueprints
    from app.routes.main_routes import main_bp
    from app.routes.api_routes import api_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp)
    return app


# Export a module-level app for WSGI/Flask CLI compatibility
app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)





