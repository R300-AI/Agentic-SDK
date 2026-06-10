"""A-02 — Workflow engine 的 PoC 實作。

設計取捨:
- **不用 LangGraph**:Phase 2 PoC 的轉換圖只是 sequential + 單一回環,手刻
  迴圈足以表達且零外部依賴;Phase 5 若引入 branching / checkpointing 再評估
  遷移成本(換 engine.py 一個檔案,Node 介面不動)。
- **同步執行**:Action 節點呼叫上游時用同步 openai SDK;Gateway 端若要併發,
  自行在 FastAPI handler 內 `await asyncio.to_thread(workflow.run, ...)`。

每個節點透過 observability.node_span 自動 emit start/finish;Workflow 級別
的 fallback / abort 額外發 workflow.fallback 事件。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from agentic_sdk.config import Settings, get_settings
from agentic_sdk.context import ActiveStore, ContextEntry, ContextEntryType
from agentic_sdk.observability import make_event, node_span
from agentic_sdk.observability.events import EVENT_WORKFLOW_FALLBACK
from agentic_sdk.workflow.gates import Gates
from agentic_sdk.workflow.node import (
    Node,
    NodeOutput,
    WorkflowAborted,
    WorkflowResult,
    WorkflowState,
)

logger = logging.getLogger(__name__)

_NODE_NAMES = ("perceive", "plan", "retrieve", "reflect", "action")


@dataclass
class Workflow:
    """五節點工作流的容器。

    使用方式:
        wf = Workflow()                       # 全部 baseline + 自動依 Settings 拾 mock/real Foundry
        result = wf.run("hello")              # 同步執行

    替換變體:
        wf = Workflow(plan=TreeOfThoughtsPlan())   # 只換 Plan,其他 baseline
    """

    perceive: Node | None = None
    plan: Node | None = None
    retrieve: Node | None = None
    reflect: Node | None = None
    action: Node | None = None
    gates: Gates | None = None
    settings: Settings | None = None
    active_store: ActiveStore | None = None
    entry_node: str = "perceive"

    nodes: dict[str, Node] = field(init=False)

    def __post_init__(self) -> None:
        # 延遲 import 避免循環(nodes/ 反過來 import Workflow 周邊)
        from agentic_sdk.workflow.llm import get_foundry_client
        from agentic_sdk.workflow.nodes.action import DEFAULT as DEFAULT_ACTION
        from agentic_sdk.workflow.nodes.perceive import DEFAULT as DEFAULT_PERCEIVE
        from agentic_sdk.workflow.nodes.plan import DEFAULT as DEFAULT_PLAN
        from agentic_sdk.workflow.nodes.reflect import DEFAULT as DEFAULT_REFLECT
        from agentic_sdk.workflow.nodes.retrieve import DEFAULT as DEFAULT_RETRIEVE

        self.settings = self.settings or get_settings()
        self.gates = self.gates or Gates(
            max_node_hops=self.settings.workflow_max_node_hops,
            max_revisit=self.settings.workflow_max_revisit,
            timeout_sec=self.settings.workflow_timeout_sec,
        )
        # Plan / Action 預設依賴外部服務(Foundry / 上游 OpenAI);
        # 明確把 Workflow 接收到的 settings 傳下去,避免它們各自
        # 退回到 lru_cache 的全域 get_settings(會被外部 .env 污染)。
        self.nodes = {
            "perceive": self.perceive or DEFAULT_PERCEIVE(),
            "plan": self.plan or DEFAULT_PLAN(foundry_client=get_foundry_client(self.settings)),
            "retrieve": self.retrieve or DEFAULT_RETRIEVE(),
            "reflect": self.reflect or DEFAULT_REFLECT(),
            "action": self.action or DEFAULT_ACTION(settings=self.settings),
        }

    @classmethod
    def from_config(
        cls,
        config: "WorkflowConfig",  # type: ignore[name-defined]
        settings: Settings | None = None,
        active_store: ActiveStore | None = None,
        node_overrides: dict[str, Node] | None = None,
    ) -> "Workflow":
        """從 WorkflowConfig 建構 Workflow 實例。

        - `node_overrides`:直接傳入已建構好的 node 實例(例如使用者自己 `AzureOpenAI(...)`
          建好 client、`FoundryCompletionAction(client=...)` 包好後丟進來),優先級高於
          `config.nodes[name]` 中的序列化規格。這是 Python SDK 的主要擴充口。
        - 未在 `node_overrides` 也未在 `config.nodes` 中指定的節點退回各自的 DEFAULT。
        - `config.gates` 覆蓋 Settings 的三道閘門預設值。
        """
        from agentic_sdk.workflow.config import _build_node_from_spec
        from agentic_sdk.workflow.llm import get_foundry_client

        s = settings or get_settings()
        fc = get_foundry_client(s)
        overrides = node_overrides or {}

        def _node(name: str):
            if name in overrides:
                return overrides[name]
            spec = config.nodes.get(name)
            if spec is None:
                return None  # 交給 __post_init__ 補 DEFAULT
            return _build_node_from_spec(spec, name, settings=s, foundry_client=fc)

        gates = Gates(
            max_node_hops=config.gates.max_node_hops,
            max_revisit=config.gates.max_revisit,
            timeout_sec=config.gates.timeout_sec,
        )

        return cls(
            perceive=_node("perceive"),
            plan=_node("plan"),
            retrieve=_node("retrieve"),
            reflect=_node("reflect"),
            action=_node("action"),
            gates=gates,
            settings=s,
            active_store=active_store,
            entry_node=config.entry,
        )

    def run(self, user_message: str, *, workflow_id: str | None = None) -> WorkflowResult:
        state = (
            WorkflowState(user_message=user_message, workflow_id=workflow_id)
            if workflow_id
            else WorkflowState(user_message=user_message)
        )
        user_entry = ContextEntry(type=ContextEntryType.USER_INPUT, content=user_message)
        state.append(user_entry)
        if self.active_store is not None:
            self.active_store.put(user_entry)

        current: str | None = self.entry_node
        total_hops = 0
        aborted = False
        abort_reason: str | None = None

        try:
            while current is not None:
                total_hops += 1
                self.gates.before_visit(current, state, total_hops)
                visit = state.increment_visit(current)

                node = self.nodes.get(current)
                if node is None:
                    raise WorkflowAborted(f"unknown node '{current}'")

                gen_ai_system, gen_ai_model = _llm_attrs(node)
                with node_span(
                    workflow_node=current,
                    workflow_id=state.workflow_id,
                    visit=visit,
                    gen_ai_system=gen_ai_system,
                    gen_ai_request_model=gen_ai_model,
                ) as span:
                    output: NodeOutput = node(state)
                    span.set_next(output.get("next_node"))
                    usage = (output.get("payload") or {}).get("_llm_usage")
                    if usage:
                        span.set_usage(
                            response_model=usage.get("model"),
                            input_tokens=usage.get("input_tokens"),
                            output_tokens=usage.get("output_tokens"),
                        )

                state.apply(output)
                if self.active_store is not None:
                    for new_entry in output.get("context_updates", []) or []:
                        self.active_store.put(new_entry)
                current = output.get("next_node")

        except WorkflowAborted as exc:
            aborted = True
            abort_reason = exc.reason
            logger.warning("workflow aborted: %s", exc.reason, extra={"event": make_event(
                EVENT_WORKFLOW_FALLBACK,
                workflow_id=state.workflow_id,
                workflow_status="aborted",
                workflow_reason=exc.reason,
            )})

        final_message = _final_message_from(state)
        return WorkflowResult(
            workflow_id=state.workflow_id,
            final_message=final_message,
            aborted=aborted,
            abort_reason=abort_reason,
            entries=list(state.entries),
            visit_counts=dict(state.visit_counts),
            usage=state.payload.get("_llm_usage"),
        )


def _llm_attrs(node: Node) -> tuple[str | None, str | None]:
    """節點若聲明 gen_ai_system / gen_ai_request_model,沿用之;否則 (None, None)。"""
    return (
        getattr(node, "gen_ai_system", None),
        getattr(node, "gen_ai_request_model", None),
    )


def _final_message_from(state: WorkflowState) -> str:
    result = state.last_action_result
    if result and "content" in result:
        return str(result["content"])
    err = state.last_action_error
    if err:
        return f"[workflow ended with error] {err.get('message', '')}"
    return ""
