from __future__ import annotations

import argparse

from playground_v1_gateway.app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Playground V1 development gateway.")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    app = create_app()
    app.run(host=args.host, port=args.port, debug=args.debug, use_reloader=False)


if __name__ == "__main__":
    main()