from playground.services.source_builder import build_default_python_source, build_python_source_from_builder_choice, get_workflow_summary
from playground.services.source_parser import parse_supported_source
from playground.services.runner_service import execute_python_source


def _sample_workflow_source(workflow_name: str, profile_hint: str | None = None) -> str:
    hint_line = f"# Playground V2 profile hint: {profile_hint}\n" if profile_hint else ""
    return (
        "from agentic_sdk import Workflow\n\n"
        f"{hint_line}"
        "workflow = Workflow(\n"
        f"    workflow_name={workflow_name!r},\n"
        ")\n"
    )


def test_parse_supported_default_source_name():
    parsed = parse_supported_source(build_default_python_source())

    assert parsed.workflow_name == "Customer Helper"
    assert parsed.supported_subset is True
    assert "WorkflowSettings" not in build_default_python_source()


def test_parse_generated_profile_hint_for_summary():
    python_source = _sample_workflow_source("Review Summary Helper")
    parsed = parse_supported_source(python_source)
    summary = get_workflow_summary(python_source)

    assert parsed.profile_hint == "Summary"
    assert summary.name == "審閱摘要 Agent"
    assert summary.can_roundtrip is True


def test_parse_structured_action_profile_hint():
    python_source = _sample_workflow_source("Structured Result Helper")
    parsed = parse_supported_source(python_source)
    summary = get_workflow_summary(python_source)

    assert parsed.profile_hint == "Structured Result"
    assert summary.template == "結構化結果"


def test_parse_readme_starter_template_hints():
    openai_source = _sample_workflow_source("OpenAI Client Helper")
    custom_source = _sample_workflow_source("Custom Action Helper")

    assert parse_supported_source(openai_source).workflow_name == "OpenAI Client Helper"
    assert get_workflow_summary(openai_source).template == "模型回覆"
    assert parse_supported_source(custom_source).workflow_name == "Custom Action Helper"
    assert get_workflow_summary(custom_source).template == "自訂處理"


def test_execute_marks_unsupported_source_without_running_arbitrary_code():
    python_source = """from agentic_sdk import Workflow

exec("raise RuntimeError('should not run')")
workflow = Workflow()
"""

    result = execute_python_source(python_source, message="hello")

    assert result["status"] == "completed"
    assert result["source_execution"]["supported_subset"] is False
    assert result["source_execution"]["workflow_name"] == "playground_preview"
    assert result["result"]["evidence"] == ["來源：目前輸入內容。", "外部資料：尚未加入。"]


def test_retrieve_builder_ignores_legacy_semantic_weight_fields():
    source = build_python_source_from_builder_choice("retrieve_policy", "semantic", None)
    source = build_python_source_from_builder_choice(
        "retrieve",
        {
            "top_k": "7",
            "similarity_weight": "0.6",
            "recency_weight": "0.2",
            "importance_weight": "0.2",
        },
        source,
    )

    assert "SemanticRetrieve(" in source
    assert "top_k=" not in source
    assert "similarity_weight" not in source
    assert "recency_weight" not in source
    assert "importance_weight" not in source


def test_keyword_retrieve_builder_emits_only_keyword_items_without_retrieve_fallback():
    source = build_python_source_from_builder_choice(
        "retrieve",
        {"keyword_pairs": "保固 = 提供保固期限與申請方式", "fallback": "沒有支援資料。"},
        None,
    )
    retrieve_block = source.split("retrieve=KeywordRetrieve(", 1)[1].split("\n    ),", 1)[0]

    assert "KeywordRetrieve(" in source
    assert '"保固"' in source
    assert "fallback=" not in retrieve_block