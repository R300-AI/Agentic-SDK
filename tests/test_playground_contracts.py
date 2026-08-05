from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

from flask import session

from agentic_sdk.core import ContextEntry, ContextEntryType, WorkflowResult, WorkflowState
from agentic_sdk.core.events import default_events_schema
from playground.app import create_app
from playground.routes import builder as builder_routes
from playground.routes import runner as runner_routes
from playground.services import key_vault_config
from playground.services import model_endpoints
from playground.services import runner_service
from playground.services import semantic_ingestion
from playground.services.runner_conversation import RunnerConversationState
from playground.services.aihub_bridge import store_loaded_agent
from playground.services.source_builder import BuilderSourceConfig, build_default_python_source, build_python_source_from_builder_choice, config_from_source
from playground.services.workflow_spec import apply_builder_step, compile_python_source, default_spec
from playground.services.workflow_reachability import reachable_workflow_roles


def test_key_vault_skip_flag_does_not_bypass_typed_settings(monkeypatch):
    monkeypatch.setenv("PLAYGROUND_SKIP_KEY_VAULT_LOAD", "true")

    settings = key_vault_config._settings_from_values(
        {
            "AI-HUB-BASE-URL": "https://aihub.example",
            "AI-HUB-PLAYGROUND-ORIGIN": "https://playground.example",
        }
    )

    assert settings.ai_hub.base_url == "https://aihub.example"


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


def test_environment_endpoint_discovery_is_not_supported(monkeypatch):
    monkeypatch.setenv("PLAYGROUND_FAST_MODEL", "gpt-test")
    monkeypatch.setenv("PLAYGROUND_FAST_BASE_URL", "https://models.example")
    monkeypatch.setenv("PLAYGROUND_FAST_API_KEY", "test-key")

    with __import__("pytest").raises(model_endpoints.MissingEndpointBinding):
        model_endpoints.endpoint_params_for_role("perceive", {})

    with __import__("pytest").raises(model_endpoints.MissingEndpointBinding):
        model_endpoints.endpoint_params_for_role("perceive", {"perceive": "playground-fast"})


def test_partial_key_vault_endpoint_family_is_rejected():
    with __import__("pytest").raises(key_vault_config.KeyVaultConfigurationError, match="GPT-54-MODEL"):
        key_vault_config._settings_from_values(
            {
                "AI-HUB-BASE-URL": "https://aihub.example",
                "AI-HUB-PLAYGROUND-ORIGIN": "https://playground.example",
                "GPT-54-API-KEY": "key",
                "GPT-54-BASE-URL": "https://models.example",
            }
        )


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
    assert 'const hasBooleanValue = field.value === true || field.value === false' in surface_source
    assert 'hasBooleanValue && (value ? booleanValue : !booleanValue)' in surface_source
    assert 'const missingRequiredFields = panel.fields.filter((field) => field.required && !hasToolCallValue(argumentsPayload[field.name]));' in surface_source
    assert 'if (missingRequiredFields.length)' in surface_source
    assert 'function hasToolCallValue(value)' in surface_source
    assert 'event.target?.dispatchEvent(new CustomEvent("runner:tool-call-complete"));' in runner_source


def test_runner_does_not_refresh_ai_hub_credentials_in_background():
    runner_source = (Path(__file__).parents[1] / "playground" / "static" / "js" / "runner" / "runner-page.js").read_text(encoding="utf-8")

    assert 'postJson("/playground/aihub/config/save")' in runner_source
    assert 'postJson("/playground/aihub/session/refresh")' not in runner_source
    assert "refreshAiHubSession" not in runner_source


def test_runner_commits_conversation_after_stream_completion():
    runner_source = (Path(__file__).parents[1] / "playground" / "static" / "js" / "runner" / "runner-page.js").read_text(encoding="utf-8")

    assert 'postJson("/playground/run/conversation/commit", { conversation_update: update })' in runner_source
    assert "await commitConversationUpdate(result.conversation_update);" in runner_source


def test_runner_execution_stream_emits_one_final_event(monkeypatch):
    def fake_execute(_python_source, *, process_observer=None, **_kwargs):
        if process_observer is not None:
            process_observer({"stage": "perceive", "status": "completed"})
            process_observer({"stage": "action", "status": "completed"})
        return {"status": "completed", "final_message": "單一最終回覆"}

    monkeypatch.setattr(runner_service, "execute_python_source", fake_execute)

    events = list(runner_service.stream_python_source_execution("workflow = Workflow()", message="測試"))

    assert [event["type"] for event in events].count("final") == 1
    assert events[-1] == {"type": "final", "execution": {"status": "completed", "final_message": "單一最終回覆"}}


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


def test_runner_conversation_state_restores_ordered_turns_and_resets_for_new_workflow():
    first = RunnerConversationState.for_workflow("workflow = 'first'")
    restored = RunnerConversationState.from_dict(
        {
            **first.as_dict(),
            "turns": [
                {"role": "user", "content": "我有高足弓"},
                {"role": "assistant", "content": "推薦科技鞋墊 加強型，SKU 7037439。"},
            ],
        },
        python_source="workflow = 'first'",
    )

    memory = restored.memory(workflow_name="LaNew")

    assert [turn.role for turn in memory.turns] == ["user", "assistant"]
    assert memory.turns[-1].content == "推薦科技鞋墊 加強型，SKU 7037439。"
    assert RunnerConversationState.from_dict(restored.as_dict(), python_source="workflow = 'changed'").turns == ()


def test_runner_conversation_memory_exposes_prior_retrieval_evidence_to_modules():
    source = build_default_python_source()
    state = RunnerConversationState.from_dict(
        {
            **RunnerConversationState.for_workflow(source).as_dict(),
            "retrieval_evidence": "高足弓適用：科技鞋墊 加強型，SKU 7037439。",
        },
        python_source=source,
    )

    memory = state.memory(workflow_name="LaNew")

    assert memory.metadata["continuity_evidence"] == "高足弓適用：科技鞋墊 加強型，SKU 7037439。"


def test_runner_execution_injects_conversation_memory_into_workflow(monkeypatch):
    captured = {}
    source = build_default_python_source()
    state = RunnerConversationState.from_dict(
        {
            **RunnerConversationState.for_workflow(source).as_dict(),
            "turns": [
                {"role": "user", "content": "我有高足弓"},
                {"role": "assistant", "content": "推薦科技鞋墊 加強型，SKU 7037439。"},
            ],
        },
        python_source=source,
    )

    class FakeWorkflow:
        def run(self, _message, **kwargs):
            captured.update(kwargs)
            memory = kwargs["memory"]
            memory.append_message("user", _message)
            memory.append_message("assistant", "已保留高足弓推薦。")
            return WorkflowResult(workflow_id="workflow", final_message="已保留高足弓推薦。", memory=memory)

    monkeypatch.setattr(runner_service, "_workflow_from_source", lambda *_args, **_kwargs: FakeWorkflow())

    execution = runner_service.execute_python_source(source, message="台北信義區", conversation_state=state)

    assert captured["session_id"] == state.conversation_id
    assert [turn.content for turn in captured["memory"].turns[:2]] == ["我有高足弓", "推薦科技鞋墊 加強型，SKU 7037439。"]
    assert execution["conversation_update"]["turns"][-1]["content"] == "已保留高足弓推薦。"


def test_tool_continuation_extends_the_same_conversation_memory():
    source = build_default_python_source()
    conversation = RunnerConversationState.from_dict(
        {
            **RunnerConversationState.for_workflow(source).as_dict(),
            "retrieval_evidence": "科技鞋墊 加強型，SKU 7037439。",
            "turns": [
                {"role": "user", "content": "高足弓適合哪款？"},
                {"role": "assistant", "content": "推薦科技鞋墊 加強型。"},
            ],
        },
        python_source=source,
    )
    captured = {}

    class FakeAction:
        def __call__(self, state):
            captured["memory"] = state.memory
            captured["evidence"] = state.entities.get("latest_retrieved_content")
            return {"next_module": None, "payload": {"latest_final_message": "已送出門市協助需求。"}}

    class FakeWorkflow:
        workflow_name = "LaNew"
        memory_store = None
        modules = {"action": FakeAction()}

    result = runner_service._run_tool_submission_continuation(
        FakeWorkflow(),
        BuilderSourceConfig(workflow_name="LaNew"),
        "使用者已送出互動選項。\n工具名稱：門市協助",
        {"function_name": "門市協助", "arguments": {"是否通知": True}, "api_result": {"skipped": True}},
        conversation_state=conversation,
        attachments=[],
        process_observer=None,
    )

    assert [turn.role for turn in captured["memory"].turns] == ["user", "assistant", "user", "assistant"]
    assert "是否通知" in captured["memory"].turns[2].content
    assert "7037439" in captured["evidence"]
    assert result.memory.turns[-1].content == "已送出門市協助需求。"
    assert conversation.update_from_result(result).retrieval_evidence == "科技鞋墊 加強型，SKU 7037439。"


def test_runner_conversation_commit_persists_one_expected_revision(monkeypatch):
    app = create_app()
    app.config.update(TESTING=True)
    source = build_default_python_source()

    with app.test_client() as client:
        with client.session_transaction() as current_session:
            current_session["python_source"] = source
            initial = RunnerConversationState.for_workflow(source)
            current_session["runner_conversation"] = initial.as_dict()

        update = {
            **initial.as_dict(),
            "revision": 1,
            "turns": [
                {"role": "user", "content": "高足弓適合哪款？"},
                {"role": "assistant", "content": "科技鞋墊 加強型，SKU 7037439。"},
            ],
        }
        committed = client.post("/playground/run/conversation/commit", json={"conversation_update": update})
        conflict = client.post("/playground/run/conversation/commit", json={"conversation_update": update})

        with client.session_transaction() as current_session:
            stored = current_session["runner_conversation"]

    assert committed.status_code == 200
    assert committed.json["committed"] is True
    assert stored["turns"][-1]["content"] == "科技鞋墊 加強型，SKU 7037439。"
    assert conflict.status_code == 409
    assert conflict.json["conflict"] is True


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


def test_semantic_builder_upload_rejects_archives_before_saving():
    app = create_app()
    app.config.update(TESTING=True)

    with app.test_client() as client:
        response = client.post(
            "/playground/builder/uploads",
            data={"files": (BytesIO(b"not an archive"), "catalog.zip")},
            content_type="multipart/form-data",
        )
        with client.session_transaction() as current_session:
            upload_id = current_session.get("builder_upload_id")

    assert response.status_code == 400
    assert response.json["updated"] is False
    assert response.json["rejected_files"] == [
        {"name": "catalog.zip", "reason": "不支援壓縮檔；請先解壓縮後上傳其中需要建立知識庫的文件。"}
    ]
    assert not upload_id


def test_semantic_ingestion_rejects_oversized_file_without_persisting(monkeypatch, tmp_path):
    monkeypatch.setattr(semantic_ingestion, "_MAX_UPLOAD_BYTES", 3)

    result = semantic_ingestion.ingest_semantic_upload(
        filename="catalog.md",
        stream=BytesIO(b"four"),
        target_dir=tmp_path,
    )

    assert result.accepted is False
    assert result.reason == "檔案超過知識庫上傳大小限制。"
    assert list(tmp_path.iterdir()) == []


def test_builder_semantic_upload_ui_advertises_only_supported_formats():
    template = (Path(__file__).parents[1] / "playground" / "templates" / "builder.html").read_text(encoding="utf-8")
    script = (Path(__file__).parents[1] / "playground" / "static" / "js" / "builder" / "builder-page.js").read_text(encoding="utf-8")

    assert 'accept=".md,.txt,.csv' in template
    assert ".zip" not in template
    assert "const allowedExtensions = new Set([" in script
    assert "rejected_files" in script


def test_runner_keeps_chat_attachments_transient_without_knowledge_upload_controls():
    template = (Path(__file__).parents[1] / "playground" / "templates" / "runner.html").read_text(encoding="utf-8")
    runner_script = (Path(__file__).parents[1] / "playground" / "static" / "js" / "runner" / "runner-page.js").read_text(encoding="utf-8")

    assert 'data-attachment-input' in template
    assert 'for="runner-attachments" aria-label="上傳本次試跑附件"' in template
    assert 'data-knowledge-input' not in template
    assert '新增知識庫檔案' not in template
    assert '/playground/run/knowledge/uploads' not in runner_script
    assert 'attachmentInput?.addEventListener("change", async () =>' not in runner_script


def test_semantic_initialization_checks_knowledge_requirement_and_restored_sources(tmp_path):
    config = BuilderSourceConfig(
        workflow_name="semantic readiness",
        retrieve_module="SemanticRetrieve",
        semantic_support_files=("catalog.md",),
    )
    source_dir = tmp_path / "source-files"
    source_dir.mkdir()
    source_dir.joinpath("catalog.md").write_text("catalog content", encoding="utf-8")

    steps = runner_service._initialization_steps(config, {}, {"retrieve"}, [str(source_dir)], str(tmp_path), None)
    initializers = {role: initializer for role, _label, initializer in steps}

    assert [role for role, _label, _initializer in steps[:3]] == ["knowledge_requirement", "knowledge_resources", "retrieve"]
    assert initializers["knowledge_requirement"]() is None
    assert initializers["knowledge_resources"]() is None


def test_semantic_initialization_blocks_when_configured_knowledge_is_unavailable():
    source = compile_python_source(apply_builder_step(default_spec(), "retrieve_policy", "semantic"))

    events = list(runner_service.stream_python_source_initialization(source))

    assert events[-1]["type"] == "final"
    assert events[-1]["ready"] is False
    assert events[-1]["role"] == "knowledge_resources"
    assert "尚未設定參考文件" in events[-1]["error"]


def test_nonsemantic_initialization_does_not_require_knowledge_sources():
    config = BuilderSourceConfig(workflow_name="no knowledge")
    steps = runner_service._initialization_steps(config, {}, set(), None, None, None)

    assert [role for role, _label, _initializer in steps] == ["knowledge_requirement"]
    assert steps[0][2]() is None


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


def test_source_preview_api_preserves_current_draft_without_legacy_page():
    app = create_app()
    app.config.update(TESTING=True)
    source = build_python_source_from_builder_choice("input_type", "text", build_default_python_source())

    with app.test_client() as client:
        with client.session_transaction() as session:
            session["python_source"] = source
            session["builder_has_user_config"] = True

        source_response = client.get("/playground/source/preview")
        legacy_page_response = client.get("/playground/source")
        export_response = client.post("/playground/source/export")
        runner_response = client.get("/playground/run")
        with client.session_transaction() as session:
            preserved_config = config_from_source(session["python_source"])

    assert source_response.status_code == 200
    assert legacy_page_response.status_code == 404
    assert export_response.status_code == 404
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
            "component_fields": "是否通知門市人員帶實體鞋墊說明 = 只有顧客明確同意後才填 true；尚未回答時保持未知（資料類型：是/否)",
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
    assert result["panel_decision"] == "information_request"


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


def test_tool_call_panel_does_not_fallback_for_health_or_safety_concern(monkeypatch):
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
                final_message="建議先就醫評估。確認後要不要安排門市下一步？",
                entities={},
            )

    monkeypatch.setattr(runner_service, "_workflow_from_source", lambda *_args, **_kwargs: FakeWorkflow())

    result = runner_service.execute_python_source(source, message="我足底很痛，走路會刺痛。")

    assert result["tool_calls"] == []
    assert result["tool_call_panels"] == []
    assert result["panel_decision"] == "safety_concern"


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
    assert result["tool_call_panels"][0]["title"] == "請確認：是否確認"


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
    assert result["tool_call_panels"][0]["title"] == "請確認：是否確認"


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
    assert result["panel_decision"] == "fallback_eligible"
    assert result["tool_call_panels"][0]["title"] == "請確認：是否確認"
    assert result["tool_call_panels"][0]["description"] == ""
    assert result["tool_call_panels"][0]["fields"][0]["label"] == "是否確認"


def test_tool_call_panel_falls_back_for_natural_next_step_question(monkeypatch):
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
                final_message="推薦商品：寬楦通勤鞋。要不要幫你進行下一步？",
                entities={},
            )

    monkeypatch.setattr(runner_service, "_workflow_from_source", lambda *_args, **_kwargs: FakeWorkflow())

    result = runner_service.execute_python_source(source, message="請推薦適合久站通勤的產品，並確認下一步。")

    assert len(result["tool_call_panels"]) == 1
    assert result["tool_call_panels"][0]["title"] == "請確認：是否確認"


def test_catalog_identifier_without_retrieved_evidence_stops_for_human_confirmation(monkeypatch):
    source = build_python_source_from_builder_choice("retrieve_policy", "semantic", None)
    source = build_python_source_from_builder_choice("output_format", "interactive", source)
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
    source = build_python_source_from_builder_choice("failure_policy", "handoff", source)

    class FakeWorkflow:
        def run(self, *_args, **_kwargs):
            return WorkflowResult(
                workflow_id="workflow-1",
                final_message="推薦商品：科技鞋墊 通用型。要不要幫你進行下一步？",
                entries=[
                    ContextEntry(
                        type=ContextEntryType.RETRIEVED,
                        content="商品編號：291090970，科技鞋墊 通用型。",
                        metadata={"source": "semantic_retrieve", "kb_hit_count": 1, "memory_hit_count": 0},
                    )
                ],
                entities={},
            )

    monkeypatch.setattr(runner_service, "_workflow_from_source", lambda *_args, **_kwargs: FakeWorkflow())

    result = runner_service.execute_python_source(source, message="請推薦產品編號 X-UNKNOWN-999，並進行下一步。")

    assert result["status"] == "aborted"
    assert result["tool_calls"] == []
    assert result["tool_call_panels"] == []
    assert "X-UNKNOWN-999" in result["final_message"]
    assert "人工確認" in result["final_message"]


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

    assert result["tool_call_panels"][0]["title"] == "請確認：是否確認"


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


def test_tool_call_panel_uses_schema_for_user_facing_confirmation(monkeypatch):
    source = build_python_source_from_builder_choice("output_format", "interactive", None)
    source = build_python_source_from_builder_choice(
        "action",
        {
            "interaction_trigger": "需要使用者確認時呼叫。",
            "api_method": "POST",
            "api_url": "https://example.com/confirm",
            "component_fields": "是否通知門市人員帶實體鞋墊說明 = 只有顧客明確同意後才填 true；尚未回答時保持未知（資料類型：是/否)",
        },
        source,
    )

    class FakeWorkflow:
        def run(self, *_args, **_kwargs):
            return WorkflowResult(
                workflow_id="workflow-1",
                final_message="我建議先採用支撐型鞋墊。\n資料缺口：仍需由門市確認技術細節。",
                entities={
                    "latest_tool_calls": [
                        {
                            "id": "call-1",
                            "type": "function",
                            "function": {"name": "submit_api_1", "arguments": '{"是否通知門市人員帶實體鞋墊說明": false}'},
                        }
                    ]
                },
            )

    monkeypatch.setattr(runner_service, "_workflow_from_source", lambda *_args, **_kwargs: FakeWorkflow())

    result = runner_service.execute_python_source(source, message="請推薦鞋墊")

    assert result["status"] == "completed"
    assert result["panel_decision"] == "tool_call"
    assert result["tool_call_panels"][0]["title"] == "請確認：是否通知門市人員帶實體鞋墊說明"
    assert "資料缺口" not in result["tool_call_panels"][0]["title"]
    assert result["tool_call_panels"][0]["description"] == ""
    assert result["tool_call_panels"][0]["fields"][0]["type"] == "boolean"
    assert result["tool_call_panels"][0]["fields"][0]["label"] == "是否通知門市人員帶實體鞋墊說明"
    assert result["tool_call_panels"][0]["fields"][0]["description"] == ""
    assert result["tool_call_panels"][0]["fields"][0]["value"] == ""
    assert result["tool_call_panels"][0]["fields"][0]["choices"] == [
        {"value": True, "label": "是", "description": ""},
        {"value": False, "label": "否", "description": ""},
    ]
    assert result["tool_call_panels"][0]["api"] == {"method": "POST", "url": "https://example.com/confirm"}


def test_runner_tool_panel_renderer_omits_empty_field_hints():
    renderer_source = (Path(__file__).parents[1] / "playground/static/js/runner/result-surface.js").read_text(encoding="utf-8")

    assert 'const hintText = String(field.description || "").trim();' in renderer_source
    assert "if (hintText)" in renderer_source
    assert "field.description || dataTypeLabel(field.type)" not in renderer_source
    assert "function dataTypeLabel" not in renderer_source


def test_interactive_optional_field_is_not_required_in_tool_schema():
    source = build_python_source_from_builder_choice("output_format", "interactive", None)
    source = build_python_source_from_builder_choice(
        "action",
        {
            "interaction_trigger": "需要使用者確認時呼叫。",
            "api_method": "POST",
            "api_url": "https://example.com/confirm",
            "component_fields": "是否確認 = 使用者是否確認（資料類型：是/否)\n顧客補充需求 = 顧客可補充的需求；可留空。",
        },
        source,
    )

    parameters = config_from_source(source).action_tools[0]["function"]["parameters"]

    assert parameters["required"] == ["是否確認"]


def test_runner_optional_field_is_not_required_for_legacy_tool_schema():
    fields = runner_service._tool_call_fields_from(
        {
            "parameters": {
                "properties": {
                    "是否確認": {"type": "boolean", "description": "使用者是否確認"},
                    "顧客補充需求": {"type": "string", "description": "顧客可補充需求；可留空。"},
                },
                "required": ["是否確認", "顧客補充需求"],
            }
        },
        {},
    )

    assert [field["required"] for field in fields] == [True, False]