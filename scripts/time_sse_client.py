"""
Real client-side SSE timing for the deployed Cloud Run gateway.

Simulates exactly what the browser does:
1. POST /v1/workflow/run with lanew.png + foot-report prompt
2. Open SSE stream and record each event's arrival time (client wall clock)
3. Compare client_arrival_ts vs backend_emit_ts (ev["ts"]) to see buffer delay
"""
from __future__ import annotations

import base64
import json
import sys
import time
from datetime import datetime
from pathlib import Path

import httpx

try:
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

ROOT = Path(__file__).resolve().parent.parent
IMAGE_PATH = ROOT / "lanew.png"
GATEWAY_URL = "https://agentic-sdk-gateway-348312930266.asia-east1.run.app"
PROMPT = "\U0001f4cf \u6211\u6709\u8db3\u6e2c\u5831\u544a\u60f3\u8aee\u8a62"

WORKFLOW_YAML = """version: "1"
name: demo
entry: perceive
nodes:
  perceive:
    type: builtin.perceive
    params:
      welcome_message: \u60a8\u597d
      options:
        - { label: "\U0001f4cf \u6211\u6709\u8db3\u6e2c\u5831\u544a\u60f3\u8aee\u8a62", intent: foot_analysis, expects_attachment: image }
    compute_target: local_cpu
  plan:
    type: builtin.plan
    params:
      model: gpt-5.2
      deployment: gpt-5.2
      endpoint: "https://<resource>.services.ai.azure.com"
    compute_target: azure_foundry
  retrieve:
    type: builtin.retrieve
    params:
      knowledge_base: examples/knowledge/shoe_store.json
      top_k: 3
    compute_target: local_cpu
  reflect:
    type: builtin.reflect
    params:
      on_failure: retry_plan
      mode: rule_based
    compute_target: local_cpu
  action:
    type: completion
    params:
      backend: foundry
    compute_target: azure_foundry
gates:
  max_node_hops: 20
  max_revisit: 3
  timeout_sec: 300
"""


def fmt(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S.%f")[:-3]


def main() -> int:
    if not IMAGE_PATH.exists():
        print(f"ERROR: missing image: {IMAGE_PATH}", flush=True)
        return 1

    image_b64 = base64.b64encode(IMAGE_PATH.read_bytes()).decode("ascii")
    attachment = {
        "kind": "image",
        "mime": "image/png",
        "data_url": f"data:image/png;base64,{image_b64}",
        "name": "lanew.png",
    }

    print(f"gateway={GATEWAY_URL}", flush=True)
    print(f"image=lanew.png ({IMAGE_PATH.stat().st_size} bytes)", flush=True)
    print(f"prompt=U+1F4CF (foot-report consultation)", flush=True)
    print("", flush=True)

    # ── Step 1: POST /v1/workflow/run ────────────────────────────────────
    post_start = time.time()
    with httpx.Client(timeout=60.0) as client:
        post_resp = client.post(
            f"{GATEWAY_URL}/v1/workflow/run",
            json={
                "workflow_yaml": WORKFLOW_YAML,
                "user_message": PROMPT,
                "attachments": [attachment],
            },
        )
    post_done = time.time()
    print(f"POST /v1/workflow/run -> {post_resp.status_code} in {post_done - post_start:.2f}s", flush=True)
    if post_resp.status_code != 200:
        print(post_resp.text, flush=True)
        return 1
    payload = post_resp.json()
    workflow_id = payload["workflow_id"]
    stream_path = payload["stream_url"]
    print(f"workflow_id={workflow_id}", flush=True)
    print("", flush=True)

    # ── Step 2: Open SSE stream, record client-side arrival timestamps ──
    print(
        "| Tn | client_recv | backend_emit | delay_ms | event | node#visit | first step (color change) | extra |",
        flush=True,
    )
    print("|---|---:|---:|---:|---|---|---|---|", flush=True)

    rows: list[dict] = []
    seen_first_token: dict[str, set[int]] = {"plan": set(), "action": set()}

    sse_open_ts = time.time()
    with httpx.Client(timeout=httpx.Timeout(connect=10.0, read=120.0, write=10.0, pool=10.0)) as client:
        with client.stream(
            "GET",
            f"{GATEWAY_URL}{stream_path}",
            headers={"Accept": "text/event-stream"},
        ) as resp:
            buffer = ""
            for chunk in resp.iter_text():
                client_recv = time.time()
                buffer += chunk
                while "\n\n" in buffer:
                    raw, buffer = buffer.split("\n\n", 1)
                    raw = raw.strip()
                    if not raw or raw.startswith(":"):
                        continue
                    if not raw.startswith("data:"):
                        continue
                    body = raw[len("data:"):].strip()
                    try:
                        ev = json.loads(body)
                    except json.JSONDecodeError:
                        continue

                    backend_ts = ev.get("ts")
                    delay_ms = (
                        (client_recv - backend_ts) * 1000 if isinstance(backend_ts, (int, float)) else 0.0
                    )
                    name = ev.get("event_name", "")
                    node = ev.get("workflow_node") or ""
                    visit = ev.get("workflow_node_visit")
                    visit_text = f"#{visit}" if visit else ""

                    color = ""
                    extra = ""
                    if name == "workflow.node.start":
                        color = f"{node}: gray->yellow"
                    elif name == "workflow.node.finish":
                        next_node = ev.get("workflow_next_node")
                        color = f"{node}: yellow->green"
                        if next_node:
                            extra = f"next={next_node}"
                    elif name == "workflow.node.delta":
                        delta_index = ev.get("delta_index")
                        if delta_index == 0 and visit and visit not in seen_first_token.get(node, set()):
                            seen_first_token.setdefault(node, set()).add(visit)
                            color = "(no color change)"
                            extra = "first token"
                        else:
                            continue  # skip subsequent delta noise
                    elif name == "workflow.node.thought":
                        continue
                    else:
                        continue

                    row = {
                        "client_recv": client_recv,
                        "backend_emit": backend_ts,
                        "delay_ms": delay_ms,
                        "event": name,
                        "node_visit": f"{node}{visit_text}",
                        "color": color,
                        "extra": extra,
                    }
                    rows.append(row)
                    tn = len(rows)
                    print(
                        f"| T{tn} | {fmt(client_recv)} | {fmt(backend_ts) if backend_ts else '-'} | "
                        f"{delay_ms:7.1f} | {name} | {row['node_visit']} | {color} | {extra} |",
                        flush=True,
                    )

                    if name == "workflow.node.finish" and not ev.get("workflow_next_node"):
                        # Terminal event reached
                        break
                else:
                    continue
                break

    sse_close_ts = time.time()
    print("", flush=True)
    print(f"sse_open={fmt(sse_open_ts)}", flush=True)
    print(f"sse_close={fmt(sse_close_ts)}", flush=True)
    print(f"total_sse_duration={sse_close_ts - sse_open_ts:.2f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
