from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from flask import session

from agentic_sdk.core import WorkflowResult, WorkflowState
from agentic_sdk.core.events import default_events_schema
from playground.app import create_app
from playground.routes import builder as builder_routes
from playground.routes import runner as runner_routes
from playground.services import key_vault_config
from playground.services import model_endpoints
from playground.services import runner_service
from playground.services.aihub_bridge import store_loaded_agent
from playground.services.source_builder import build_default_python_source, build_python_source_from_builder_choice, config_from_source
from playground.services.workflow_spec import apply_builder_step, default_spec
from playground.services.workflow_reachability import reachable_workflow_roles


def test_local_fae_can_skip_key_vault_loading(monkeypatch):
    monkeypatch.setenv("PLAYGROUND_SKIP_KEY_VAULT_LOAD", "true")
    monkeypatch.setattr(
        key_vault_config,
        "_access_token",
        lambda: (_ for _ in ()).throw(AssertionError("Key Vault access should be skipped")),
    )

    assert key_vault_config.load_key_vault_secrets() == {}


def test_builder_choices_map_to_runtime_modules():
    source = build_default_python_source()

    for choice, expected_module in {
        "pass_through": "PassThroughPerceive",
        "text": "TextPerceive",
        "text_image": "TextImagePerceive",
    }.items():
        config = config_from_source(build_python_source_from_builder_choice("input_type", choice, source))
        assert config.perceive_module == expected_module
        assert "perceive" in reachable_workflow_roles(config)

    for choice, expected_module in {
        "none": "PassThroughRetrieve",
        "keyword": "KeywordRetrieve",
        "semantic": "SemanticRetrieve",
    }.items():
        config = config_from_source(build_python_source_from_builder_choice("retrieve_policy", choice, source))
        assert config.retrieve_module == expected_module
        assert "retrieve" in reachable_workflow_roles(config)

    free_text = config_from_source(build_python_source_from_builder_choice("output_format", "free_text", source))
    interactive = config_from_source(build_python_source_from_builder_choice("output_format", "interactive", source))

    assert free_text.action_module == "GenerativeAction"
    assert interactive.action_module == "ToolCallAction"
    assert "action" in reachable_workflow_roles(free_text)
    assert "action" in reachable_workflow_roles(interactive)


def test_endpoint_binding_missing_is_distinct_from_missing_credentials(monkeypatch):
    monkeypatch.setenv("PLAYGROUND_FAST_MODEL", "gpt-test")
    monkeypatch.setenv("PLAYGROUND_FAST_BASE_URL", "https://models.example")
    monkeypatch.setenv("PLAYGROUND_FAST_API_KEY", "test-key")

    with __import__("pytest").raises(model_endpoints.MissingEndpointBinding):
        model_endpoints.endpoint_params_for_role("perceive", {})

    monkeypatch.delenv("PLAYGROUND_FAST_API_KEY")
    with __import__("pytest").raises(model_endpoints.MissingEndpointCredentials):
        model_endpoints.endpoint_params_for_role("perceive", {"perceive": "playground-fast"})


def test_interactive_action_contract_roundtrips_to_boolean_tool_schema():
    source = build_python_source_from_builder_choice("output_format", "interactive", None)
    source = build_python_source_from_builder_choice(
        "action",
        {
            "response_instruction": "先說明建議，再詢問是否提交。",
            "api_contracts": "",
            "interaction_trigger": "使用者需要確認下一步時呼叫。",
            "api_method": "POST",
            "api_url": "https://example.com/submit",
            "component_fields": "是否提交 = 使用者是否確認提交（資料類型：是/否)",
        },
        source,
    )

    config = config_from_source(source)
    field = config.action_tools[0]["function"]["parameters"]["properties"]["是否提交"]

    assert config.action_module == "ToolCallAction"
    assert field["type"] == "boolean"
    assert config.action_tools[0]["function"]["parameters"]["required"] == ["是否提交"]


def test_interactive_panel_submission_releases_pending_state():
    runner_directory = Path(__file__).parents[1] / "playground" / "static" / "js" / "runner"
    surface_source = (runner_directory / "result-surface.js").read_text(encoding="utf-8")
    runner_source = (runner_directory / "runner-page.js").read_text(encoding="utf-8")

    assert 'confirmButton.disabled = true;' in surface_source
    assert 'form.addEventListener("runner:tool-call-complete"' in surface_source
    assert 'status.textContent = "已送出選擇。";' in surface_source
    assert 'event.target?.dispatchEvent(new CustomEvent("runner:tool-call-complete"));' in runner_source


def test_runner_execute_routes_forward_attachment_payloads(monkeypatch):
    app = create_app()
    app.config.update(TESTING=True)
    captured = {}

    def fake_execute_python_source(_python_source, **kwargs):
        captured.update(kwargs)
        return {
            "status": "completed",
            "final_message": "ok",
            "tool_calls": [],
            "tool_call_panels": [],
            "debug_messages": [],
            "process_events": [],
            "result": {"message": "ok"},
            "scene_profile": {},
        }

    monkeypatch.setattr(runner_routes, "execute_python_source", fake_execute_python_source)

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["python_source"] = build_default_python_source()
        response = client.post(
            "/playground/run/execute",
            json={
                "message": "請判讀圖片",
                "attachments": [
                    {
                        "kind": "image",
                        "name": "report.png",
                        "media_type": "image/png",
                        "content": "data:image/png;base64,abc",
                    }
                ],
            },
        )

    assert response.status_code == 200
    assert captured["attachments"] == [
        {
            "kind": "image",
            "name": "report.png",
            "media_type": "image/png",
            "content": "data:image/png;base64,abc",
        }
    ]


def test_atomic_runner_metadata_update_compiles_the_current_v2_spec():
    app = create_app()
    app.config.update(TESTING=True)
    spec = default_spec()

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["workflow_spec"] = spec
            session["python_source"] = build_default_python_source()

        response = client.post(
            "/playground/run/metadata",
            json={
                "name": "Metadata contract verification",
                "description": "Keep name and description in one v2 mutation.",
            },
        )
        preview = client.get("/playground/source/preview")

    assert response.status_code == 200
    assert response.get_json()["workflow_summary"]["name"] == "Metadata contract verification"
    assert preview.status_code == 200
    assert 'workflow_name="Metadata contract verification"' in preview.get_data(as_text=True)
    assert "Keep name and description in one v2 mutation." in preview.get_data(as_text=True)


def test_semantic_builder_upload_unblocks_review_and_reaches_runner(monkeypatch):
    app = create_app()
    app.config.update(TESTING=True)
    captured = {}

    monkeypatch.setattr(
        builder_routes,
        "endpoint_state",
        lambda _python_source, _endpoint_selections: {"requirements": [], "configured_roles": {}},
    )

    def fake_execute_python_source(_python_source, **kwargs):
        captured.update(kwargs)
        return {
            "status": "completed",
            "final_message": "ok",
            "tool_calls": [],
            "tool_call_panels": [],
            "debug_messages": [],
            "process_events": [],
            "result": {"message": "ok"},
            "scene_profile": {},
        }

    monkeypatch.setattr(runner_routes, "execute_python_source", fake_execute_python_source)

    with app.test_client() as client:
        semantic_response = client.post("/playground/builder/state", json={"step": "retrieve_policy", "choice": "semantic"})
        semantic_payload = semantic_response.get_json()
        retrieve_review = next(item for item in semantic_payload["builder_review_state"] if item["step_key"] == "retrieve_policy")

        upload_response = client.post(
            "/playground/builder/uploads",
            data={"files": (BytesIO(b"product information"), "products.md")},
            content_type="multipart/form-data",
        )
        upload_payload = upload_response.get_json()
        uploaded_review = next(item for item in upload_payload["builder_review_state"] if item["step_key"] == "retrieve_policy")

        run_response = client.post("/playground/run/execute", json={"message": "查詢產品"})

    assert semantic_response.status_code == 200
    assert retrieve_review["completed"] is False
    assert "參考文件" in retrieve_review["detail"]
    assert upload_response.status_code == 200
    assert upload_payload["semantic_support_files"] == ["products.md"]
    assert uploaded_review["completed"] is True
    assert run_response.status_code == 200
    assert captured["semantic_sources"] and captured["semantic_sources"][0].endswith("source-files")
    assert captured["semantic_saved_path"]


def test_runner_edit_settings_navigation_preserves_current_draft():
    app = create_app()
    app.config.update(TESTING=True)
    source = build_python_source_from_builder_choice("input_type", "text_image", build_default_python_source())

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["python_source"] = source
            session["builder_has_user_config"] = True

        runner_response = client.get("/playground/run")
        builder_response = client.get("/playground/builder")

        with client.session_transaction() as session:
            preserved_config = config_from_source(session["python_source"])

    assert runner_response.status_code == 200
    assert builder_response.status_code == 200
    assert preserved_config.perceive_module == "TextImagePerceive"


def test_aihub_readonly_deep_link_without_loaded_source_does_not_dead_end(monkeypatch):
    app = create_app()
    app.config.update(TESTING=True)

    def fake_load_public_config(agent_id, **_kwargs):
        return {
            "loaded": True,
            "agent_id": agent_id,
            "agent_name": "Shared Agent",
            "python_source": build_python_source_from_builder_choice("input_type", "text", build_default_python_source()),
        }

    monkeypatch.setattr("playground.routes.entry.load_public_config", fake_load_public_config)

    with app.test_client() as client:
        response = client.get("/playground?mode=aihub_readonly&agent_id=agent-1", follow_redirects=True)
        with client.session_transaction() as session:
            loaded_config = config_from_source(session["python_source"])

    assert response.status_code == 200
    assert loaded_config.perceive_module == "TextPerceive"
    assert b"\xe8\xa9\xa6\xe8\xb7\x91 Agent" in response.data


def test_anonymous_start_clears_prior_loaded_agent_state():
    app = create_app()
    app.config.update(TESTING=True)

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["mode"] = "aihub_editable"
            session["agent_id"] = "old-agent"
            session["python_source"] = build_python_source_from_builder_choice("input_type", "text_image", build_default_python_source())
            session["builder_upload_id"] = "old-upload"

        response = client.post("/playground/start/anonymous")
        with client.session_transaction() as session:
            config = config_from_source(session["python_source"])
            session_snapshot = dict(session)

    assert response.status_code == 302
    assert response.location.endswith("/playground/builder")
    assert session_snapshot["mode"] == "anonymous"
    assert session_snapshot["source_origin"] == "manual_new"
    assert "agent_id" not in session_snapshot
    assert "builder_upload_id" not in session_snapshot
    assert config.perceive_module == "PassThroughPerceive"


def test_runner_without_source_redirects_to_builder_without_dead_end():
    app = create_app()
    app.config.update(TESTING=True)

    with app.test_client() as client:
        response = client.get("/playground/run")
        follow_response = client.get(response.location)

    assert response.status_code == 302
    assert response.location.endswith("/playground/builder")
    assert follow_response.status_code == 200


def test_source_preview_roundtrip_preserves_current_draft():
    app = create_app()
    app.config.update(TESTING=True)
    source = build_python_source_from_builder_choice("input_type", "text", build_default_python_source())

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["python_source"] = source
            session["builder_has_user_config"] = True

        source_response = client.get("/playground/source")
        runner_response = client.get("/playground/run")
        with client.session_transaction() as session:
            preserved_config = config_from_source(session["python_source"])

    assert source_response.status_code == 200
    assert runner_response.status_code == 200
    assert preserved_config.perceive_module == "TextPerceive"


def test_v2_source_preview_preserves_renamed_workflow():
    app = create_app()
    app.config.update(TESTING=True)
    spec = apply_builder_step(default_spec(), "name", "Contract verification")

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["workflow_spec"] = spec
            session["python_source"] = build_default_python_source()

        response = client.get("/playground/source/preview")
        with client.session_transaction() as session:
            compiled_source = session["python_source"]

    assert response.status_code == 200
    assert 'workflow_name="Contract verification"' in compiled_source
    assert 'workflow_name="Contract verification"' in response.get_data(as_text=True)


def test_loading_v2_agent_compiles_canonical_execution_source():
    app = create_app()
    app.config.update(TESTING=True)
    spec = apply_builder_step(default_spec(), "output_format", "free_text")

    with app.test_request_context():
        store_loaded_agent(
            {
                "agent_id": "agent-1",
                "agent_name": "Stored Agent",
                "python_source": build_default_python_source(),
                "endpoint_bindings": {"action": "gpt-54"},
                "workflow_spec": spec,
                "runner_presentation": {},
            }
        )
        config = config_from_source(session["python_source"])

    assert config.action_module == "GenerativeAction"


def test_runner_starter_questions_use_session_metadata_not_python_source():
    app = create_app()
    app.config.update(TESTING=True)
    source = build_python_source_from_builder_choice("memory_type", {"starter_questions": "如何上架？"}, build_default_python_source())

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["python_source"] = source
            session["builder_form_state"] = {
                "choices": {},
                "values": {"memory_type": {"starter_questions": "如何上架？\n如何部署？"}},
            }

        source_response = client.get("/playground/source/preview")
        runner_response = client.get("/playground/run")

    assert source_response.status_code == 200
    assert "RUNNER_CONFIG" not in source_response.get_data(as_text=True)
    assert "starter_questions" not in source_response.get_data(as_text=True)
    assert runner_response.status_code == 200
    assert "如何上架？" in runner_response.get_data(as_text=True)
    assert "如何部署？" in runner_response.get_data(as_text=True)


def test_streaming_execute_route_forwards_attachment_payloads(monkeypatch):
    app = create_app()
    app.config.update(TESTING=True)
    captured = {}

    def fake_stream_python_source_execution(_python_source, **kwargs):
        captured.update(kwargs)
        yield {
            "type": "final",
            "execution": {
                "status": "completed",
                "final_message": "ok",
                "tool_calls": [],
                "tool_call_panels": [],
                "debug_messages": [],
                "process_events": [],
                "result": {"message": "ok"},
                "scene_profile": {},
            },
        }

    monkeypatch.setattr(runner_routes, "stream_python_source_execution", fake_stream_python_source_execution)

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["python_source"] = build_default_python_source()
        response = client.post(
            "/playground/run/execute/stream",
            json={
                "message": "請判讀圖片",
                "attachments": [
                    {
                        "kind": "image",
                        "name": "report.png",
                        "media_type": "image/png",
                        "content": "data:image/png;base64,abc",
                    }
                ],
            },
        )
        response.get_data(as_text=True)

    assert response.status_code == 200
    assert captured["attachments"][0]["content"] == "data:image/png;base64,abc"


def test_streaming_execute_route_forwards_finish_fields_as_ndjson_process_events(monkeypatch):
    app = create_app()
    app.config.update(TESTING=True)
    schema = default_events_schema()

    def standard_event(module, phase, **extra):
        return {
            "type": "stage",
            "phase": phase,
            "status": "running" if phase == "start" else "done",
            "module": module,
            "label": schema[module]["label"],
            "schema": schema[module],
            "metadata": {
                "schema_label": schema[module]["label"],
                "schema_fields": list(schema[module]["fields"]),
                "schema_metadata": dict(schema[module]["metadata"]),
            },
            "visit_id": f"workflow-1:{module}:1",
            **extra,
        }

    class FakeWorkflow:
        def run(self, _message, *, event_callback=None, **_kwargs):
            assert event_callback is not None
            state = WorkflowState(user_message="測試輸入", workflow_id="workflow-1", session_id="session-1")
            events = [
                standard_event("perceive", "start"),
                standard_event("perceive", "finish", fields=[{"field": "summary", "value": '包含 "引號" 的理解'}], state=state),
                standard_event("plan", "start"),
                standard_event("plan", "finish", fields=[{"field": "thought", "value": "需要先整理來源"}], state=state),
            ]
            for event in events:
                event_callback(event)
            return WorkflowResult(
                workflow_id="workflow-1",
                session_id="session-1",
                final_message="完成",
                visit_counts={"perceive": 1, "plan": 1, "action": 1},
            )

    monkeypatch.setattr(runner_service, "_workflow_from_source", lambda *_args, **_kwargs: FakeWorkflow())

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["python_source"] = build_default_python_source()
        response = client.post(
            "/playground/run/execute/stream",
            json={"message": "測試輸入"},
        )
        lines = [
            json.loads(line)
            for line in response.get_data(as_text=True).splitlines()
            if line.strip()
        ]

    process_events = [item["event"] for item in lines if item["type"] == "process"]
    final = next(item["result"] for item in lines if item["type"] == "final")

    assert response.status_code == 200
    assert [event["description"] for event in process_events if event["role"] == "perceive"] == [
        "正在讀取使用者輸入，整理成後續步驟可使用的內容。",
        '目前理解為：包含 "引號" 的理解',
    ]
    assert [event["description"] for event in process_events if event["role"] == "plan"] == [
        "正在判斷這次需要先整理來源，或可以直接準備回覆。",
        "判斷依據：需要先整理來源",
    ]
    assert final["process_events"] == process_events


def test_runner_process_event_rejects_legacy_stage_event_without_schema():
    config = config_from_source(build_default_python_source())

    try:
        runner_service._process_event_for_workflow_event(
            config,
            {
                "type": "stage",
                "phase": "start",
                "status": "running",
                "module": "perceive",
                "label": "理解輸入",
            },
        )
    except TypeError as exc:
        assert "schema" in str(exc)
    else:
        raise AssertionError("legacy stage events without schema must be rejected")


def test_runner_process_event_rejects_legacy_stage_alias_without_module():
    config = config_from_source(build_default_python_source())
    schema = default_events_schema()["perceive"]

    try:
        runner_service._process_event_for_workflow_event(
            config,
            {
                "type": "stage",
                "phase": "start",
                "status": "running",
                "stage": "perceive",
                "label": "理解輸入",
                "schema": schema,
            },
        )
    except ValueError as exc:
        assert "module" in str(exc)
    else:
        raise AssertionError("legacy stage alias events without module must be rejected")


def test_tool_call_panel_does_not_fallback_for_information_intent(monkeypatch):
    source = build_python_source_from_builder_choice("output_format", "interactive", None)
    source = build_python_source_from_builder_choice(
        "action",
        {
            "interaction_trigger": "需要使用者確認時呼叫。",
            "api_method": "POST",
            "api_url": "https://example.com/confirm",
            "component_fields": "是否確認 = 使用者是否確認（資料類型：是/否)",
        },
        source,
    )

    class FakeWorkflow:
        def run(self, *_args, **_kwargs):
            return WorkflowResult(workflow_id="workflow-1", final_message="目前結果顯示資料仍需補充。", entities={})

    monkeypatch.setattr(runner_service, "_workflow_from_source", lambda *_args, **_kwargs: FakeWorkflow())

    result = runner_service.execute_python_source(source, message="請分析目前結果")

    assert result["status"] == "completed"
    assert result["tool_calls"] == []
    assert result["tool_call_panels"] == []


def test_tool_call_panel_does_not_fallback_for_optional_followup_question(monkeypatch):
    source = build_python_source_from_builder_choice("output_format", "interactive", None)
    source = build_python_source_from_builder_choice(
        "action",
        {
            "interaction_trigger": "需要使用者確認下一步時呼叫。",
            "api_method": "POST",
            "api_url": "https://example.com/confirm",
            "component_fields": "是否確認 = 使用者是否確認（資料類型：是/否)",
        },
        source,
    )

    class FakeWorkflow:
        def run(self, *_args, **_kwargs):
            return WorkflowResult(
                workflow_id="workflow-1",
                final_message="目前足測結果屬正常足弓。若你願意，我可以整理成門市話術版。",
                entities={},
            )

    monkeypatch.setattr(runner_service, "_workflow_from_source", lambda *_args, **_kwargs: FakeWorkflow())

    result = runner_service.execute_python_source(source, message="這份報告代表我的腳有什麼問題嗎？")

    assert result["tool_call_panels"] == []


def test_tool_call_panel_falls_back_for_reservation_confirmation(monkeypatch):
    source = build_python_source_from_builder_choice("output_format", "interactive", None)
    source = build_python_source_from_builder_choice(
        "action",
        {
            "interaction_trigger": "需要使用者確認下一步時呼叫。",
            "api_method": "POST",
            "api_url": "https://example.com/confirm",
            "component_fields": "是否確認 = 使用者是否確認（資料類型：是/否)",
        },
        source,
    )

    class FakeWorkflow:
        def run(self, *_args, **_kwargs):
            return WorkflowResult(
                workflow_id="workflow-1",
                final_message="商品名稱：科技鞋墊 通用型\n商品編號：291090970\n請問我要先為您登記保留這款推薦嗎？",
                entities={},
            )

    monkeypatch.setattr(runner_service, "_workflow_from_source", lambda *_args, **_kwargs: FakeWorkflow())

    result = runner_service.execute_python_source(source, message="好，那就幫我保留你推薦的那款。")

    assert len(result["tool_call_panels"]) == 1
    assert result["tool_call_panels"][0]["title"] == "請問我要先為您登記保留這款推薦嗎？"


def test_tool_call_panel_allows_data_limitations_after_recommendation(monkeypatch):
    source = build_python_source_from_builder_choice("output_format", "interactive", None)
    source = build_python_source_from_builder_choice(
        "action",
        {
            "interaction_trigger": "需要使用者確認下一步時呼叫。",
            "api_method": "POST",
            "api_url": "https://example.com/confirm",
            "component_fields": "是否確認 = 使用者是否確認（資料類型：是/否)",
        },
        source,
    )

    class FakeWorkflow:
        def run(self, *_args, **_kwargs):
            return WorkflowResult(
                workflow_id="workflow-1",
                final_message="商品名稱：科技鞋墊 通用型\n商品編號：291090970\n資料限制：目前庫存資料不足，需由門市確認。\n您要我先幫您保留或購買這款推薦嗎？",
                entities={},
            )

    monkeypatch.setattr(runner_service, "_workflow_from_source", lambda *_args, **_kwargs: FakeWorkflow())

    result = runner_service.execute_python_source(source, message="請直接幫我推薦一款合適的鞋墊。")

    assert len(result["tool_call_panels"]) == 1
    assert result["tool_call_panels"][0]["title"] == "您要我先幫您保留或購買這款推薦嗎？"


def test_tool_call_panel_falls_back_for_decision_intent_without_model_tool_call(monkeypatch):
    source = build_python_source_from_builder_choice("output_format", "interactive", None)
    source = build_python_source_from_builder_choice(
        "action",
        {
            "interaction_trigger": "需要使用者確認下一步時呼叫。",
            "api_method": "POST",
            "api_url": "https://example.com/confirm",
            "component_fields": "是否確認 = 使用者是否確認（資料類型：是/否)",
        },
        source,
    )

    class FakeWorkflow:
        def run(self, *_args, **_kwargs):
            return WorkflowResult(workflow_id="workflow-1", final_message="我建議採用第一個方案。是否要進入下一步？", entities={})

    monkeypatch.setattr(runner_service, "_workflow_from_source", lambda *_args, **_kwargs: FakeWorkflow())

    result = runner_service.execute_python_source(source, message="請推薦下一步")

    assert result["status"] == "completed"
    assert result["tool_calls"] == []
    assert len(result["tool_call_panels"]) == 1
    assert result["tool_call_panels"][0]["title"] == "我建議採用第一個方案。是否要進入下一步？"
    assert result["tool_call_panels"][0]["fields"][0]["label"] == "你的選擇"


def test_tool_call_panel_uses_final_confirmation_line_for_long_recommendation(monkeypatch):
    source = build_python_source_from_builder_choice("output_format", "interactive", None)
    source = build_python_source_from_builder_choice(
        "action",
        {
            "interaction_trigger": "需要使用者確認下一步時呼叫。",
            "api_method": "POST",
            "api_url": "https://example.com/confirm",
            "component_fields": "是否確認 = 使用者是否確認（資料類型：是/否)",
        },
        source,
    )

    class FakeWorkflow:
        def run(self, *_args, **_kwargs):
            return WorkflowResult(
                workflow_id="workflow-1",
                final_message="推薦結果\n我建議採用第一個方案。\n\n**要幫你保留這項推薦嗎？**",
                entities={},
            )

    monkeypatch.setattr(runner_service, "_workflow_from_source", lambda *_args, **_kwargs: FakeWorkflow())

    result = runner_service.execute_python_source(source, message="請推薦下一步")

    assert result["tool_call_panels"][0]["title"] == "要幫你保留這項推薦嗎？"


def test_tool_call_panel_does_not_fallback_when_recommendation_needs_more_input(monkeypatch):
    source = build_python_source_from_builder_choice("output_format", "interactive", None)
    source = build_python_source_from_builder_choice(
        "action",
        {
            "interaction_trigger": "需要使用者確認下一步時呼叫。",
            "api_method": "POST",
            "api_url": "https://example.com/confirm",
            "component_fields": "是否確認 = 使用者是否確認（資料類型：是/否)",
        },
        source,
    )

    class FakeWorkflow:
        def run(self, *_args, **_kwargs):
            return WorkflowResult(workflow_id="workflow-1", final_message="請提供更多資料後，我才能推薦合適方案。", entities={})

    monkeypatch.setattr(runner_service, "_workflow_from_source", lambda *_args, **_kwargs: FakeWorkflow())

    result = runner_service.execute_python_source(source, message="請推薦下一步")

    assert result["status"] == "completed"
    assert result["tool_calls"] == []
    assert result["tool_call_panels"] == []


def test_tool_call_panel_uses_model_message_as_user_facing_question(monkeypatch):
    source = build_python_source_from_builder_choice("output_format", "interactive", None)
    source = build_python_source_from_builder_choice(
        "action",
        {
            "interaction_trigger": "需要使用者確認時呼叫。",
            "api_method": "POST",
            "api_url": "https://example.com/confirm",
            "component_fields": "是否確認 = 使用者是否確認（資料類型：是/否)",
        },
        source,
    )

    class FakeWorkflow:
        def run(self, *_args, **_kwargs):
            return WorkflowResult(
                workflow_id="workflow-1",
                final_message="我建議先採用支撐型鞋墊。是否要購買這項推薦？",
                entities={
                    "latest_tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "submit_api_1", "arguments": '{"是否確認": true}'},
                        }
                    ]
                },
            )

    monkeypatch.setattr(runner_service, "_workflow_from_source", lambda *_args, **_kwargs: FakeWorkflow())

    result = runner_service.execute_python_source(source, message="請推薦鞋墊")

    assert result["status"] == "completed"
    assert result["tool_call_panels"][0]["title"] == "我建議先採用支撐型鞋墊。是否要購買這項推薦？"
    assert "https://example.com/confirm" not in result["tool_call_panels"][0]["description"]
    assert result["tool_call_panels"][0]["fields"][0]["type"] == "boolean"
    assert result["tool_call_panels"][0]["fields"][0]["label"] == "你的選擇"
    assert result["tool_call_panels"][0]["fields"][0]["description"] == "請根據上方問題選擇是否繼續。"
    assert result["tool_call_panels"][0]["fields"][0]["choices"] == [
        {"value": True, "label": "是", "description": "我同意進行這個下一步。"},
        {"value": False, "label": "否", "description": "我暫時不進行這個下一步。"},
    ]
    assert result["tool_call_panels"][0]["api"] == {"method": "POST", "url": "https://example.com/confirm"}