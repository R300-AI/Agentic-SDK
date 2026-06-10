"""M9 + M10 — 多模態使用者輸入 + Retrieve vision_query 測試。

涵蓋:
- Attachment dataclass round-trip
- WorkflowState 帶 attachments
- Foundry / Upstream Action 在 state.attachments 非空時改用 OpenAI multimodal content
- /v1/workflow/run 接 attachments 透傳
- SemanticRetrieve 的 vision_query hook
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from agentic_sdk.context import ContextEntry, ContextEntryType
from agentic_sdk.workflow.attachments import Attachment
from agentic_sdk.workflow.node import WorkflowState


_TINY_PNG = (
    "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR4nGNiAAIAAAUAAen63NgAAAAASUVORK5CYII="
)


# ── M9-1 ─────────────────────────────────────────────────────────────────────


def test_attachment_from_dict_round_trip() -> None:
    raw = {"kind": "image", "mime": "image/png", "data_url": _TINY_PNG, "name": "foot.png"}
    a = Attachment.from_dict(raw)
    assert a.kind == "image"
    assert a.mime == "image/png"
    assert a.name == "foot.png"
    assert a.to_dict() == raw


def test_state_carries_attachments() -> None:
    s = WorkflowState(user_message="x")
    assert s.attachments == []
    s.attachments.append(Attachment(kind="image", mime="image/png", data_url=_TINY_PNG))
    assert len(s.attachments) == 1


# ── M9-3 Foundry / Upstream Action 多模態 messages ───────────────────────────


def test_foundry_action_builds_multimodal_content_when_attachments_present() -> None:
    from agentic_sdk.workflow.nodes.action.foundry_completion import _build_messages

    state = WorkflowState(user_message="這雙鞋適合我嗎")
    state.attachments = [Attachment(kind="image", mime="image/png", data_url=_TINY_PNG)]
    msgs = _build_messages(state, "你是門市專員")

    user_msg = msgs[-1]
    assert user_msg["role"] == "user"
    assert isinstance(user_msg["content"], list)
    types = [p["type"] for p in user_msg["content"]]
    assert types == ["text", "image_url"]
    assert user_msg["content"][1]["image_url"]["url"] == _TINY_PNG


def test_foundry_action_keeps_string_content_when_no_attachments() -> None:
    from agentic_sdk.workflow.nodes.action.foundry_completion import _build_messages

    state = WorkflowState(user_message="哈囉")
    msgs = _build_messages(state, "sys")
    assert isinstance(msgs[-1]["content"], str)
    assert msgs[-1]["content"] == "哈囉"


def test_upstream_action_builds_multimodal_content_when_attachments_present() -> None:
    from agentic_sdk.workflow.nodes.action.upstream_completion import _build_messages

    state = WorkflowState(user_message="看看這張")
    state.attachments = [Attachment(kind="image", mime="image/jpeg", data_url=_TINY_PNG)]
    msgs = _build_messages(state, "sys")

    assert len(msgs) == 1
    content = msgs[0]["content"]
    assert isinstance(content, list)
    assert content[0]["type"] == "text"
    assert "sys" in content[0]["text"]
    assert "看看這張" in content[0]["text"]
    assert content[1]["type"] == "image_url"
    assert content[1]["image_url"]["url"] == _TINY_PNG


def test_upstream_action_string_path_unchanged_without_attachments() -> None:
    from agentic_sdk.workflow.nodes.action.upstream_completion import _build_messages

    state = WorkflowState(user_message="哈囉")
    msgs = _build_messages(state, "sys")
    assert msgs == [{"role": "user", "content": "sys\n\nuser 輸入:\n哈囉"}]


# ── M9-2 Gateway 透 attachments(以 /v1/chat/completions 走 multimodal 入口) ──


def test_chat_completions_extracts_multimodal_content() -> None:
    from agentic_sdk.gateway.routes_chat import _extract_user_input

    messages = [
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "看看這張鞋款"},
                {"type": "image_url", "image_url": {"url": _TINY_PNG}},
            ],
        }
    ]
    text, atts = _extract_user_input(messages)
    assert text == "看看這張鞋款"
    assert len(atts) == 1
    assert atts[0].kind == "image"
    assert atts[0].mime == "image/png"
    assert atts[0].data_url == _TINY_PNG


def test_chat_completions_falls_back_to_string_content() -> None:
    from agentic_sdk.gateway.routes_chat import _extract_user_input

    text, atts = _extract_user_input([{"role": "user", "content": "純文字"}])
    assert text == "純文字"
    assert atts == []


# ── M10-3 SemanticRetrieve vision_query hook ─────────────────────────────────


def test_retrieve_uses_vision_query_to_rewrite_search_text() -> None:
    from agentic_sdk.knowledge import KnowledgeBase, KnowledgeEntry
    from agentic_sdk.workflow.nodes.retrieve import SemanticRetrieve

    kb = KnowledgeBase(
        name="test",
        entries=[
            KnowledgeEntry(id="k1", title="氣墊跑鞋", content="緩衝吸震，寬楦"),
            KnowledgeEntry(id="k2", title="商務皮鞋", content="正式場合"),
        ],
    )

    vq = MagicMock(return_value="氣墊跑鞋 寬楦")

    retrieve = SemanticRetrieve(knowledge_base=kb, vision_query=vq)
    state = WorkflowState(user_message="幫我看看")
    state.attachments = [Attachment(kind="image", mime="image/png", data_url=_TINY_PNG)]

    out = retrieve(state)
    entry = out["context_updates"][0]
    meta = entry.metadata

    vq.assert_called_once_with("幫我看看", state.attachments)
    assert meta["vision_augmented"] is True
    assert meta["vision_query_text"] == "氣墊跑鞋 寬楦"
    assert meta["kb_hit_count"] >= 1
    assert meta["kb_scores"][0]["id"] == "k1"


def test_retrieve_skips_vision_query_when_no_attachments() -> None:
    from agentic_sdk.knowledge import KnowledgeBase, KnowledgeEntry
    from agentic_sdk.workflow.nodes.retrieve import SemanticRetrieve

    kb = KnowledgeBase(name="t", entries=[KnowledgeEntry(id="x", title="a", content="b")])
    vq = MagicMock(return_value="should not be used")

    retrieve = SemanticRetrieve(knowledge_base=kb, vision_query=vq)
    state = WorkflowState(user_message="純文字查詢")
    out = retrieve(state)

    vq.assert_not_called()
    assert "vision_augmented" not in out["context_updates"][0].metadata


def test_retrieve_vision_query_falls_back_when_builder_raises() -> None:
    from agentic_sdk.knowledge import KnowledgeBase, KnowledgeEntry
    from agentic_sdk.workflow.nodes.retrieve import SemanticRetrieve

    kb = KnowledgeBase(name="t", entries=[KnowledgeEntry(id="x", title="a", content="b")])
    vq = MagicMock(side_effect=RuntimeError("boom"))

    retrieve = SemanticRetrieve(knowledge_base=kb, vision_query=vq)
    state = WorkflowState(user_message="保底文字")
    state.attachments = [Attachment(kind="image", mime="image/png", data_url=_TINY_PNG)]

    out = retrieve(state)
    meta = out["context_updates"][0].metadata
    assert meta["vision_augmented"] is False


# ── M9-2 /v1/workflow/run 透 attachments ─────────────────────────────────────

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


def test_v1_workflow_run_accepts_attachments(make_client) -> None:
    with make_client() as client:
        resp = client.post(
            "/v1/workflow/run",
            json={
                "workflow_yaml": _MINIMAL_YAML,
                "user_message": "看這張",
                "attachments": [
                    {"kind": "image", "mime": "image/png", "data_url": _TINY_PNG}
                ],
            },
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "workflow_id" in body
    assert body["stream_url"].startswith("/v1/workflow/")


def test_v1_workflow_run_rejects_malformed_attachment(make_client) -> None:
    with make_client() as client:
        resp = client.post(
            "/v1/workflow/run",
            json={
                "workflow_yaml": _MINIMAL_YAML,
                "user_message": "x",
                "attachments": [{"kind": "image"}],  # 缺 mime / data_url
            },
        )
    assert resp.status_code == 400
    assert "attachments" in resp.json()["detail"]
