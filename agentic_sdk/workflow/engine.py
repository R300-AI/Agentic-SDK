"""A-02 — Workflow engine 的 PoC 實作。

設計取捨:
- **不用 LangGraph**:Phase 2 PoC 的轉換圖只是 sequential + 單一回環,手刻
  迴圈足以表達且零外部依賴;Phase 5 若引入 branching / checkpointing 再評估
    遷移成本(換 engine.py 一個檔案,Module 介面不動)。
- **同步執行**:Action 模組呼叫上游時用同步 openai SDK;Gateway 端若要併發,
  自行在 FastAPI handler 內 `await asyncio.to_thread(workflow.run, ...)`。

每個模組透過 observability.module_span 自動 emit start/finish;Workflow 級別
的 fallback / abort 額外發 workflow.fallback 事件。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from agentic_sdk.config import Settings, get_settings
from agentic_sdk.context import ActiveStore, ContextEntry, ContextEntryType
from agentic_sdk.memory import MemoryStore
from agentic_sdk.observability import make_event, module_span
from agentic_sdk.observability.events import EVENT_WORKFLOW_FALLBACK
from agentic_sdk.workflow.gates import Gates
from agentic_sdk.workflow.attachments import Attachment
from agentic_sdk.workflow.module import (
    Module,
    ModuleOutput,
    WorkflowAborted,
    WorkflowResult,
    WorkflowState,
)

logger = logging.getLogger(__name__)


@dataclass
class Workflow:
    """五模組工作流的容器。

    使用方式:
        wf = Workflow()                       # 最小 non-LLM baseline
        result = wf.run("hello")              # 同步執行

    替換變體:
        wf = Workflow(plan=TreeOfThoughtsPlan())   # 只換 Plan,其他 baseline
    """

    perceive: Module | None = None
    plan: Module | None = None
    retrieve: Module | None = None
    reflect: Module | None = None
    action: Module | None = None
    gates: Gates | None = None
    settings: Settings | None = None
    active_store: ActiveStore | None = None
    memory_store: MemoryStore | None = None
    workflow_name: str = "default"
    entry_module: str = "perceive"

    modules: dict[str, Module] = field(init=False)

    def __post_init__(self) -> None:
        # 延遲 import 避免循環(modules/ 反過來 import Workflow 周邊)
        from agentic_sdk.workflow.modules.action import DEFAULT as DEFAULT_ACTION
        from agentic_sdk.workflow.modules.perceive import DEFAULT as DEFAULT_PERCEIVE
        from agentic_sdk.workflow.modules.retrieve import DEFAULT as DEFAULT_RETRIEVE

        self.settings = self.settings or get_settings()
        self.gates = self.gates or Gates(
            max_node_hops=self.settings.workflow_max_node_hops,
            max_revisit=self.settings.workflow_max_revisit,
            timeout_sec=self.settings.workflow_timeout_sec,
        )
        self.modules = {
            "perceive": self.perceive or DEFAULT_PERCEIVE(),
            "retrieve": self.retrieve or DEFAULT_RETRIEVE(),
            "action": self.action or DEFAULT_ACTION(),
        }
        if self.plan is not None:
            self.modules["plan"] = self.plan
        if self.reflect is not None:
            self.modules["reflect"] = self.reflect

    @classmethod
    def from_config(
        cls,
        config: "WorkflowConfig",  # type: ignore[name-defined]
        settings: Settings | None = None,
        active_store: ActiveStore | None = None,
        memory_store: MemoryStore | None = None,
        module_overrides: dict[str, Module] | None = None,
    ) -> "Workflow":
        """從 WorkflowConfig 建構 Workflow 實例。

                - `module_overrides`:直接傳入已建構好的 module 實例(例如使用者自己 `OpenAI(...)`
                    建好 client、`GenerativeAction(client=...)` 包好後丟進來),優先級高於
          `config.modules[name]` 中的序列化規格。這是 Python SDK 的主要擴充口。
        - 未在 `module_overrides` 也未在 `config.modules` 中指定的模組退回各自的 DEFAULT。
        - `config.gates` 覆蓋 Settings 的三道閘門預設值。
        """
        from agentic_sdk.workflow.config import _build_module_from_spec

        s = settings or get_settings()
        overrides = module_overrides or {}

        def _module(name: str):
            if name in overrides:
                return overrides[name]
            spec = config.modules.get(name)
            if spec is None:
                return None  # 交給 __post_init__ 補 DEFAULT
            return _build_module_from_spec(spec, settings=s, config=config)

        gates = Gates(
            max_node_hops=config.gates.max_node_hops,
            max_revisit=config.gates.max_revisit,
            timeout_sec=config.gates.timeout_sec,
        )

        return cls(
            perceive=_module("perceive"),
            plan=_module("plan"),
            retrieve=_module("retrieve"),
            reflect=_module("reflect"),
            action=_module("action"),
            gates=gates,
            settings=s,
            active_store=active_store,
            memory_store=memory_store,
            workflow_name=config.name,
            entry_module=config.entry,
        )

    def run(
        self,
        user_message: str,
        *,
        workflow_id: str | None = None,
        attachments: list[Attachment] | None = None,
    ) -> WorkflowResult:
        state = (
            WorkflowState(user_message=user_message, workflow_id=workflow_id)
            if workflow_id
            else WorkflowState(user_message=user_message)
        )
        state.workflow_name = self.workflow_name
        state.memory_store = self.memory_store
        if attachments:
            state.attachments = list(attachments)
        user_entry = ContextEntry(type=ContextEntryType.USER_INPUT, content=user_message)
        state.append(user_entry)
        if self.active_store is not None:
            self.active_store.put(user_entry)

        current: str | None = self.entry_module
        total_hops = 0
        aborted = False
        abort_reason: str | None = None

        try:
            while current is not None:
                total_hops += 1
                self.gates.before_visit(current, state, total_hops)
                visit = state.increment_visit(current)

                module = self.modules.get(current)
                if module is None:
                    raise WorkflowAborted(f"unknown module '{current}'")

                gen_ai_system, gen_ai_model = _llm_attrs(module)
                with module_span(
                    workflow_module=current,
                    workflow_id=state.workflow_id,
                    visit=visit,
                    gen_ai_system=gen_ai_system,
                    gen_ai_request_model=gen_ai_model,
                ) as span:
                    raw_output: Any = module(state)
                    output = _normalize_output(current, raw_output, state)
                    span.set_next(output.get("next_module"))
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
                current = output.get("next_module")

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


def _llm_attrs(module: Module) -> tuple[str | None, str | None]:
    """模組若聲明 gen_ai_system / gen_ai_request_model,沿用之;否則 (None, None)。"""
    return (
        getattr(module, "gen_ai_system", None),
        getattr(module, "gen_ai_request_model", None),
    )


def _final_message_from(state: WorkflowState) -> str:
    result = state.last_action_result
    if result and "content" in result:
        return str(result["content"])
    err = state.last_action_error
    if err:
        return f"[workflow ended with error] {err.get('message', '')}"
    return ""


def _normalize_output(current: str, raw_output: Any, state: WorkflowState) -> ModuleOutput:
    if isinstance(raw_output, dict):
        return raw_output

    if current == "action":
        content = "" if raw_output is None else str(raw_output)
        state.last_action_error = None
        state.last_action_result = {"content": content, "model": "custom-action"}
        return ModuleOutput(
            next_module=None,
            payload={"latest_final_message": content},
            context_updates=[
                ContextEntry(
                    type=ContextEntryType.ACTION_RESULT,
                    content=content,
                    metadata={"ok": True, "model": "custom-action"},
                )
            ],
        )

    raise TypeError(f"module '{current}' returned unsupported output type: {type(raw_output).__name__}")
