from agentic_sdk.memory.in_context import InContextMemory, build_module_messages


def test_build_module_messages_includes_continuity_evidence_as_context_not_user_input():
    memory = InContextMemory(metadata={"continuity_evidence": "高足弓對應 SKU 7037439。"})
    memory.append_message("user", "台北信義區")

    messages = build_module_messages(memory, system_prompt="system")

    assert messages[0]["role"] == "system"
    assert "continuity_evidence: 高足弓對應 SKU 7037439。" in messages[0]["content"]
    assert messages[1] == {"role": "user", "content": "台北信義區"}