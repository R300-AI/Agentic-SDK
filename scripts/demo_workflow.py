r"""Phase 2 demo — 直接執行 Workflow,印出節點事件序列。

執行方式:
    .\.venv\Scripts\python.exe scripts\demo_workflow.py

此腳本不啟動 Gateway,單機跑一次工作流並把節點事件列表 dump 出來,
方便驗證 Phase 2 A-01~A-03 的整合是否符合預期。
"""

from __future__ import annotations

import os

# 在 import settings 前先設環境變數,避免 lru_cache 拾到本機 .env 的真實 Azure key
os.environ["WORKFLOW_FORCE_MOCK_FOUNDRY"] = "true"
os.environ["UPSTREAM_API_BASE_URL"] = "http://localhost:9999/v1"

from agentic_sdk.config import Settings  # noqa: E402
from agentic_sdk.observability import (  # noqa: E402
    EVENT_NODE_FINISH,
    EVENT_WORKFLOW_FALLBACK,
    configure_observability,
)
from agentic_sdk.workflow import Workflow  # noqa: E402


def main() -> None:
    settings = Settings(
        _env_file=None,
        workflow_force_mock_foundry=True,
        upstream_api_base_url="http://localhost:9999/v1",
        upstream_api_key="x",
        workflow_max_revisit=2,
        infer_request_timeout_sec=3.0,
    )
    buf = configure_observability(settings)
    wf = Workflow(settings=settings)

    result = wf.run("請說說 TSiP 是什麼")

    print("=" * 60)
    print(f"workflow_id : {result.workflow_id}")
    print(f"aborted     : {result.aborted}")
    print(f"abort_reason: {result.abort_reason}")
    print(f"visit_counts: {result.visit_counts}")
    print(f"final_msg   : {result.final_message[:80]}")
    print()
    print("entries:")
    for e in result.entries:
        print(f"  - {e.type.value:15s} | {e.content[:60]}")
    print()
    print("node.finish events:")
    for e in buf.filter_by_name(EVENT_NODE_FINISH):
        print(
            f"  - {e['workflow_node']:9s} visit={e['workflow_node_visit']} "
            f"next={e.get('workflow_next_node')!s:9s} status={e.get('workflow_status')} "
            f"duration={round(e['duration_ms'], 1)}ms"
        )
    print()
    fallback = buf.filter_by_name(EVENT_WORKFLOW_FALLBACK)
    if fallback:
        print("workflow.fallback events:")
        for e in fallback:
            print(f"  - status={e['workflow_status']} reason={e['workflow_reason']}")


if __name__ == "__main__":
    main()
