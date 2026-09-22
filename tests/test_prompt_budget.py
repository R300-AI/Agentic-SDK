"""What a module gives up when what it wants to send will not fit.

Observed through ``Workflow.run()`` with a fake endpoint that records the
messages it was handed, and — where the point is the shape of one request
rather than the shape of a run — against the assembler directly.

The order here is not the order messages are sent in. They are sent in the
order the conversation happened. It is the order they are given up in.
"""

from __future__ import annotations

from unittest.mock import patch

from agentic_sdk import (
    GateConfig,
    Gates,
    GenerativeAction,
    PassThroughPerceive,
    PassThroughPlan,
    PassThroughRetrieve,
    Workflow,
    WorkflowConfig,
    build_workflow,
)
from agentic_sdk.memory.in_context import _within, build_module_messages, tokens_in_request

from support import FoundryOpenAILikeClient


LLM_PARAMS = {
    "api_key": "test-key",
    "base_url": "https://example.openai.test/v1",
    "model": "foundry-openai-like",
}


def _answering_workflow(**workflow_kwargs):
    client = FoundryOpenAILikeClient(action_text="好的。")
    with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=client):
        workflow = Workflow(
            perceive=PassThroughPerceive(),
            plan=PassThroughPlan(),
            retrieve=PassThroughRetrieve(),
            action=GenerativeAction(**LLM_PARAMS),
            **workflow_kwargs,
        )
    return workflow, client


def _sent(client) -> list[dict]:
    return list(client.last_create_kwargs.get("messages", []))


def _said(client) -> str:
    return " ".join(str(message.get("content", "")) for message in _sent(client))


def _long_conversation(workflow, client, turns: int = 12) -> None:
    for index in range(turns):
        workflow.run(f"第{index}個問題，內容夠長好讓這段對話撐得起來測試。", session_id="one")


def _conversation(*roles_and_texts) -> list[dict]:
    return [{"role": role, "content": text} for role, text in roles_and_texts]


# --- what a ceiling does, and does not do --------------------------------


def test_without_a_ceiling_nothing_is_dropped():
    workflow, client = _answering_workflow()
    _long_conversation(workflow, client)

    assert "第0個問題" in _said(client), "a limit nobody set must not quietly start cutting"


def test_a_ceiling_drops_the_oldest_of_the_conversation_first():
    workflow, client = _answering_workflow(gates=Gates(max_prompt_tokens=400))
    _long_conversation(workflow, client)

    said = _said(client)
    assert "第11個問題" in said, "what was just asked is the last thing to go"
    assert "第0個問題" not in said, "and the oldest of the conversation is the first"


def test_a_ceiling_is_honoured_as_far_as_the_conversation_can_pay_for_it():
    workflow, client = _answering_workflow(gates=Gates(max_prompt_tokens=400))
    _long_conversation(workflow, client)

    roles = [message["role"] for message in _sent(client)]
    assert roles == ["system", "user"], (
        "the conversation pays until there is none of it left, and what is left is the "
        "instructions and the question"
    )


def test_a_ceiling_no_conversation_can_pay_for_is_exceeded_rather_than_met():
    workflow, client = _answering_workflow(gates=Gates(max_prompt_tokens=10))
    _long_conversation(workflow, client, turns=3)

    assert tokens_in_request(_sent(client)) > 10, (
        "a ceiling is what the conversation is measured against, not a promise about the "
        "request: cutting into the instructions or the question would change what is asked"
    )
    assert "第2個問題" in _said(client), "so the question is still there to be answered"


def test_a_ceiling_of_zero_is_a_ceiling_and_not_an_absence():
    messages = build_module_messages(None, system_prompt="SYSTEM", latest_user_message="IGNORED")
    messages[1:] = _conversation(
        ("user", "很久以前的閒聊。"),
        ("assistant", "先前的回答。"),
        ("user", "我要退貨"),
    )

    assert len(_within(messages, 0, None)) == 2, (
        "zero is the strictest ceiling somebody can set, not a way of saying they set none"
    )


def test_the_evidence_outlives_the_conversation():
    workflow, client = _answering_workflow(gates=Gates(max_prompt_tokens=400))
    _long_conversation(workflow, client)

    said = _said(client)
    assert "第0個問題" not in said, "this only says something once the cutting has started"
    assert "retrieved_context" in said, (
        "the answer is checked against its evidence, so dropping that fails the check by construction"
    )


def test_the_system_prompt_is_never_given_up():
    workflow, client = _answering_workflow(gates=Gates(max_prompt_tokens=80))
    _long_conversation(workflow, client, turns=6)

    sent = _sent(client)
    assert len([message for message in sent if message["role"] == "user"]) < 6, (
        "six questions under an 80-token ceiling must have been cut down"
    )
    assert sent[0]["role"] == "system"
    assert sent[0]["content"], "there is no answer worth giving without the instructions for it"


# --- what is protected, and why the last message is the wrong mark -------


def test_the_question_survives_a_skill_appended_after_it():
    messages = build_module_messages(
        None,
        system_prompt="SYSTEM",
        latest_user_message="IGNORED",
    )
    messages[1:] = _conversation(
        ("user", "很久以前的閒聊，內容夠長，足以把這個請求撐爆預算。" * 6),
        ("assistant", "先前的回答。"),
        ("user", "我要退貨"),
        ("user", "skill: 退貨處理流程"),
    )

    kept = _within(messages, 60, None)
    said = " ".join(str(message["content"]) for message in kept)

    assert "我要退貨" in said, (
        "a planning module appends a skill as a user message, so the last user message "
        "is not the question"
    )
    assert "很久以前的閒聊" not in said, "and the conversation behind it is what pays for keeping it"


def test_a_tool_reply_is_not_left_without_its_call():
    messages = build_module_messages(None, system_prompt="SYSTEM", latest_user_message="IGNORED")
    messages[1:] = _conversation(
        ("assistant", "第一次查詢。"),
        ("tool", "第一次查詢的結果，內容夠長，足以把這個請求撐爆預算。" * 6),
        ("user", "那庫存呢"),
        ("assistant", "第二次查詢。"),
        ("tool", "第二次查詢的結果。"),
    )

    kept = _within(messages, 60, None)

    assert [message["role"] for message in kept].count("tool") <= 1
    for index, message in enumerate(kept):
        if message["role"] == "tool":
            assert kept[index - 1]["role"] == "assistant", (
                "a tool reply on its own is an answer to nothing, and some endpoints reject it"
            )


# --- what the memory remembers rides above all of it ---------------------


def test_what_is_remembered_rides_in_the_system_layer():
    messages = build_module_messages(
        None,
        system_prompt="SYSTEM",
        index_lines=["先前談過保固與退貨。"],
        latest_user_message="鞋號",
    )

    assert "先前談過保固與退貨。" in messages[0]["content"], (
        "the index says what can be looked up, so planning must see it every time"
    )


def test_the_index_is_never_trimmed():
    messages = build_module_messages(None, system_prompt="SYSTEM", latest_user_message="IGNORED")
    messages[1:] = _conversation(
        *[("user", f"第{index}段對話，內容夠長好讓這段對話撐得起來測試。") for index in range(12)]
    )
    messages[0] = {
        "role": "system",
        "content": "SYSTEM\n\nremembered_topics:\n"
        + "\n".join(f"- 主題{index}的一句話說明。" for index in range(40)),
    }

    kept = _within(messages, 200, None)
    said = " ".join(str(message["content"]) for message in kept)

    assert "第0段對話" not in said, "this only says something once the cutting has started"
    assert "主題39" in kept[0]["content"] and "主題0" in kept[0]["content"], (
        "planning does not look up a topic it cannot see, so cutting the index loses the memory itself"
    )


# --- what a request costs ------------------------------------------------


def test_the_tools_a_module_offers_count_against_the_budget():
    tools = [{"type": "function", "function": {"name": "book", "description": "預約試穿", "parameters": {}}}]

    without = tokens_in_request([{"role": "user", "content": "鞋號"}], tools=None)
    with_tools = tokens_in_request([{"role": "user", "content": "鞋號"}], tools=tools)

    assert with_tools > without, "ten tool definitions are not free just because they ride in another field"


def test_offering_tools_costs_the_conversation_room():
    tools = [
        {"type": "function", "function": {"name": f"tool{index}", "description": "一個用途說明。" * 8, "parameters": {}}}
        for index in range(6)
    ]
    conversation = _conversation(
        ("user", "很久以前的閒聊。"),
        ("assistant", "先前的回答。"),
        ("user", "我要退貨"),
    )

    def kept_with(tools_offered):
        messages = build_module_messages(None, system_prompt="SYSTEM", latest_user_message="IGNORED")
        messages[1:] = [dict(message) for message in conversation]
        return _within(messages, 80, tools_offered)

    assert len(kept_with(tools)) < len(kept_with(None)), (
        "the room tool definitions take is room the conversation no longer has"
    )


def test_an_image_does_not_count_as_the_words_it_is_made_of():
    data_uri = "data:image/png;base64," + "A" * 20000
    with_image = tokens_in_request(
        [{"role": "user", "content": [{"type": "text", "text": "這雙"}, {"type": "image_url", "image_url": {"url": data_uri}}]}]
    )

    assert with_image < 100, (
        "counting a data URI as text would throw the whole conversation away to make room for one photograph"
    )


# --- where the ceiling is declared ---------------------------------------


def test_the_budget_is_declared_with_the_rest_of_the_assembly():
    config = WorkflowConfig(gates=GateConfig(max_prompt_tokens=1234))
    workflow = build_workflow(config)

    assert workflow.gates.max_prompt_tokens == 1234


def test_the_ceiling_is_off_unless_somebody_sets_it():
    assert Gates().max_prompt_tokens is None
    assert GateConfig().max_prompt_tokens is None


def test_the_ceiling_tells_a_memory_when_to_collect_itself():
    from agentic_sdk.core.workflow import _let_memory_collect_itself

    class Collecting:
        compaction_threshold_tokens = None

    class AlreadyTold:
        compaction_threshold_tokens = 999

    class CannotCollect:
        pass

    unset, told, cannot = Collecting(), AlreadyTold(), CannotCollect()
    for memory in (unset, told, cannot):
        _let_memory_collect_itself(memory, 400)

    assert unset.compaction_threshold_tokens == 400, (
        "cutting at the seam loses what was said; collecting it into a topic keeps it"
    )
    assert told.compaction_threshold_tokens == 999, "somebody chose that number for that memory"
    assert not hasattr(cannot, "compaction_threshold_tokens"), (
        "a memory that cannot collect itself is not given a number it has no use for"
    )


def test_a_ceiling_tells_a_file_memory_to_collect_itself(tmp_path, monkeypatch):
    from agentic_sdk import FileMemoryStore

    monkeypatch.setattr(
        "agentic_sdk.memory.file_store.resolve_openai_client",
        lambda *_args, **_kwargs: FoundryOpenAILikeClient(action_text="前面談的是保固與退貨。"),
    )
    memory = FileMemoryStore(root=str(tmp_path), workflow_name="w", session_id="s", **LLM_PARAMS)
    workflow, client = _answering_workflow(gates=Gates(max_prompt_tokens=200))

    for index in range(12):
        workflow.run(f"第{index}個問題，內容夠長好讓這段對話撐得起來測試。", memory=memory, session_id="s")

    assert [entry for entry in memory._entries if entry.tier == "topic"], (
        "a ceiling that only cut messages at the seam would lose what was said; the point of "
        "collecting it is that it stays as a topic"
    )
