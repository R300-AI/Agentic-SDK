"""
Measure workflow node timing for lanew.png + the foot-report prompt.

Outputs one T row per relevant event. Each row starts with the color change
that should happen at that T, then states the work that follows.
"""
from __future__ import annotations

import base64
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from agentic_sdk.config import get_settings
from agentic_sdk.observability import configure_observability
from agentic_sdk.observability.events import (
    EVENT_NODE_DELTA,
    EVENT_NODE_FINISH,
    EVENT_NODE_START,
)
from agentic_sdk.workflow import Workflow
from agentic_sdk.workflow.attachments import Attachment

IMAGE_PATH = ROOT / "lanew.png"
PROMPT = "\U0001f4cf \u6211\u6709\u8db3\u6e2c\u5831\u544a\u60f3\u8aee\u8a62"


def fmt(ts: float) -> str:
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S.%f")[:-3]


def action_for_start(node: str, visit: int) -> str:
    if node == "perceive":
        return "RuleBasePerceive parses user message and attachment metadata"
    if node == "plan" and visit == 1:
        return "ReActPlan calls Azure Foundry; TTFT belongs to Plan processing"
    if node == "plan":
        return "ReActPlan revisits after retrieve and decides the next route"
    if node == "retrieve":
        return "Retrieve gathers context and sends it back to Plan"
    if node == "reflect":
        return "Reflect checks quality and decides whether to continue"
    if node == "action":
        return "Action calls the response model and streams the final answer"
    return "Node starts work"


def action_for_finish(node: str, visit: int, next_node: str | None) -> str:
    if next_node:
        return f"{node} finished; route payload to {next_node}"
    return f"{node} finished; workflow is complete"


def main() -> int:
    if not IMAGE_PATH.exists():
        print(f"ERROR: missing image: {IMAGE_PATH}")
        return 1

    image_b64 = base64.b64encode(IMAGE_PATH.read_bytes()).decode("ascii")
    attachment = Attachment(
        kind="image",
        mime="image/png",
        data_url=f"data:image/png;base64,{image_b64}",
        name="lanew.png",
    )

    settings = get_settings()
    handler = configure_observability(settings)
    workflow_id = f"timing-{int(time.time())}"
    workflow = Workflow(settings=settings)

    rows: list[dict] = []
    seen_plan_first_token: set[int] = set()
    seen_action_first_token = False
    stop_flag = threading.Event()

    def add_row(ts: float, event: str, node: str, visit: int | None, color_first: str, after: str) -> None:
        tn = len(rows) + 1
        rows.append({
            "tn": tn,
            "ts": ts,
            "event": event,
            "node": node,
            "visit": visit,
            "color_first": color_first,
            "after": after,
        })
        visit_text = "" if visit is None else f"#{visit}"
        print(
            f"| T{tn} | {fmt(ts)} | {event} | {node}{visit_text} | {color_first} | {after} |",
            flush=True,
        )

    def monitor() -> None:
        nonlocal seen_action_first_token
        seen = 0
        while not stop_flag.is_set():
            snapshot = handler.snapshot()
            new_events = snapshot[seen:]
            seen = len(snapshot)

            for ev in new_events:
                if ev.get("workflow_id") != workflow_id:
                    continue

                event_name = ev.get("event_name")
                node = ev.get("workflow_node")
                if not node:
                    continue
                visit = ev.get("workflow_node_visit")

                if event_name == EVENT_NODE_START:
                    add_row(
                        ev["ts"],
                        event_name,
                        node,
                        visit,
                        f"{node}: gray -> yellow",
                        action_for_start(node, int(visit or 1)),
                    )
                elif event_name == EVENT_NODE_FINISH:
                    next_node = ev.get("workflow_next_node")
                    add_row(
                        ev["ts"],
                        event_name,
                        node,
                        visit,
                        f"{node}: yellow -> green",
                        action_for_finish(node, int(visit or 1), next_node),
                    )
                elif event_name == EVENT_NODE_DELTA:
                    delta_index = ev.get("delta_index")
                    if node == "plan" and delta_index == 0:
                        plan_visit = int(visit or 1)
                        if plan_visit not in seen_plan_first_token:
                            seen_plan_first_token.add(plan_visit)
                            add_row(
                                ev["ts"],
                                event_name,
                                node,
                                plan_visit,
                                "no color change; plan remains yellow",
                                "Azure Foundry produced the first Plan token",
                            )
                    elif node == "action" and delta_index == 0 and not seen_action_first_token:
                        seen_action_first_token = True
                        add_row(
                            ev["ts"],
                            event_name,
                            node,
                            int(visit or 1),
                            "no color change; action remains yellow",
                            "Response model produced the first final-answer token",
                        )

            time.sleep(0.02)

    print(f"workflow_id={workflow_id}", flush=True)
    print("input_image=lanew.png", flush=True)
    print("input_prompt=U+1F4CF 我有足測報告想諮詢", flush=True)
    print("", flush=True)
    print("| Tn | Time | Backend event | Node visit | First step at T: color change | Work after color change |", flush=True)
    print("|---|---:|---|---|---|---|", flush=True)

    thread = threading.Thread(target=monitor, daemon=True)
    thread.start()
    started = time.time()
    try:
        result = workflow.run(PROMPT, workflow_id=workflow_id, attachments=[attachment])
    finally:
        time.sleep(0.5)
        stop_flag.set()
        thread.join(timeout=2)

    rows.sort(key=lambda row: row["ts"])
    print(f"\nrun_started={fmt(started)}", flush=True)
    print(f"run_finished={fmt(time.time())}", flush=True)
    print(f"aborted={result.aborted}", flush=True)
    if result.aborted:
        print(f"abort_reason={result.abort_reason}", flush=True)

    plan_starts = [row for row in rows if row["event"] == EVENT_NODE_START and row["node"] == "plan"]
    plan_first_tokens = [row for row in rows if row["event"] == EVENT_NODE_DELTA and row["node"] == "plan"]
    plan_finishes = [row for row in rows if row["event"] == EVENT_NODE_FINISH and row["node"] == "plan"]
    for idx, start_row in enumerate(plan_starts):
        if idx < len(plan_first_tokens) and idx < len(plan_finishes):
            first_row = plan_first_tokens[idx]
            finish_row = plan_finishes[idx]
            print(
                f"\nplan_visit_{idx + 1}: "
                f"start_to_first_token={first_row['ts'] - start_row['ts']:.2f}s, "
                f"first_token_to_finish={finish_row['ts'] - first_row['ts']:.2f}s, "
                f"start_to_finish={finish_row['ts'] - start_row['ts']:.2f}s"
                ,
                flush=True,
            )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
