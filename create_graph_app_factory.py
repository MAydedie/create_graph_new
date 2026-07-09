from __future__ import annotations

from flask import Flask


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["JSON_AS_ASCII"] = False

    @app.after_request
    def apply_cross_origin_isolation_headers(response):
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        response.headers.setdefault("Cross-Origin-Embedder-Policy", "require-corp")
        return response

    from app.routes.main_routes import main_bp
    from app.routes.api_routes import api_bp
    from app.routes.se_team_api_routes import se_team_api_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(api_bp)
    app.register_blueprint(se_team_api_bp)

    try:
        from app.services.persona_skill_service import deactivate_persona_skill
        deactivate_persona_skill()
    except Exception:
        pass

    return app
