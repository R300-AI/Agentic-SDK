"""What happens to the details of what earlier turns fetched or called.

A tool's reply, or the text of a skill that was taken up, is bulky and was
useful for about one turn. Two turns later it is still in front of the model,
costing what a long answer costs and saying nothing the run still needs.

Deleting it is worse than keeping it. Planning reads the conversation to see
what has already been tried; a conversation with no trace of it is a
conversation where planning fetches it again. So the details go and the fact
stays: this was fetched, this tool was called.

Observed at the assembler, which is where the size of a request is first
known and so the only place the decision can be made.
"""

from __future__ import annotations

from agentic_sdk.memory.in_context import build_module_messages
from agentic_sdk.memory import SKILL_TURN_METADATA_KEY


BULK = "查到的細節，內容夠長，足以把這個請求撐爆預算。" * 8


class _Conversation:
    """A conversation shaped the way the stores shape one, and nothing more."""

    def __init__(self, turns):
        self.turns = turns
        self.metadata = {}

    def as_openai_messages(self, *, include_attachments: bool = False):
        return [{"role": turn.role, "content": turn.content} for turn in self.turns]


class _Turn:
    def __init__(self, role, content, metadata=None):
        self.role = role
        self.content = content
        self.metadata = dict(metadata or {})


def _assembled(turns, budget_tokens=60):
    return build_module_messages(
        _Conversation(turns),
        system_prompt="SYSTEM",
        budget_tokens=budget_tokens,
    )


def _said(messages):
    return " ".join(str(message["content"]) for message in messages)


# --- the details go, the fact stays --------------------------------------


def test_a_tool_reply_from_an_earlier_turn_loses_its_details():
    messages = _assembled([
        _Turn("user", "上一輪的問題"),
        _Turn("tool", BULK),
        _Turn("assistant", "上一輪的回答"),
        _Turn("user", "這一輪的問題"),
    ])

    assert BULK not in _said(messages), "two turns on, the details are paying rent and doing nothing"


def test_the_record_that_it_was_called_survives():
    messages = _assembled([
        _Turn("user", "上一輪的問題"),
        _Turn("tool", BULK),
        _Turn("assistant", "上一輪的回答"),
        _Turn("user", "這一輪的問題"),
    ])

    assert any(message["role"] == "tool" for message in messages), (
        "a conversation with no trace of the call is one where planning calls it again — and "
        "on an endpoint small enough to need this, that is the expensive mistake"
    )


def test_the_text_of_a_skill_taken_up_earlier_loses_its_body():
    messages = _assembled([
        _Turn("user", "上一輪的問題"),
        _Turn("user", BULK, {SKILL_TURN_METADATA_KEY: "退貨處理", "package": "sop"}),
        _Turn("assistant", "上一輪的回答"),
        _Turn("user", "這一輪的問題"),
    ])

    said = _said(messages)
    assert BULK not in said, "a skill is looked up once and then sits there"
    assert "退貨處理" in said, "and which skill it was is what stops it being taken up again"


def test_what_a_person_said_is_never_masked():
    messages = _assembled([
        _Turn("user", "我上一輪就說過我要退貨，" + BULK),
        _Turn("assistant", "上一輪的回答"),
        _Turn("user", "這一輪的問題"),
    ])

    assert "已遮蔽" not in _said(messages), (
        "what a person said is either carried or given up whole; masking it would leave a "
        "conversation that claims they said something and will not say what"
    )
    for message in messages:
        if message["role"] == "user" and "我上一輪" in str(message["content"]):
            assert BULK in str(message["content"]), "carried means carried, not trimmed in place"


# --- this turn is not touched --------------------------------------------


def test_what_this_turn_fetched_keeps_its_details():
    messages = _assembled([
        _Turn("user", "很久以前的閒聊"),
        _Turn("assistant", "很久以前的回答"),
        _Turn("user", "這一輪的問題"),
        _Turn("tool", BULK),
    ])

    assert BULK in _said(messages), (
        "the answer being written now is written from what was just fetched; masking that "
        "is answering with nothing"
    )


def test_what_this_turn_retrieved_is_not_masked():
    messages = build_module_messages(
        _Conversation([_Turn("user", "這一輪的問題")]),
        system_prompt="SYSTEM",
        extra_context={"retrieved_context": BULK},
        budget_tokens=60,
    )

    assert BULK in messages[0]["content"], (
        "the answer being written now is checked against what was just retrieved"
    )


def test_the_evidence_carried_over_from_earlier_turns_is_masked():
    conversation = _Conversation([_Turn("user", "這一輪的問題")])
    conversation.metadata = {"continuity_evidence": BULK}

    messages = build_module_messages(conversation, system_prompt="SYSTEM", budget_tokens=60)

    assert BULK not in messages[0]["content"], (
        "it is every earlier turn's evidence rolled into one block, and it rides in the layer "
        "nothing is ever given up from — left whole it would outlive everything else"
    )
    assert "已遮蔽" in messages[0]["content"], "and planning still sees that it was retrieved"


def test_carried_over_evidence_survives_a_request_that_fits():
    conversation = _Conversation([_Turn("user", "這一輪的問題")])
    conversation.metadata = {"continuity_evidence": BULK}

    messages = build_module_messages(conversation, system_prompt="SYSTEM", budget_tokens=100_000)

    assert BULK in messages[0]["content"], "masking is for a request that does not fit, not for every request"


# --- the record is kept, so it is not then thrown away -------------------


def test_the_record_is_not_given_up_once_masking_has_kept_it():
    messages = _assembled([
        _Turn("user", "第一個問題，" + BULK),
        _Turn("tool", BULK),
        _Turn("assistant", "第一個回答，" + BULK),
        _Turn("user", "這一輪的問題"),
    ], budget_tokens=40)

    said = _said(messages)
    assert "已遮蔽" in said, (
        "masking reduced it to one line precisely so it could stay; giving it up anyway saves "
        "almost nothing and loses the one thing masking exists for"
    )


# --- masking is not a fixed boundary -------------------------------------


def test_nothing_is_masked_while_the_request_still_fits():
    messages = _assembled([
        _Turn("user", "上一輪的問題"),
        _Turn("tool", "很短的結果。"),
        _Turn("assistant", "上一輪的回答"),
        _Turn("user", "這一輪的問題"),
    ], budget_tokens=100_000)

    assert "很短的結果。" in _said(messages), (
        "masking costs the run something, so it is not done to a request that fits"
    )


def test_no_ceiling_means_nothing_is_masked():
    messages = _assembled([
        _Turn("user", "上一輪的問題"),
        _Turn("tool", BULK),
        _Turn("user", "這一輪的問題"),
    ], budget_tokens=None)

    assert BULK in _said(messages), "a limit nobody set must not quietly start masking"


def test_the_oldest_is_masked_first():
    messages = _assembled([
        _Turn("user", "第一個問題"),
        _Turn("tool", "最舊的結果，" + BULK),
        _Turn("assistant", "第一個回答"),
        _Turn("user", "第二個問題"),
        _Turn("tool", "比較新的結果。"),
        _Turn("assistant", "第二個回答"),
        _Turn("user", "這一輪的問題"),
    ], budget_tokens=120)

    said = _said(messages)
    assert "已遮蔽" in said, "the oldest was masked rather than given up"
    assert "最舊的結果" not in said
    assert "比較新的結果。" in said, (
        "what was fetched most recently is the most likely to still matter"
    )


def test_masking_is_tried_before_anything_is_given_up():
    turns = [
        _Turn("user", "上一輪的問題"),
        _Turn("tool", BULK),
        _Turn("assistant", "上一輪的回答"),
        _Turn("user", "這一輪的問題"),
    ]

    messages = _assembled(turns, budget_tokens=60)

    assert "上一輪的問題" in _said(messages), (
        "dropping the details of one fetch made room for the whole conversation, so nothing "
        "had to be given up"
    )


# --- through a real run, with a real store -------------------------------


def test_masking_reaches_the_endpoint_in_a_real_run(tmp_path):
    """The stub above is 1:1 by construction. A real store has to be too."""
    from unittest.mock import patch

    from agentic_sdk import (
        FileMemoryStore,
        Gates,
        GenerativeAction,
        PassThroughPerceive,
        PassThroughPlan,
        PassThroughRetrieve,
        Workflow,
    )
    from support import FoundryOpenAILikeClient

    params = {"api_key": "k", "base_url": "https://example.openai.test/v1", "model": "foundry-openai-like"}
    client = FoundryOpenAILikeClient(action_text="好的。")
    memory = FileMemoryStore(root=str(tmp_path), workflow_name="default", session_id="one")
    memory.append_message("user", "上一輪的問題")
    memory.append_message("tool", BULK)
    memory.append_message("assistant", "上一輪的回答")

    with patch("agentic_sdk.llm.openai_compatible.OpenAI", return_value=client):
        workflow = Workflow(
            perceive=PassThroughPerceive(),
            plan=PassThroughPlan(),
            retrieve=PassThroughRetrieve(),
            action=GenerativeAction(**params),
            gates=Gates(max_prompt_tokens=700),
        )
        workflow.run("這一輪的問題", memory=memory, session_id="one")

    messages = client.last_create_kwargs["messages"]
    # The conversation only. What this turn retrieved rides in the system layer
    # and is not masked — a memory search that matched this old reply surfaced
    # it as evidence for the question being answered now, which is its job.
    conversation = " ".join(
        str(message.get("content", "")) for message in messages if message.get("role") != "system"
    )
    assert BULK not in conversation, (
        "the details of an earlier turn's tool reply must not ride along as conversation"
    )
    assert "已遮蔽" in conversation, (
        "and the record that it was called must, or planning calls it again — which is the "
        "whole reason this masks rather than deletes"
    )
