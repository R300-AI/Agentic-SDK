from __future__ import annotations

import os
from dataclasses import asdict, dataclass

from playground_v2.services.source_builder import BuilderSourceConfig, config_from_source
from playground_v2.services.workflow_reachability import reachable_openai_roles


_LEGACY_SELECTION_KEY = "model_endpoint"


@dataclass(frozen=True)
class ModelEndpoint:
    id: str
    label: str
    model: str
    base_url: str
    base_url_env: str
    api_key_env: str


@dataclass(frozen=True)
class OpenAIRequirement:
    role: str
    role_label: str
    module_name: str
    module_label: str


class MissingEndpointCredentials(ValueError):
    def __init__(self, role_label: str, endpoint: ModelEndpoint | None, missing_envs: list[str]) -> None:
        missing = "、".join(missing_envs)
        if endpoint is None:
            super().__init__(f"{role_label} 需要模型 endpoint。請在 .env 宣告 {missing}。")
        else:
            super().__init__(f"{role_label} 選用了 {endpoint.label}，請在 .env 填入 {missing}。")
        self.role_label = role_label
        self.endpoint = endpoint
        self.missing_envs = missing_envs


def endpoint_options() -> list[dict[str, str]]:
    return [asdict(endpoint) for endpoint in _model_endpoints()]


def openai_requirements_from_source(python_source: str | None) -> list[dict[str, str]]:
    return [asdict(requirement) for requirement in _openai_requirements(config_from_source(python_source))]


def endpoint_state(python_source: str | None, selections: dict[str, str] | None) -> dict[str, object]:
    requirements = _openai_requirements(config_from_source(python_source))
    normalized = normalize_endpoint_selections(python_source, selections)
    selected_endpoints = {
        requirement.role: _endpoint_for_role(requirement.role, normalized)
        for requirement in requirements
    }
    missing_envs_by_role = {
        requirement.role: _missing_endpoint_envs(selected_endpoints[requirement.role])
        for requirement in requirements
    }
    configured_roles = {
        requirement.role: not missing_envs_by_role[requirement.role]
        for requirement in requirements
    }
    return {
        "requirements": [asdict(requirement) for requirement in requirements],
        "endpoints": endpoint_options(),
        "selections": normalized,
        "selected_endpoints": {
            role: asdict(endpoint) if endpoint else None
            for role, endpoint in selected_endpoints.items()
        },
        "missing_envs_by_role": missing_envs_by_role,
        "configured": all(configured_roles.values()) if requirements else True,
        "configured_roles": configured_roles,
    }


def normalize_endpoint_selections(python_source: str | None, selections: dict[str, str] | None) -> dict[str, str]:
    requirements = _openai_requirements(config_from_source(python_source))
    if not requirements:
        return {}

    raw = selections or {}
    endpoints_by_id = _endpoints_by_id()
    if not endpoints_by_id:
        return {}

    default_endpoint_id = next(iter(endpoints_by_id))
    legacy_endpoint_id = str(raw.get(_LEGACY_SELECTION_KEY) or "")
    normalized: dict[str, str] = {}
    for requirement in requirements:
        endpoint_id = str(raw.get(requirement.role) or legacy_endpoint_id or default_endpoint_id)
        if endpoint_id not in endpoints_by_id:
            endpoint_id = default_endpoint_id
        normalized[requirement.role] = endpoint_id
    return normalized


def endpoint_params_for_role(role: str, selections: dict[str, str] | None) -> dict[str, str]:
    endpoint = _endpoint_for_role(role, selections or {})
    missing_envs = _missing_endpoint_envs(endpoint)
    if missing_envs:
        raise MissingEndpointCredentials(_role_label(role), endpoint, missing_envs)
    api_key = _api_key_for_role(endpoint, role)
    return {"api_key": api_key, "base_url": endpoint.base_url, "model": endpoint.model}


def _openai_requirements(config: BuilderSourceConfig) -> list[OpenAIRequirement]:
    requirements: list[OpenAIRequirement] = []
    reachable_roles = reachable_openai_roles(config)
    if "perceive" in reachable_roles:
        requirements.append(OpenAIRequirement("perceive", "輸入解析器", config.perceive_module, "Perceive"))
    if "plan" in reachable_roles:
        requirements.append(OpenAIRequirement("plan", "流程路由器", "NextStepPlan", "Plan"))
    if "action" in reachable_roles:
        requirements.append(OpenAIRequirement("action", "模型回覆器", config.action_module, "Action"))
    if "reflect" in reachable_roles:
        requirements.append(OpenAIRequirement("reflect", "回覆檢核器", "ResponseCheckReflect", "Reflect"))
    return requirements


def _endpoint_for_role(role: str, selections: dict[str, str]) -> ModelEndpoint | None:
    endpoints_by_id = _endpoints_by_id()
    endpoint_id = selections.get(role, selections.get(_LEGACY_SELECTION_KEY, ""))
    if endpoint_id:
        return endpoints_by_id.get(endpoint_id)
    return next(iter(endpoints_by_id.values()), None)


def _missing_endpoint_envs(endpoint: ModelEndpoint | None) -> list[str]:
    if endpoint is None:
        return ["<PREFIX>_MODEL", "<PREFIX>_BASE_URL", "<PREFIX>_API_KEY"]
    missing: list[str] = []
    if not endpoint.base_url.strip():
        missing.append(endpoint.base_url_env)
    if not _api_key_for_role(endpoint, ""):
        missing.append(endpoint.api_key_env)
    return missing


def _api_key_for_role(endpoint: ModelEndpoint, role: str) -> str:
    return _env_value(endpoint.api_key_env)


def _role_label(role: str) -> str:
    return {
        "perceive": "輸入解析器",
        "plan": "流程路由器",
        "action": "模型回覆器",
        "reflect": "回覆檢核器",
    }.get(role, role)


def _model_endpoints() -> tuple[ModelEndpoint, ...]:
    return _configured_model_endpoints()


def _configured_model_endpoints() -> tuple[ModelEndpoint, ...]:
    endpoints: list[ModelEndpoint] = []
    for model_env in sorted(key for key, value in _normalized_env_items() if key.endswith("_MODEL") and value.strip()):
        env_prefix = model_env[: -len("_MODEL")]
        if _is_module_prefix(env_prefix):
            continue
        model = _env_value(model_env).strip()
        label = _env_value(f"{env_prefix}_LABEL", _display_label_for_model(model)).strip() or _display_label_for_model(model)
        base_url_env = f"{env_prefix}_BASE_URL"
        base_url = _env_value(base_url_env).strip()
        api_key_env = f"{env_prefix}_API_KEY"
        endpoints.append(
            ModelEndpoint(
                id=_model_id(env_prefix),
                label=label,
                model=model,
                base_url=base_url,
                base_url_env=base_url_env,
                api_key_env=api_key_env,
            )
        )
    return _dedupe_endpoints(endpoints)


def _endpoints_by_id() -> dict[str, ModelEndpoint]:
    return {endpoint.id: endpoint for endpoint in _model_endpoints()}


def _dedupe_endpoints(endpoints: object) -> tuple[ModelEndpoint, ...]:
    deduped: dict[str, ModelEndpoint] = {}
    for endpoint in endpoints:
        if isinstance(endpoint, ModelEndpoint) and endpoint.id not in deduped:
            deduped[endpoint.id] = endpoint
    return tuple(deduped.values())


def _model_id(model: str) -> str:
    normalized = "-".join(model.strip().lower().replace(":", "-").replace("_", "-").split())
    return normalized or "model"


def _display_label_for_model(model: str) -> str:
    return model.removeprefix("agentic-sdk-")


def _is_module_prefix(env_prefix: str) -> bool:
    return env_prefix in {"PERCEIVE", "PLAN", "ACTION", "REFLECT"}


def _env_value(name: str, default: str = "") -> str:
    return _normalized_env_map().get(name, default)


def _normalized_env_items() -> list[tuple[str, str]]:
    return list(_normalized_env_map().items())


def _normalized_env_map() -> dict[str, str]:
    values: dict[str, str] = {}
    for key, value in os.environ.items():
        clean_key = _clean_env_key(key)
        if key == clean_key:
            values[clean_key] = value
    for key, value in os.environ.items():
        clean_key = _clean_env_key(key)
        if clean_key not in values:
            values[clean_key] = value
    return values


def _clean_env_key(key: str) -> str:
    return key.lstrip("\ufeff")