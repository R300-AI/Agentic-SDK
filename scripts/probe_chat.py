"""End-to-end probe: hit Cloud Run gateway routes."""

from __future__ import annotations

import requests

BASE = "https://agentic-sdk-gateway-k6olp2xs7q-de.a.run.app"


def main() -> None:
    for path in ("/healthz", "/v1/models"):
        r = requests.get(BASE + path, timeout=30)
        snippet = r.text[:300].replace("\n", " ")
        print(f"GET {path} -> {r.status_code}  {snippet}")

    payload = {
        "model": "agentic-sdk",
        "messages": [{"role": "user", "content": "say hello in one short sentence"}],
    }
    r = requests.post(BASE + "/v1/chat/completions", json=payload, timeout=120)
    print(f"\nPOST /v1/chat/completions -> {r.status_code}")
    print(r.text[:800])


if __name__ == "__main__":
    main()
