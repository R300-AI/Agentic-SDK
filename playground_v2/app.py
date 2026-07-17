from __future__ import annotations

from flask import Flask

from playground_v2.routes.aihub import aihub_bp
from playground_v2.routes.builder import builder_bp
from playground_v2.routes.entry import entry_bp
from playground_v2.routes.runner import runner_bp
from playground_v2.routes.source import source_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.update(SECRET_KEY="agentic-sdk-playground-v2-dev")

    app.register_blueprint(entry_bp)
    app.register_blueprint(builder_bp)
    app.register_blueprint(runner_bp)
    app.register_blueprint(aihub_bp)
    app.register_blueprint(source_bp)

    return app


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)