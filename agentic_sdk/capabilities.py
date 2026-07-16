"""Capability discovery and lightweight registries for Stage II contracts."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agentic_sdk.knowledge import KnowledgeBase


_REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class KnowledgeBaseDefinition:
    ref: str
    name: str
    description: str
    source_kind: str
    source_path: str
    schema_version: int = 1
    metadata_fields: tuple[str, ...] = ()

    def resolved_path(self) -> Path:
        path = Path(self.source_path)
        if path.is_absolute():
            return path
        return _REPO_ROOT / path

    def to_summary(self) -> dict[str, Any]:
        entry_count = 0
        sample_entries: list[dict[str, str]] = []
        try:
            kb = KnowledgeBase.from_file(self.resolved_path())
            entry_count = len(kb.entries)
            sample_entries = [
                {"id": entry.id, "title": entry.title}
                for entry in kb.entries[:3]
            ]
        except (FileNotFoundError, OSError, ValueError, KeyError):
            sample_entries = []
        return {
            "ref": self.ref,
            "name": self.name,
            "description": self.description,
            "source": {"kind": self.source_kind, "path": self.source_path},
            "schema_version": self.schema_version,
            "entry_count": entry_count,
            "metadata_fields": list(self.metadata_fields),
            "sample_entries": sample_entries,
        }


class KnowledgeBaseRegistry:
    """Resolve knowledge_base_ref values without exposing paths to the demo UI."""

    def __init__(self, definitions: list[KnowledgeBaseDefinition] | None = None) -> None:
        items = definitions or default_knowledge_base_definitions()
        self._definitions = {item.ref: item for item in items}

    def list_definitions(self) -> list[dict[str, Any]]:
        return [definition.to_summary() for definition in self._definitions.values()]

    def get_definition(self, ref: str) -> KnowledgeBaseDefinition:
        try:
            return self._definitions[ref]
        except KeyError as exc:
            raise KeyError(f"Unknown knowledge_base_ref: {ref}") from exc

    def load(self, ref: str) -> KnowledgeBase:
        definition = self.get_definition(ref)
        return KnowledgeBase.from_file(definition.resolved_path())

    def preview(self, ref: str, query: str, top_k: int = 3) -> dict[str, Any]:
        kb = self.load(ref)
        hits = kb.search(query, top_k=top_k)
        return {
            "knowledge_base_ref": ref,
            "query": query,
            "hits": [
                {
                    "id": hit.entry.id,
                    "title": hit.entry.title,
                    "score": hit.score,
                    "source": "knowledge_base",
                }
                for hit in hits
            ],
        }


@dataclass(frozen=True)
class RetrieveStrategyDefinition:
    ref: str
    module_type: str
    label: str
    description: str
    params_schema: dict[str, Any]
    enabled: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "type": self.module_type,
            "label": self.label,
            "description": self.description,
            "params_schema": self.params_schema,
            "enabled": self.enabled,
        }


@dataclass(frozen=True)
class RetrieveTemplateDefinition:
    ref: str
    label: str
    strategy_ref: str
    defaults: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "ref": self.ref,
            "label": self.label,
            "strategy_ref": self.strategy_ref,
            "defaults": self.defaults,
        }


class RetrieveStrategyRegistry:
    """Expose retrieve families and profile-ready templates to UI/CLI callers."""

    def __init__(
        self,
        strategies: list[RetrieveStrategyDefinition] | None = None,
        templates: list[RetrieveTemplateDefinition] | None = None,
    ) -> None:
        self._strategies = {item.ref: item for item in (strategies or default_retrieve_strategies())}
        self._templates = {item.ref: item for item in (templates or default_retrieve_templates())}

    def list_strategies(self) -> list[dict[str, Any]]:
        return [strategy.to_dict() for strategy in self._strategies.values()]

    def list_templates(self) -> list[dict[str, Any]]:
        return [template.to_dict() for template in self._templates.values()]


def _number_schema(default: float, minimum: float = 0.0, maximum: float = 1.0) -> dict[str, Any]:
    return {"type": "number", "default": default, "min": minimum, "max": maximum}


def default_knowledge_base_definitions() -> list[KnowledgeBaseDefinition]:
    return [
        KnowledgeBaseDefinition(
            ref="shoe_store",
            name="shoe_store",
            description="鞋店產品型錄示例，用於 SDK demo profile。",
            source_kind="file",
            source_path="examples/knowledge/shoe_store.json",
            metadata_fields=("category", "size_range", "price"),
        )
    ]


def default_retrieve_strategies() -> list[RetrieveStrategyDefinition]:
    return [
        RetrieveStrategyDefinition(
            ref="semantic_kb",
            module_type="SemanticRetrieve",
            label="Semantic KB",
            description="使用 KnowledgeBase 與對話記憶進行語意檢索。",
            params_schema={
                "knowledge_base_ref": {"type": "ref", "ref_kind": "knowledge_base", "required": True},
                "top_k": {"type": "integer", "default": 3, "min": 1, "max": 20},
                "similarity_weight": _number_schema(0.5),
                "recency_weight": _number_schema(0.3),
                "importance_weight": _number_schema(0.2),
            },
        ),
        RetrieveStrategyDefinition(
            ref="hybrid_memory_kb",
            module_type="HybridRetrieve",
            label="Hybrid memory + KB",
            description="同時查靜態 KB 與 Memory Stream。",
            params_schema={
                "knowledge_base_ref": {"type": "ref", "ref_kind": "knowledge_base", "required": False},
                "top_k": {"type": "integer", "default": 3, "min": 1, "max": 20},
                "similarity_weight": _number_schema(0.5),
                "recency_weight": _number_schema(0.3),
                "importance_weight": _number_schema(0.2),
            },
        ),
    ]


def default_retrieve_templates() -> list[RetrieveTemplateDefinition]:
    return [
        RetrieveTemplateDefinition(
            ref="shoe_store_catalog_search",
            label="鞋店產品型錄搜尋",
            strategy_ref="semantic_kb",
            defaults={"knowledge_base_ref": "shoe_store", "top_k": 3},
        )
    ]


def _module_definitions() -> list[dict[str, Any]]:
    return [
        {
            "type": "PassThroughPerceive",
            "role": "perceive",
            "label": "Pass-through perceive",
            "params_schema": {
            },
        },
        {
            "type": "TextPerceive",
            "role": "perceive",
            "label": "Text perceive",
            "params_schema": {
                "welcome_message": {"type": "string", "default": ""},
                "options": {"type": "array", "default": []},
                "importance": {"type": "number", "default": 1.0, "min": 0.0},
            },
        },
        {
            "type": "StructuredPerceive",
            "role": "perceive",
            "label": "Structured perceive",
            "params_schema": {
                "welcome_message": {"type": "string", "default": ""},
                "options": {"type": "array", "default": []},
                "importance": {"type": "number", "default": 1.0, "min": 0.0},
            },
        },
        {
            "type": "TextImagePerceive",
            "role": "perceive",
            "label": "Text + image perceive",
            "params_schema": {
                "welcome_message": {"type": "string", "default": ""},
                "options": {"type": "array", "default": []},
                "importance": {"type": "number", "default": 1.0, "min": 0.0},
            },
        },
        {
            "type": "NextStepPlan",
            "role": "plan",
            "label": "Next-step plan",
            "params_schema": {
                "system_prompt": {"type": "string", "ui": {"control": "textarea"}},
                "deployment": {"type": "string", "advanced": True},
            },
        },
        {
            "type": "KeywordRetrieve",
            "role": "retrieve",
            "label": "Keyword retrieve",
            "params_schema": {
                "items": {"type": "array", "default": []},
            },
        },
        {
            "type": "SemanticRetrieve",
            "role": "retrieve",
            "label": "Semantic retrieve",
            "params_schema": {
                "knowledge_base_ref": {"type": "ref", "ref_kind": "knowledge_base"},
                "top_k": {"type": "integer", "default": 3, "min": 1, "max": 20},
                "similarity_weight": _number_schema(0.5),
                "recency_weight": _number_schema(0.3),
                "importance_weight": _number_schema(0.2),
            },
        },
        {
            "type": "HybridRetrieve",
            "role": "retrieve",
            "label": "Hybrid retrieve",
            "params_schema": {
                "knowledge_base_ref": {"type": "ref", "ref_kind": "knowledge_base"},
                "top_k": {"type": "integer", "default": 3, "min": 1, "max": 20},
                "similarity_weight": _number_schema(0.5),
                "recency_weight": _number_schema(0.3),
                "importance_weight": _number_schema(0.2),
            },
        },
        {
            "type": "ResponseCheckReflect",
            "role": "reflect",
            "label": "Response check reflect",
            "params_schema": {
                "on_failure": {"type": "string", "default": "retry_plan"},
            },
        },
        {
            "type": "EvidenceCheckReflect",
            "role": "reflect",
            "label": "Evidence check reflect",
            "params_schema": {
                "on_failure": {"type": "string", "default": "retry_plan"},
            },
        },
        {
            "type": "DirectAnswerAction",
            "role": "action",
            "label": "Direct answer action",
            "params_schema": {
            },
        },
        {
            "type": "GenerativeAction",
            "role": "action",
            "label": "Generative action",
            "params_schema": {
                "provider_ref": {"type": "ref", "ref_kind": "provider"},
                "backend": {"type": "string", "enum": ["upstream", "foundry"], "default": "upstream"},
                "deployment": {"type": "string", "advanced": True},
                "temperature": {"type": "number", "default": 0.2, "min": 0.0, "max": 2.0},
                "secret_ref": {"type": "ref", "ref_kind": "secret"},
            },
        },
        {
            "type": "StructuredAction",
            "role": "action",
            "label": "Structured action",
            "params_schema": {
                "provider_ref": {"type": "ref", "ref_kind": "provider"},
                "backend": {"type": "string", "enum": ["upstream", "foundry"], "default": "upstream"},
                "deployment": {"type": "string", "advanced": True},
                "temperature": {"type": "number", "default": 0.2, "min": 0.0, "max": 2.0},
                "secret_ref": {"type": "ref", "ref_kind": "secret"},
            },
        },
    ]


def build_capability_document() -> dict[str, Any]:
    kb_registry = KnowledgeBaseRegistry()
    retrieve_registry = RetrieveStrategyRegistry()
    return {
        "schema_version": 1,
        "module_definitions": _module_definitions(),
        "provider_refs": [
            {"ref": "upstream_default", "kind": "openai_compatible", "label": "Upstream default", "trusted": False},
            {"ref": "foundry_default", "kind": "azure_foundry", "label": "Azure Foundry default", "trusted": False},
        ],
        "profile_refs": [
            {
                "ref": "shoe_store",
                "label": "鞋店客服 demo profile",
                "retrieve_template_ref": "shoe_store_catalog_search",
            }
        ],
        "retrieve_strategy_refs": retrieve_registry.list_strategies(),
        "retrieve_template_refs": retrieve_registry.list_templates(),
        "knowledge_base_refs": kb_registry.list_definitions(),
        "execution_env_refs": [
            {
                "ref": "local-default",
                "kind": "uv",
                "label": "Local uv default",
                "enabled": True,
            }
        ],
        "export_capabilities": {
            "yaml": True,
            "json": True,
            "python_preview": True,
            "runnable_bundle": True,
            "secret_redaction": True,
            "required_files": ["main.py", "workflow.yaml", "profile.yaml", "registries.yaml"],
        },
        "feature_flags": {
            "inline_python_local": True,
            "inline_python_hosted": False,
        },
    }
