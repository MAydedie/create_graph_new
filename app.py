#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Flask application entrypoint.
Creates the app and registers Blueprints; all business logic lives in app/services.
"""

import os
from dotenv import load_dotenv

from app import create_app

# Ensure environment variables are loaded for local runs
load_dotenv()


# Export a module-level app for WSGI/Flask CLI compatibility
app = create_app()


if __name__ == "__main__":
    port = int(os.getenv("PORT", "5000"))
    app.run(host="0.0.0.0", port=port, debug=False)
