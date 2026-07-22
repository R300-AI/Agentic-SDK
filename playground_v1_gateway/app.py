from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass
from typing import Any

from flask import Flask, Response, jsonify, request

from agentic_sdk import Workflow
from agentic_sdk.modules import DirectAnswerAction, GenerativeAction, KeywordRetrieve, PassThroughPerceive


@dataclass(frozen=True)
class KnowledgeItem:
    id: str
    title: str
    content: str
    keywords: tuple[str, ...]


_KNOWLEDGE: list[KnowledgeItem] = [
    KnowledgeItem(
        id="stable-pro-walker",
        title="StablePro 機能健走鞋",
        content="StablePro 機能健走鞋適合久站、扁平足或需要足弓支撐的使用者。",
        keywords=("久站", "扁平足", "足弓", "支撐", "健走"),
    ),
    KnowledgeItem(
        id="cloud-runner-lite",
        title="CloudRunner Lite 慢跑鞋",
        content="CloudRunner Lite 主打輕量緩震，適合日常慢跑與通勤步行。",
        keywords=("慢跑", "輕量", "緩震", "通勤"),
    ),
    KnowledgeItem(
        id="rain-guard-trail",
        title="RainGuard Trail 戶外鞋",
        content="RainGuard Trail 具備止滑外底與防潑水鞋面，適合雨天或輕戶外路線。",
        keywords=("雨天", "止滑", "防潑水", "戶外"),
    ),
]

_RESULTS: dict[str, dict[str, Any]] = {}
_EVENTS: dict[str, list[dict[str, Any]]] = {}
_AGENTS: dict[str, dict[str, Any]] = {}


def create_app() -> Flask:
    app = Flask(__name__)

    @app.after_request
    def add_cors_headers(response):
        response.headers.setdefault("Access-Control-Allow-Origin", "*")
        response.headers.setdefault("Access-Control-Allow-Headers", "Content-Type, X-CSRF-Token")
        response.headers.setdefault("Access-Control-Allow-Methods", "GET, POST, PUT, DELETE, OPTIONS")
        return response

    @app.route("/healthz", methods=["GET"])
    def healthz():
        return jsonify({"ok": True, "service": "playground_v1_gateway"})

    @app.route("/v1/capabilities", methods=["GET"])
    def capabilities():
        return jsonify(_capability_document())

    @app.route("/v1/knowledge-bases/<knowledge_base_ref>/preview", methods=["GET"])
    def preview_knowledge_base(knowledge_base_ref: str):
        query = request.args.get("query", "")
        top_k = _to_int(request.args.get("top_k"), 3)
        hits = _search_knowledge(query, top_k=top_k) if knowledge_base_ref == "shoe_store" else []
        return jsonify(
            {
                "knowledge_base_ref": knowledge_base_ref,
                "query": query,
                "hits": [
                    {"id": item.id, "title": item.title, "score": score, "source": "playground_fixture"}
                    for item, score in hits
                ],
            }
        )

    @app.route("/v1/workflow/run", methods=["POST", "OPTIONS"])
    def run_workflow():
        if request.method == "OPTIONS":
            return Response(status=204)
        body = request.get_json(silent=True) or {}
        user_message = str(body.get("user_message") or "").strip()
        workflow_yaml = str(body.get("workflow_yaml") or "")
        workflow_id = uuid.uuid4().hex

        result = _execute_workflow(user_message=user_message, workflow_yaml=workflow_yaml, workflow_id=workflow_id)
        _RESULTS[workflow_id] = result
        _EVENTS[workflow_id] = _build_events(workflow_id=workflow_id, result=result)
        return jsonify(
            {
                "workflow_id": workflow_id,
                "stream_url": f"/v1/workflow/{workflow_id}/stream",
                "result_url": f"/v1/workflow/{workflow_id}/result",
            }
        )

    @app.route("/v1/workflow/<workflow_id>/result", methods=["GET"])
    def workflow_result(workflow_id: str):
        result = _RESULTS.get(workflow_id)
        if result is None:
            return jsonify({"detail": "workflow result not found"}), 404
        return jsonify(result)

    @app.route("/v1/workflow/<workflow_id>/stream", methods=["GET"])
    def workflow_stream(workflow_id: str):
        events = _EVENTS.get(workflow_id)
        if events is None:
            return jsonify({"detail": "workflow stream not found"}), 404
        return Response(_stream_events(events), mimetype="text/event-stream")

    @app.route("/api/me/agents", methods=["GET", "POST", "OPTIONS"])
    def agents_collection():
        if request.method == "OPTIONS":
            return Response(status=204)
        if request.method == "GET":
            return jsonify({"items": [_agent_summary(agent) for agent in _AGENTS.values()]})
        body = request.get_json(silent=True) or {}
        agent_id = uuid.uuid4().hex
        agent = _agent_detail(agent_id, body)
        _AGENTS[agent_id] = agent
        return jsonify(agent)

    @app.route("/api/me/agents/<agent_id>", methods=["GET", "PUT", "DELETE", "OPTIONS"])
    def agent_item(agent_id: str):
        if request.method == "OPTIONS":
            return Response(status=204)
        if request.method == "GET":
            agent = _AGENTS.get(agent_id)
            if agent is None:
                return jsonify({"detail": "agent not found"}), 404
            return jsonify(agent)
        if request.method == "DELETE":
            _AGENTS.pop(agent_id, None)
            return Response(status=204)
        body = request.get_json(silent=True) or {}
        agent = _agent_detail(agent_id, body)
        _AGENTS[agent_id] = agent
        return jsonify(agent)

    return app


def _capability_document() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "node_definitions": [
            {"type": "builtin.perceive", "role": "perceive", "label": "Perceive", "params_schema": {}},
            {"type": "builtin.plan", "role": "plan", "label": "Plan", "params_schema": {}},
            {"type": "builtin.retrieve", "role": "retrieve", "label": "Retrieve", "params_schema": {}},
            {"type": "builtin.reflect", "role": "reflect", "label": "Reflect", "params_schema": {}},
            {"type": "completion", "role": "action", "label": "Action", "params_schema": {}},
        ],
        "provider_refs": [],
        "profile_refs": [],
        "retrieve_strategy_refs": [
            {"ref": "lexical_file_kb", "label": "本機關鍵字知識庫", "enabled": True},
        ],
        "retrieve_template_refs": [
            {
                "ref": "shoe_store_catalog_search",
                "label": "鞋款知識庫搜尋",
                "strategy_ref": "lexical_file_kb",
                "defaults": {
                    "knowledge_base_ref": "shoe_store",
                    "retrieve_strategy_ref": "lexical_file_kb",
                    "top_k": 3,
                },
            }
        ],
        "knowledge_base_refs": [
            {"ref": "shoe_store", "name": "鞋款範例知識庫", "label": "鞋款範例知識庫"},
        ],
        "execution_env_refs": [{"ref": "local-dev", "kind": "flask", "label": "Playground V1 dev gateway"}],
        "export_capabilities": {"runnable_bundle": True},
        "feature_flags": {"inline_python_hosted": False},
    }


def _execute_workflow(*, user_message: str, workflow_yaml: str, workflow_id: str) -> dict[str, Any]:
    hits = _search_knowledge(user_message, top_k=3)
    items = [{"keywords": list(item.keywords), "content": item.content} for item, _score in hits]
    if not items:
        items = [{"keywords": [user_message.lower()], "content": "沒有命中任何條目。"}]

    action = _build_action_from_yaml(workflow_yaml)
    workflow = Workflow(
        perceive=PassThroughPerceive(),
        retrieve=KeywordRetrieve(items=items, fallback="沒有命中任何條目。"),
        action=action,
        workflow_name="playground_v1",
    )
    result = workflow.run(user_message, workflow_id=workflow_id)
    return {
        "workflow_id": result.workflow_id,
        "final_message": result.final_message,
        "aborted": result.aborted,
        "abort_reason": result.abort_reason,
        "visit_counts": result.visit_counts,
        "usage": result.usage,
    }


def _build_action_from_yaml(workflow_yaml: str):
    params = _action_params(workflow_yaml)
    api_key = str(params.get("api_key") or "").strip()
    base_url = str(params.get("base_url") or params.get("endpoint") or "").strip()
    model = str(params.get("model") or params.get("deployment") or "").strip()
    if api_key and base_url and model:
        return GenerativeAction(
            api_key=api_key,
            base_url=base_url,
            model=model,
            temperature=_to_float(params.get("temperature")),
        )
    return DirectAnswerAction()


def _action_params(workflow_yaml: str) -> dict[str, Any]:
    try:
        import yaml
    except Exception:
        return {}
    try:
        parsed = yaml.safe_load(workflow_yaml) or {}
    except Exception:
        return {}
    nodes = parsed.get("nodes") if isinstance(parsed, dict) else None
    action = nodes.get("action") if isinstance(nodes, dict) else None
    params = action.get("params") if isinstance(action, dict) else None
    return params if isinstance(params, dict) else {}


def _search_knowledge(query: str, *, top_k: int) -> list[tuple[KnowledgeItem, float]]:
    normalized = query.lower()
    scored: list[tuple[KnowledgeItem, float]] = []
    for item in _KNOWLEDGE:
        score = 0.0
        for keyword in item.keywords:
            if keyword.lower() in normalized:
                score += 1.0
        if item.title.lower() in normalized:
            score += 1.0
        if score > 0:
            scored.append((item, score))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    return scored[:top_k]


def _build_events(*, workflow_id: str, result: dict[str, Any]) -> list[dict[str, Any]]:
    nodes = ["perceive", "plan", "retrieve", "action", "reflect"]
    events: list[dict[str, Any]] = []
    for index, node in enumerate(nodes, start=1):
        events.append(_event("workflow.node.start", workflow_id, node, workflow_node_visit=1))
        if node == "plan":
            events.append(
                _event(
                    "workflow.node.thought",
                    workflow_id,
                    node,
                    plan_thought="dev gateway routes to retrieve, then action",
                    plan_next_node="retrieve",
                    plan_fallback=False,
                )
            )
        if node == "action":
            final_message = str(result.get("final_message") or "")
            for delta_index, chunk in enumerate(_chunks(final_message), start=1):
                events.append(_event("workflow.node.delta", workflow_id, node, delta_text=chunk, delta_index=delta_index))
        events.append(
            _event(
                "workflow.node.finish",
                workflow_id,
                node,
                workflow_status="ok",
                workflow_next_node=nodes[index] if index < len(nodes) else None,
            )
        )
    return events


def _event(event_name: str, workflow_id: str, workflow_node: str, **extra: Any) -> dict[str, Any]:
    payload = {
        "ts": time.time(),
        "event_name": event_name,
        "workflow_id": workflow_id,
        "workflow_node": workflow_node,
    }
    payload.update({key: value for key, value in extra.items() if value is not None})
    return payload


def _stream_events(events: list[dict[str, Any]]):
    for event in events:
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        time.sleep(0.03)


def _chunks(text: str, size: int = 8):
    if not text:
        return
    for start in range(0, len(text), size):
        yield text[start:start + size]


def _agent_summary(agent: dict[str, Any]) -> dict[str, Any]:
    return {
        "agent_id": agent["agent_id"],
        "agent_name": agent["agent_name"],
        "description": agent.get("description", ""),
        "execution_backend": agent.get("execution_backend", "openai"),
        "updated_at": agent.get("updated_at"),
        "last_run_at": agent.get("last_run_at"),
    }


def _agent_detail(agent_id: str, body: dict[str, Any]) -> dict[str, Any]:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    return {
        "agent_id": agent_id,
        "agent_name": str(body.get("agent_name") or "Untitled Agent"),
        "description": str(body.get("description") or ""),
        "workflow_yaml": str(body.get("workflow_yaml") or ""),
        "execution_backend": str(body.get("execution_backend") or "openai"),
        "updated_at": now,
        "created_at": now,
        "last_run_at": None,
        "owner_username": "local-dev",
    }


def _to_int(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _to_float(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None