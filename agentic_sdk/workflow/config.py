"""E-06 — WorkflowConfig:UI 與 Python SDK 的共用工作流組態契約。

設計原則:
- `WorkflowConfig` 是 Domain 最內層物件,不依賴任何框架、UI 或執行引擎
- YAML / JSON 雙向序列化;格式版本號碼預留向下相容空間
- `Workflow.from_config(config)` 是唯一的執行入口(見 engine.py)
- 自訂模組透過 Python import path 引用,內建模組直接用 type 字串

YAML 格式範例::

    version: "1"
    entry: perceive
        modules:
      perceive:
                type: TextPerceive
      plan:
                type: NextStepPlan
      retrieve:
                type: HybridRetrieve
        params:
                    knowledge_base_ref: default
      reflect:
                type: ResponseCheckReflect
      action:
                type: GenerativeAction
        params:
          backend: foundry
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


@dataclass
class ModuleSpec:
    """單一模組的組態描述。

    type:
        - ``TextPerceive`` / ``NextStepPlan`` / ... — 文件定義的標準模組
        - 完整 Python import path(如 ``mypackage.modules.MyModule``)— 自訂模組
    params:
        傳遞給模組建構子的關鍵字參數,各模組自行解讀。
    compute_target:
        M6-3 模組異質部署宣告。MVP 階段僅作 telemetry / UI label使用,
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
    def from_dict(d: dict) -> "ModuleSpec":
        return ModuleSpec(
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

    modules 中只需列出要覆蓋預設值的模組;未列出的模組在 ``Workflow.from_config``
    時會補回各模組的 DEFAULT。

    name 是 M6-1 Memory Stream 的隔離單位:同名 workflow 跨 run 共享記憶,
    不同名互不干擾。預設 ``default``。

    version 用於未來 schema 向下相容判斷,目前只認 "1"。
    """

    modules: dict[str, ModuleSpec] = field(default_factory=dict)
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
            "modules": {name: spec.to_dict() for name, spec in self.modules.items()},
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
        modules = {
            name: ModuleSpec.from_dict(spec)
            for name, spec in (d.get("modules") or {}).items()
        }
        gates = GateConfig.from_dict(d.get("gates") or {})
        return WorkflowConfig(
            modules=modules,
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


# ── 模組建構輔助 ─────────────────────────────────────────────────────────────

def _build_module_from_spec(
    spec: ModuleSpec,
    module_name: str,
    settings=None,
    foundry_client=None,
    config: "WorkflowConfig | None" = None,
):
    """依 ModuleSpec 建構模組實例。

    標準模組直接 import 對應實作;custom 模組用 importlib 動態載入。
    """
    t = spec.type

    if t == "PassThroughPerceive":
        from agentic_sdk.workflow.modules.perceive import PassThroughPerceive
        return PassThroughPerceive(**spec.params)

    if t in {"TextPerceive", "StructuredPerceive", "TextImagePerceive"}:
        from agentic_sdk.workflow.modules.perceive import (
            StructuredPerceive,
            TextImagePerceive,
            TextPerceive,
        )
        perceive_cls = {
            "TextPerceive": TextPerceive,
            "StructuredPerceive": StructuredPerceive,
            "TextImagePerceive": TextImagePerceive,
        }[t]
        kw = {"foundry_client": foundry_client, **spec.params} if foundry_client else spec.params
        return perceive_cls(**kw)

    if t == "NextStepPlan":
        from agentic_sdk.workflow.modules.plan import NextStepPlan
        plan_params = {k: v for k, v in spec.params.items()
                       if k not in ("model", "endpoint", "deployment")}
        # 自動帶入 retrieve 模組的 KB 名稱/描述，讓 Plan 知道「可檢索什麼」
        if "retrieve_description" not in plan_params and config is not None:
            retrieve_spec = config.modules.get("retrieve")
            if retrieve_spec is not None:
                kb = retrieve_spec.params.get("knowledge_base")
                kb_ref = retrieve_spec.params.get("knowledge_base_ref")
                if isinstance(kb, str):
                    try:
                        from agentic_sdk.knowledge import KnowledgeBase
                        kb_obj = KnowledgeBase.from_file(kb)
                        plan_params.setdefault("retrieve_name", kb_obj.name)
                        plan_params.setdefault("retrieve_description", kb_obj.description)
                    except (FileNotFoundError, OSError, ValueError):
                        pass
                elif isinstance(kb_ref, str):
                    try:
                        from agentic_sdk.capabilities import KnowledgeBaseRegistry
                        kb_obj = KnowledgeBaseRegistry().load(kb_ref)
                        plan_params.setdefault("retrieve_name", kb_obj.name)
                        plan_params.setdefault("retrieve_description", kb_obj.description)
                    except (KeyError, FileNotFoundError, OSError, ValueError):
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
        return NextStepPlan(**kw)

    if t in {"KeywordRetrieve", "SemanticRetrieve", "HybridRetrieve"}:
        from agentic_sdk.capabilities import KnowledgeBaseRegistry
        from agentic_sdk.knowledge import KnowledgeBase
        from agentic_sdk.workflow.modules.retrieve import HybridRetrieve, KeywordRetrieve, SemanticRetrieve
        retrieve_params = {
            k: v
            for k, v in spec.params.items()
            if k not in ("enable_vision_query", "retrieve_template_ref", "retrieve_strategy_ref")
        }
        kb_ref = retrieve_params.pop("knowledge_base_ref", None)
        if isinstance(kb_ref, str):
            retrieve_params["knowledge_base"] = KnowledgeBaseRegistry().load(kb_ref)
        if isinstance(retrieve_params.get("knowledge_base"), str):
            retrieve_params["knowledge_base"] = KnowledgeBase.from_file(retrieve_params["knowledge_base"])
        if t == "KeywordRetrieve":
            return KeywordRetrieve(**retrieve_params)
        if t == "SemanticRetrieve":
            return SemanticRetrieve(**retrieve_params)
        return HybridRetrieve(**retrieve_params)

    if t in {"ResponseCheckReflect", "EvidenceCheckReflect"}:
        from agentic_sdk.workflow.modules.reflect import EvidenceCheckReflect, ResponseCheckReflect
        params = dict(spec.params)
        if t == "ResponseCheckReflect":
            kw = {"foundry_client": foundry_client, **params} if foundry_client else params
            return ResponseCheckReflect(**kw)
        return EvidenceCheckReflect(**params)

    if t in {"DirectAnswerAction", "GenerativeAction", "StructuredAction"}:
        from agentic_sdk.workflow.modules.action import DirectAnswerAction, GenerativeAction, StructuredAction
        params = dict(spec.params)
        if t == "DirectAnswerAction":
            return DirectAnswerAction(**params)
        if t == "StructuredAction":
            return StructuredAction(settings=settings, **params)
        return GenerativeAction(settings=settings, **params)

    # custom — 解析為 "module.path:ClassName" 或 "module.path.ClassName"
    if ":" in t:
        module_path, class_name = t.rsplit(":", 1)
    elif "." in t:
        module_path, class_name = t.rsplit(".", 1)
    else:
        raise ValueError(f"ModuleSpec.type={t!r} 無法解析:須為標準模組名稱或完整 import path。")

    try:
        mod = importlib.import_module(module_path)
        cls = getattr(mod, class_name)
    except (ImportError, AttributeError) as exc:
        raise ImportError(f"無法載入自訂模組 {t!r}:{exc}") from exc

    return cls(**spec.params)
