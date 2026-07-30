from __future__ import annotations

import os
from flask import Flask

from playground.routes.aihub import aihub_bp
from playground.routes.builder import builder_bp
from playground.routes.entry import entry_bp
from playground.routes.runner import runner_bp
from playground.routes.source import source_bp
from playground.services.key_vault_config import load_key_vault_secrets


def create_app() -> Flask:
    load_key_vault_secrets(override=False)

    app = Flask(__name__)
    app.config.update(SECRET_KEY=os.environ.get("PLAYGROUND_SECRET_KEY", "agentic-sdk-playground-dev"))

    app.register_blueprint(entry_bp)
    app.register_blueprint(builder_bp)
    app.register_blueprint(runner_bp)
    app.register_blueprint(aihub_bp)
    app.register_blueprint(source_bp)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)