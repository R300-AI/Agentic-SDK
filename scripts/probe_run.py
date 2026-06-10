"""一次性檢查 Cloud Run revision 與最近 log。"""

from __future__ import annotations

import sys

import requests
from google.auth.transport.requests import Request
from google.oauth2 import service_account

SA_PATH = r"C:\Users\B20447\Desktop\eternal-insight-423516-m3-77714146c715.json"
PROJECT = "eternal-insight-423516-m3"
LOCATION = "asia-east1"
SERVICE = "agentic-sdk-gateway"


def get_token() -> str:
    creds = service_account.Credentials.from_service_account_file(
        SA_PATH, scopes=["https://www.googleapis.com/auth/cloud-platform"]
    )
    creds.refresh(Request())
    return creds.token


def main() -> None:
    token = get_token()
    h = {"Authorization": f"Bearer {token}"}

    svc_url = (
        f"https://run.googleapis.com/v2/projects/{PROJECT}"
        f"/locations/{LOCATION}/services/{SERVICE}"
    )
    svc = requests.get(svc_url, headers=h).json()
    print("=== SERVICE ===")
    print("uri:", svc.get("uri"))
    print("latestReady:", str(svc.get("latestReadyRevision", "")).split("/")[-1])
    print("latestCreated:", str(svc.get("latestCreatedRevision", "")).split("/")[-1])
    print("conditions:")
    for c in svc.get("conditions", []):
        print(" -", c.get("type"), c.get("state"), c.get("message", ""))

    # Revision detail
    rev_name = svc.get("latestReadyRevision") or svc.get("latestCreatedRevision")
    if rev_name:
        rev = requests.get(f"https://run.googleapis.com/v2/{rev_name}", headers=h).json()
        print("\n=== REVISION ===")
        print("name:", rev_name.split("/")[-1])
        print("conditions:")
        for c in rev.get("conditions", []):
            print(" -", c.get("type"), c.get("state"), c.get("message", ""))

    # Logs (will 403 if SA lacks logging.viewer)
    body = {
        "resourceNames": [f"projects/{PROJECT}"],
        "filter": (
            f'resource.type="cloud_run_revision" '
            f'AND resource.labels.service_name="{SERVICE}"'
        ),
        "pageSize": 40,
        "orderBy": "timestamp desc",
    }
    r = requests.post(
        "https://logging.googleapis.com/v2/entries:list", headers=h, json=body
    )
    print("\n=== LOGS HTTP:", r.status_code, "===")
    if r.status_code != 200:
        print(r.text[:500])
        sys.exit(0)
    entries = r.json().get("entries", [])
    for e in entries:
        sev = e.get("severity", "DEFAULT")
        msg = (
            e.get("textPayload")
            or (e.get("jsonPayload") or {}).get("message")
            or str(e.get("jsonPayload") or e.get("protoPayload") or "")[:200]
        )
        print(f"[{sev}] {msg}")


if __name__ == "__main__":
    main()
