"""E-06 — WorkflowConfig:UI 與 Python SDK 的共用工作流組態契約。

設計原則:
- `WorkflowConfig` 是 Domain 最內層物件,不依賴任何框架、UI 或執行引擎
- YAML / JSON 雙向序列化;格式版本號碼預留向下相容空間
- `Workflow.from_config(config)` 是唯一的執行入口(見 engine.py)
- 自訂節點透過 Python import path 引用,builtin 節點直接用 type 字串

YAML 格式範例::

    version: "1"
    entry: perceive
    nodes:
      perceive:
        type: builtin.perceive
      plan:
        type: builtin.plan
      retrieve:
        type: builtin.retrieve
        params:
          backend: none
      reflect:
        type: builtin.reflect
      action:
        type: foundry_completion
        params:
          deployment: gpt-5.2
    gates:
      max_node_hops: 50
      max_revisit: 5
      timeout_sec: 30
"""

from __future__ import annotations

import importlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

# ── YAML 支援(非必要依賴,缺少時 JSON 仍可用) ──────────────────────────────
try:
    import yaml as _yaml

    _HAS_YAML = True
except ImportError:
    _HAS_YAML = False


# ── builtin 節點類型對應表 ────────────────────────────────────────────────────
_BUILTIN_NODE_TYPES = {
    "builtin.perceive",
    "builtin.plan",
    "builtin.retrieve",
    "builtin.reflect",
    "builtin.action",           # alias → upstream_completion
    "upstream_completion",
    "foundry_completion",
}

_BUILTIN_ACTION_TYPES = {"builtin.action", "upstream_completion", "foundry_completion"}


@dataclass
class NodeSpec:
    """單一節點的組態描述。

    type:
        - ``builtin.perceive`` / ``builtin.plan`` / ... — 內建節點
        - ``upstream_completion`` / ``foundry_completion`` — 內建 Action 變體
        - 完整 Python import path(如 ``mypackage.nodes.MyNode``)— 自訂節點
    params:
        傳遞給節點建構子的關鍵字參數,各節點自行解讀。
    compute_target:
        M6-3 節點異質部署宣告。MVP 階段僅作 telemetry / UI label使用,
        SDK 端不隨此值實際 dispatch。合法值:``ryzen_ai`` / ``azure_foundry`` /
        ``local_cpu``。None 表示未宣告。
    """

    type: str
    params: dict[str, Any] = field(default_factory=dict)
    compute_target: str | None = None

    def to_dict(self) -> dict:
        d: dict = {"type": self.type}
        if self.params:
            d["params"] = self.params
        if self.compute_target:
            d["compute_target"] = self.compute_target
        return d

    @staticmethod
    def from_dict(d: dict) -> "NodeSpec":
        return NodeSpec(
            type=d["type"],
            params=d.get("params") or {},
            compute_target=d.get("compute_target"),
        )


@dataclass
class GateConfig:
    """工作流閘門參數。對應 Settings 的三個 WORKFLOW_* 欄位。"""

    max_node_hops: int = 50
    max_revisit: int = 5
    timeout_sec: float = 300.0

    def to_dict(self) -> dict:
        return {
            "max_node_hops": self.max_node_hops,
            "max_revisit": self.max_revisit,
            "timeout_sec": self.timeout_sec,
        }

    @staticmethod
    def from_dict(d: dict) -> "GateConfig":
        return GateConfig(
            max_node_hops=int(d.get("max_node_hops", 50)),
            max_revisit=int(d.get("max_revisit", 5)),
            timeout_sec=float(d.get("timeout_sec", 300.0)),
        )


@dataclass
class WorkflowConfig:
    """工作流的完整組態,可由 UI 或 Python SDK 建立並序列化為 YAML/JSON。

    nodes 中只需列出要覆蓋預設值的節點;未列出的節點在 ``Workflow.from_config``
    時會補回各節點的 DEFAULT。

    name 是 M6-1 Memory Stream 的隔離單位:同名 workflow 跨 run 共享記憶,
    不同名互不干擾。預設 ``default``。

    version 用於未來 schema 向下相容判斷,目前只認 "1"。
    """

    nodes: dict[str, NodeSpec] = field(default_factory=dict)
    gates: GateConfig = field(default_factory=GateConfig)
    entry: str = "perceive"
    name: str = "default"
    version: str = "1"

    # ── 序列化 ────────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "name": self.name,
            "entry": self.entry,
            "nodes": {name: spec.to_dict() for name, spec in self.nodes.items()},
            "gates": self.gates.to_dict(),
        }

    def to_json(self, **kwargs) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, **kwargs)

    def to_yaml(self) -> str:
        if not _HAS_YAML:
            raise RuntimeError(
                "PyYAML 未安裝。請執行 `uv add pyyaml` 後再使用 YAML 序列化。"
            )
        return _yaml.dump(
            self.to_dict(), allow_unicode=True, default_flow_style=False, sort_keys=False
        )

    def save(self, path: str | Path) -> None:
        """依副檔名自動選擇 YAML 或 JSON 儲存。"""
        p = Path(path)
        if p.suffix in (".yaml", ".yml"):
            p.write_text(self.to_yaml(), encoding="utf-8")
        else:
            p.write_text(self.to_json(indent=2), encoding="utf-8")

    # ── 反序列化 ──────────────────────────────────────────────────────────────

    @staticmethod
    def from_dict(d: dict) -> "WorkflowConfig":
        version = str(d.get("version", "1"))
        if version != "1":
            raise ValueError(f"WorkflowConfig version={version!r} 不支援,目前僅接受 '1'。")
        nodes = {
            name: NodeSpec.from_dict(spec)
            for name, spec in (d.get("nodes") or {}).items()
        }
        gates = GateConfig.from_dict(d.get("gates") or {})
        return WorkflowConfig(
            nodes=nodes,
            gates=gates,
            entry=d.get("entry", "perceive"),
            name=d.get("name", "default"),
            version=version,
        )

    @staticmethod
    def from_json(text: str) -> "WorkflowConfig":
        return WorkflowConfig.from_dict(json.loads(text))

    @staticmethod
    def from_yaml(text_or_path: str | Path) -> "WorkflowConfig":
        if not _HAS_YAML:
            raise RuntimeError(
                "PyYAML 未安裝。請執行 `uv add pyyaml` 後再使用 YAML 反序列化。"
            )
        p = Path(text_or_path) if isinstance(text_or_path, (str, Path)) else None
        try:
            is_file = p is not None and p.exists() and p.is_file()
        except OSError:
            is_file = False
        if is_file:
            text = p.read_text(encoding="utf-8")  # type: ignore[union-attr]
        else:
            text = str(text_or_path)
        return WorkflowConfig.from_dict(_yaml.safe_load(text))

    @staticmethod
    def load(path: str | Path) -> "WorkflowConfig":
        """從檔案載入,自動依副檔名選擇解析器。"""
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"WorkflowConfig 檔案不存在:{p}")
        if p.suffix in (".yaml", ".yml"):
            return WorkflowConfig.from_yaml(p)
        return WorkflowConfig.from_json(p.read_text(encoding="utf-8"))


# ── 節點建構輔助 ─────────────────────────────────────────────────────────────

def _build_node_from_spec(
    spec: NodeSpec,
    node_name: str,
    settings=None,
    foundry_client=None,
    config: "WorkflowConfig | None" = None,
):
    """依 NodeSpec 建構節點實例。

    builtin 節點直接 import 各自的 DEFAULT;custom 節點用 importlib 動態載入。
    """
    t = spec.type

    if t == "builtin.perceive":
        from agentic_sdk.workflow.nodes.perceive import DEFAULT
        return DEFAULT(**spec.params)

    if t == "builtin.plan":
        from agentic_sdk.workflow.nodes.plan import DEFAULT
        plan_params = {k: v for k, v in spec.params.items()
                       if k not in ("model", "endpoint", "deployment")}
        # 自動帶入 retrieve 節點的 KB 名稱/描述，讓 Plan 知道「可檢索什麼」
        if "retrieve_description" not in plan_params and config is not None:
            retrieve_spec = config.nodes.get("retrieve")
            if retrieve_spec is not None:
                kb = retrieve_spec.params.get("knowledge_base")
                if isinstance(kb, str):
                    try:
                        from agentic_sdk.knowledge import KnowledgeBase
                        kb_obj = KnowledgeBase.from_file(kb)
                        plan_params.setdefault("retrieve_name", kb_obj.name)
                        plan_params.setdefault("retrieve_description", kb_obj.description)
                    except (FileNotFoundError, OSError, ValueError):
                        pass
        # 若 YAML 指定 deployment 且與全域不同，建立 override foundry client
        plan_foundry = foundry_client
        spec_deployment = spec.params.get("deployment")
        if spec_deployment and settings and spec_deployment != settings.azure_foundry_deployment:
            from agentic_sdk.workflow.llm import RealFoundryClient
            try:
                plan_foundry = RealFoundryClient(
                    settings.model_copy(update={"azure_foundry_deployment": spec_deployment})
                )
            except Exception:
                pass  # key 未設定時退回全域 client
        kw = {"foundry_client": plan_foundry, **plan_params} if plan_foundry else plan_params
        return DEFAULT(**kw)

    if t == "builtin.retrieve":
        from agentic_sdk.knowledge import KnowledgeBase
        from agentic_sdk.workflow.nodes.retrieve import DEFAULT
        retrieve_params = {k: v for k, v in spec.params.items() if k != "enable_vision_query"}
        if isinstance(retrieve_params.get("knowledge_base"), str):
            retrieve_params["knowledge_base"] = KnowledgeBase.from_file(retrieve_params["knowledge_base"])
        return DEFAULT(**retrieve_params)

    if t == "builtin.reflect":
        from agentic_sdk.workflow.nodes.reflect import ReflexionReflect, RuleBasedReflect
        params = dict(spec.params)
        mode = params.pop("mode", "rule_based")
        if mode == "llm":
            kw = {"foundry_client": foundry_client, **params} if foundry_client else params
            return ReflexionReflect(**kw)
        return RuleBasedReflect(**params)

    if t in ("builtin.action", "upstream_completion"):
        from agentic_sdk.workflow.nodes.action import UpstreamCompletionAction
        return UpstreamCompletionAction(settings=settings, **spec.params)

    if t == "foundry_completion":
        from agentic_sdk.workflow.nodes.action import FoundryCompletionAction
        return FoundryCompletionAction(settings=settings, **spec.params)

    # custom — 解析為 "module.path:ClassName" 或 "module.path.ClassName"
    if ":" in t:
        module_path, class_name = t.rsplit(":", 1)
    elif "." in t:
        module_path, class_name = t.rsplit(".", 1)
    else:
        raise ValueError(f"NodeSpec.type={t!r} 無法解析:須為 builtin 名稱或完整 import path。")

    try:
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
    except (ImportError, AttributeError) as exc:
        raise ImportError(f"無法載入自訂節點 {t!r}:{exc}") from exc

    return cls(**spec.params)
