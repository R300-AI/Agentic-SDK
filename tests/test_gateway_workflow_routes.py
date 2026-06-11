"""M5-2 — POST /v1/workflow/run 與 GET /v1/workflow/{id}/stream 測試。

策略:
- POST 端走 TestClient,YAML 解析 / 400 錯誤 / 200 成功路徑
- SSE 端的 _sse_event_stream 直接 unit test(避免 TestClient SSE 長連線複雜度);
  終止判定 _is_terminal_event 同樣 unit test
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from agentic_sdk.gateway.routes_workflow import (
    _is_terminal_event,
    _sse_event_stream,
)
from agentic_sdk.observability.events import (
    EVENT_NODE_FINISH,
    EVENT_NODE_START,
    EVENT_WORKFLOW_FALLBACK,
    EVENT_NODE_DELTA,
)


_MINIMAL_YAML = """\
version: "1"
entry: perceive
nodes:
  action:
    type: upstream_completion
gates:
  max_node_hops: 20
  max_revisit: 2
  timeout_sec: 10
"""


# ── POST /v1/workflow/run ────────────────────────────────────────────────────


def test_post_v1_workflow_run_accepts_yaml_returns_stream_url(make_client) -> None:
    with make_client() as client:
        resp = client.post(
            "/v1/workflow/run",
            json={"workflow_yaml": _MINIMAL_YAML, "user_message": "hi"},
        )

    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "workflow_id" in body
    assert len(body["workflow_id"]) == 32  # uuid4 hex
    assert body["stream_url"] == f"/v1/workflow/{body['workflow_id']}/stream"


def test_post_v1_workflow_run_rejects_invalid_yaml(make_client) -> None:
    with make_client() as client:
        resp = client.post(
            "/v1/workflow/run",
            json={"workflow_yaml": "not: valid: yaml: [", "user_message": "hi"},
        )

    assert resp.status_code == 400
    assert "YAML" in resp.json()["detail"]


def test_post_v1_workflow_run_accepts_empty_message_for_attachments(make_client) -> None:
    """純圖片請求允許 user_message 為空字串（M9 多模態語意）。"""
    with make_client() as client:
        resp = client.post(
            "/v1/workflow/run",
            json={"workflow_yaml": _MINIMAL_YAML, "user_message": ""},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "workflow_id" in body and "stream_url" in body


def test_post_v1_workflow_run_rejects_unknown_node_type(make_client) -> None:
    bad_yaml = """\
version: "1"
entry: perceive
nodes:
  action:
    type: nonexistent.fake.Node
"""
    with make_client() as client:
        resp = client.post(
            "/v1/workflow/run",
            json={"workflow_yaml": bad_yaml, "user_message": "hi"},
        )

    assert resp.status_code == 400


# ── _is_terminal_event 終止判斷 ──────────────────────────────────────────────


def test_terminal_event_node_finish_with_next_node_is_not_terminal() -> None:
    ev = {
        "event_name": EVENT_NODE_FINISH,
        "workflow_node": "perceive",
        "workflow_next_node": "plan",
    }
    assert _is_terminal_event(ev) is False


def test_terminal_event_node_finish_without_next_node_is_terminal() -> None:
    ev = {"event_name": EVENT_NODE_FINISH, "workflow_node": "reflect"}
    assert _is_terminal_event(ev) is True


def test_terminal_event_workflow_fallback_is_terminal() -> None:
    ev = {"event_name": EVENT_WORKFLOW_FALLBACK, "workflow_status": "aborted"}
    assert _is_terminal_event(ev) is True


def test_terminal_event_node_start_is_not_terminal() -> None:
    ev = {"event_name": EVENT_NODE_START, "workflow_node": "plan"}
    assert _is_terminal_event(ev) is False


# ── _sse_event_stream 推送邏輯 ───────────────────────────────────────────────


class _FakeRing:
    """模擬 RingBufferHandler 的 snapshot() 介面;測試可動態 append 事件。"""

    def __init__(self) -> None:
        self._events: list[dict[str, Any]] = []

    def append(self, ev: dict[str, Any]) -> None:
        self._events.append(ev)

    def snapshot(self) -> list[dict[str, Any]]:
        return list(self._events)


@pytest.mark.asyncio
async def test_sse_stream_filters_by_workflow_id_and_terminates() -> None:
    ring = _FakeRing()
    workflow_id = "wid-target"

    # 預先 seed 兩個事件:一個屬於別的 workflow,一個是 target 的 node.start
    ring.append({
        "event_name": EVENT_NODE_START,
        "workflow_id": "wid-other",
        "workflow_node": "perceive",
    })
    ring.append({
        "event_name": EVENT_NODE_START,
        "workflow_id": workflow_id,
        "workflow_node": "perceive",
    })

    received: list[bytes] = []

    async def _producer():
        # 0.2s 後 append 終止事件(node.finish 無 next_node)
        await asyncio.sleep(0.2)
        ring.append({
            "event_name": EVENT_NODE_FINISH,
            "workflow_id": workflow_id,
            "workflow_node": "reflect",
        })

    async def _consumer():
        async for chunk in _sse_event_stream(ring, workflow_id):
            received.append(chunk)

    await asyncio.gather(_producer(), asyncio.wait_for(_consumer(), timeout=2.0))

    # 過濾掉 SSE comment （「: 」開頭，例如 ready / keep-alive 心跳）後應收到
    # 2 筆:target 的 node.start + node.finish（終止）
    data_chunks = [c for c in received if c.startswith(b"data:")]
    assert len(data_chunks) == 2
    text_all = b"".join(data_chunks).decode()
    assert "wid-other" not in text_all  # 別的 workflow 不出現
    assert workflow_id in text_all
    assert "perceive" in text_all
    assert "reflect" in text_all


@pytest.mark.asyncio
async def test_sse_stream_first_chunk_is_ready_padding_for_proxy_flush() -> None:
    """前端 onopen 與中間層 chunked transfer 都需要立刻看到第一個 byte，
    否則 Cloud Run / GFE 會等到第一個有意義事件才 flush，導致首次 SSE
    抵達延遲到節點全部跑完。"""
    ring = _FakeRing()
    workflow_id = "wid-ready"
    received: list[bytes] = []

    async def _consumer():
        async for chunk in _sse_event_stream(ring, workflow_id):
            received.append(chunk)
            if len(received) >= 1:
                return

    await asyncio.wait_for(_consumer(), timeout=1.0)
    assert received[0].startswith(b":")  # SSE comment (ready padding)


@pytest.mark.asyncio
async def test_sse_stream_emits_keepalive_when_idle() -> None:
    """當後端無新事件時 SSE 仍需 ≥1Hz 送 keep-alive comment，
    確保 Cloud Run / GFE 不會 buffer 整個 response。"""
    ring = _FakeRing()
    workflow_id = "wid-idle"
    received: list[bytes] = []

    async def _consumer():
        async for chunk in _sse_event_stream(ring, workflow_id):
            received.append(chunk)
            # 收集 2.5 秒,期間沒有任何 data 事件
            if len(received) >= 4:  # ready + 2 keep-alive 至少
                return

    async def _terminate():
        await asyncio.sleep(2.5)
        # 注入終止事件讓 stream 結束
        ring.append({
            "event_name": EVENT_NODE_FINISH,
            "workflow_id": workflow_id,
            "workflow_node": "action",
        })

    await asyncio.gather(_terminate(), asyncio.wait_for(_consumer(), timeout=4.0))

    comment_chunks = [c for c in received if c.startswith(b":")]
    # 2.5 秒內預期至少 ready + 2 個 keep-alive
    assert len(comment_chunks) >= 3, f"expected ≥3 SSE comments, got {len(comment_chunks)}: {received}"


# ── 端到端:真實 workflow.run() → SSE chunks 順序契約 ─────────────────────────


@pytest.mark.asyncio
async def test_sse_chunks_match_node_event_order_for_full_workflow(
    test_settings, respx_mock,
) -> None:
    """
    跑一次完整 5 節點工作流，驗證 SSE consumer 觀察到的事件順序是
    perceive.start → perceive.finish → plan.start → plan.thought →
    plan.finish → retrieve.start → retrieve.finish → plan.start →
    plan.thought → plan.finish → action.start → action.delta×N →
    action.finish。

    這是前端動畫的真實合約：UI 嚴格依照這個順序逐一顯示節點顏色。
    任何事件亂序或缺失，前端動畫就會錯位。
    """
    import httpx
    import json

    from agentic_sdk.observability import (
        EVENT_NODE_START,
        EVENT_NODE_FINISH,
        configure_observability,
    )
    from agentic_sdk.observability.events import (
        EVENT_NODE_THOUGHT,
        EVENT_NODE_DELTA,
    )
    from agentic_sdk.workflow import Workflow
    from agentic_sdk.workflow.llm import MockFoundryClient
    from agentic_sdk.workflow.nodes.action import CompletionAction
    from agentic_sdk.workflow.nodes.plan.react import ReActPlan
    import logging

    handler = configure_observability(test_settings)
    try:
        respx_mock.post("http://upstream.test/v1/chat/completions").mock(
            return_value=httpx.Response(200, json={
                "id": "cmpl-1", "object": "chat.completion", "created": 0,
                "model": "gemma3-4b-npu",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "hello world"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 5, "completion_tokens": 3, "total_tokens": 8},
            })
        )

        wf = Workflow(
            plan=ReActPlan(foundry_client=MockFoundryClient()),
            action=CompletionAction(backend="upstream", settings=test_settings, model="gemma3-4b-npu"),
            settings=test_settings,
        )
        workflow_id = "wid-e2e"
        result = await asyncio.to_thread(wf.run, "hi e2e", workflow_id=workflow_id)
        assert not result.aborted, f"workflow aborted: {result.abort_reason}"

        # 用 _sse_event_stream 把 handler ring 取出（offset=0，因為單一 workflow_id 已分隔）
        received: list[dict[str, Any]] = []
        async for chunk in _sse_event_stream(handler, workflow_id):
            if not chunk.startswith(b"data:"):
                continue
            data_line = next(
                line for line in chunk.split(b"\n\n") if line.startswith(b"data:")
            )
            received.append(json.loads(data_line[len(b"data: "):].decode()))
            # 收到終止 finish（無 next_node）就結束
            if (
                received[-1].get("event_name") == EVENT_NODE_FINISH
                and "workflow_next_node" not in received[-1]
            ):
                break

        # ── 驗證 1：所有事件 workflow_id 一致 ────────────────────
        assert {ev["workflow_id"] for ev in received} == {workflow_id}

        # ── 驗證 2：node.start 與 node.finish 數量配對（含 plan 兩次） ──
        starts = [ev for ev in received if ev["event_name"] == EVENT_NODE_START]
        finishes = [ev for ev in received if ev["event_name"] == EVENT_NODE_FINISH]
        assert len(starts) == 5, f"expected 5 starts, got {len(starts)}: {[s['workflow_node'] for s in starts]}"
        assert len(finishes) == 5

        # ── 驗證 3：節點順序符合預期路徑 ──────────────────────────
        assert [s["workflow_node"] for s in starts] == ["perceive", "plan", "retrieve", "plan", "action"]
        assert [f["workflow_node"] for f in finishes] == ["perceive", "plan", "retrieve", "plan", "action"]

        # ── 驗證 4：每個 start 都緊接其 finish（中間可有 thought / delta） ──
        # 把事件依時間索引拆，逐節點檢查 start 與其對應 finish 之間
        # 不會出現「另一個節點的 start/finish」（嚴格不交錯）
        node_visits = []  # [(node, start_idx, finish_idx), ...]
        open_stack: list[tuple[str, int]] = []
        for idx, ev in enumerate(received):
            if ev["event_name"] == EVENT_NODE_START:
                open_stack.append((ev["workflow_node"], idx))
            elif ev["event_name"] == EVENT_NODE_FINISH:
                assert open_stack, f"finish without matching start at idx {idx}"
                node, start_idx = open_stack.pop()
                assert node == ev["workflow_node"], (
                    f"finish node {ev['workflow_node']} doesn't match open start {node}"
                )
                node_visits.append((node, start_idx, idx))
        assert not open_stack, f"unclosed starts: {open_stack}"

        # ── 驗證 5：Plan 與 Action 之間的 thought / delta 也在對應 span 內 ──
        for node, s_idx, f_idx in node_visits:
            inner = received[s_idx + 1:f_idx]
            for ev in inner:
                name = ev["event_name"]
                if name == EVENT_NODE_THOUGHT:
                    assert node == "plan", f"thought event inside non-plan node {node}"
                elif name == EVENT_NODE_DELTA:
                    # plan 節點以 delta_index=0 作為第一個 token 的時間戳記錨點；
                    # action 節點以 delta 串流回應內容。兩者都合法。
                    assert node in ("action", "plan"), f"delta event inside unexpected node {node}"
                else:
                    # 不應有別的 start/finish
                    assert name not in (EVENT_NODE_START, EVENT_NODE_FINISH), (
                        f"nested {name} inside {node}"
                    )

        # ── 驗證 6：Plan 兩次造訪都有 thought 事件 ────────────────
        plan_visits = [v for v in node_visits if v[0] == "plan"]
        assert len(plan_visits) == 2
        for _, s_idx, f_idx in plan_visits:
            inner_names = [ev["event_name"] for ev in received[s_idx + 1:f_idx]]
            assert EVENT_NODE_THOUGHT in inner_names, (
                f"plan span [{s_idx}..{f_idx}] missing thought event"
            )

        # ── 驗證 7：Action 造訪在 span 內可有 delta（streaming 後端才會）
        #          至少要有對應的 start / finish 配對 ────────────────────
        action_visit = [v for v in node_visits if v[0] == "action"]
        assert len(action_visit) == 1

    finally:
        logging.getLogger("agentic_sdk").removeHandler(handler)

@pytest.mark.asyncio
async def test_plan_start_precedes_thought_in_realtime_sse(
    test_settings, respx_mock,
) -> None:
    """
    「plan 先黃後綠」時序合約的即時驗證。

    現有 test_sse_chunks_match_node_event_order_for_full_workflow 只驗證事件順序——
    它先跑完整個 workflow，再讀 ring buffer，兩個事件都已在 ring 裡，
    無法驗證「LLM 執行期間 plan.start 是否已可被 SSE consumer 讀到」。

    本測試使用 SlowPlanFoundryClient（第一次 plan.chat 延遲 2 秒），
    並行讀 SSE stream，量測：
      - timestamps["plan_start"]: SSE consumer 收到 plan.start 的時刻
      - timestamps["plan_thought"]: SSE consumer 收到 plan.thought 的時刻
    斷言：plan_thought - plan_start >= 1.5s，
    即「consumer 看到黃燈」比「看到 LLM 輸出」早至少 1.5 秒。
    """
    import json
    import time
    import httpx

    from agentic_sdk.observability import configure_observability
    from agentic_sdk.observability.events import EVENT_NODE_START, EVENT_NODE_THOUGHT, EVENT_NODE_FINISH
    from agentic_sdk.workflow import Workflow
    from agentic_sdk.workflow.llm import MockFoundryClient, FoundryResponse
    from agentic_sdk.workflow.nodes.action import CompletionAction
    from agentic_sdk.workflow.nodes.plan.react import ReActPlan
    import logging

    class SlowPlanFoundryClient(MockFoundryClient):
        """第一次 plan 節點的 chat_stream() 延遲 2 秒，模擬慢 LLM；其餘節點不延遲。
        ReActPlan 現在使用 chat_stream，所以需要 override chat_stream 而非 chat。
        """
        def __init__(self) -> None:
            super().__init__()
            self._plan_slow_done = False

        def chat_stream(self, *, system: str, user: str, temperature: float = 0.0,
                        on_delta=None, idle_timeout_sec: float = 30.0,
                        response_format=None):
            if system.startswith("PLAN") and not self._plan_slow_done:
                self._plan_slow_done = True
                time.sleep(2.0)   # 在 asyncio.to_thread 內，time.sleep 不阻塞 event loop
            return super().chat_stream(
                system=system, user=user, temperature=temperature,
                on_delta=on_delta, idle_timeout_sec=idle_timeout_sec,
                response_format=response_format,
            )

    respx_mock.post("http://upstream.test/v1/chat/completions").mock(
        return_value=httpx.Response(200, json={
            "id": "cmpl-timing", "object": "chat.completion", "created": 0,
            "model": "gemma3-4b-npu",
            "choices": [{"index": 0, "message": {"role": "assistant", "content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
        })
    )

    handler = configure_observability(test_settings)
    try:
        wf = Workflow(
            plan=ReActPlan(foundry_client=SlowPlanFoundryClient()),
            action=CompletionAction(backend="upstream", settings=test_settings, model="gemma3-4b-npu"),
            settings=test_settings,
        )
        workflow_id = "wid-timing-realtime"
        timestamps: dict[str, float] = {}
        t0 = time.monotonic()

        async def collect_plan_timing() -> None:
            async for chunk in _sse_event_stream(handler, workflow_id):
                if not chunk.startswith(b"data:"):
                    continue
                data_line = next(
                    line for line in chunk.split(b"\n\n") if line.startswith(b"data:")
                )
                ev = json.loads(data_line[len(b"data: "):])
                name = ev.get("event_name")
                node = ev.get("workflow_node")
                visit = ev.get("workflow_node_visit", 1)
                delta_index = ev.get("delta_index")
                if name == EVENT_NODE_START and node == "plan" and visit == 1:
                    timestamps["plan_start"] = time.monotonic() - t0
                elif name == EVENT_NODE_DELTA and node == "plan" and delta_index == 0:
                    timestamps["plan_first_token"] = time.monotonic() - t0
                elif name == EVENT_NODE_THOUGHT and node == "plan" and visit == 1:
                    timestamps["plan_thought"] = time.monotonic() - t0
                    return  # plan 第一次 thought 到手即可，不用等 action 完成
                # 安全出口：action 跑完代表 workflow 已結束
                elif name == EVENT_NODE_FINISH and node == "action":
                    return

        wf_task = asyncio.ensure_future(
            asyncio.to_thread(wf.run, "slow plan timing test", workflow_id=workflow_id)
        )
        sse_task = asyncio.ensure_future(collect_plan_timing())
        await asyncio.gather(wf_task, sse_task)

        assert "plan_start" in timestamps, "未收到 plan.start（黃燈），SSE 時序測試無效"
        assert "plan_first_token" in timestamps, "未收到 plan delta_index=0（第一個 token），chat_stream on_delta 未正確觸發"
        assert "plan_thought" in timestamps, "未收到 plan.thought（LLM 輸出），SlowMock 未正確觸發"

        # 核心斷言：T1（黃燈）< T2（第一個 token）
        # 即「plan 先黃，LLM 才開始產第一個字」
        gap_start_to_first = timestamps["plan_first_token"] - timestamps["plan_start"]
        assert gap_start_to_first >= 1.5, (
            f"plan.start → first_token 間距僅 {gap_start_to_first:.2f}s，"
            "期望 ≥ 1.5s（代表黃燈已亮超過 1.5 秒才收到第一個 token）"
        )

        # 順序斷言：T2 ≤ T3（第一個 token 不晚於 thought 完成）
        # Mock 因同步執行兩者可同 tick，用 <= 而非 <
        assert timestamps["plan_first_token"] <= timestamps["plan_thought"], (
            f"first_token({timestamps['plan_first_token']:.3f}s) 不應晚於 plan.thought({timestamps['plan_thought']:.3f}s)"
        )
    finally:
        logging.getLogger("agentic_sdk").removeHandler(handler)