from __future__ import annotations

from dataclasses import asdict, dataclass

from playground.services.key_vault_config import key_vault_settings
from playground.services.source_builder import BuilderSourceConfig, config_from_source
from playground.services.workflow_reachability import reachable_openai_roles, reachable_workflow_roles


@dataclass(frozen=True)
class ModelEndpoint:
    id: str
    label: str
    model: str
    model_env: str
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
            super().__init__(f"{role_label} 需要模型 endpoint。請在 Key Vault 設定 {missing}。")
        else:
            super().__init__(f"{role_label} 選用了 {endpoint.label}，請確認 Key Vault 設定 {missing}。")
        self.role_label = role_label
        self.endpoint = endpoint
        self.missing_envs = missing_envs


class MissingEndpointBinding(ValueError):
    def __init__(self, role_label: str) -> None:
        super().__init__(f"{role_label} 尚未選擇模型 endpoint。請先完成部署選項設定。")
        self.role_label = role_label


def endpoint_options() -> list[dict[str, str]]:
    return [asdict(endpoint) for endpoint in _model_endpoints()]


def openai_requirements_from_source(python_source: str | None) -> list[dict[str, str]]:
    return [asdict(requirement) for requirement in _openai_requirements(config_from_source(python_source))]


def endpoint_state(python_source: str | None, selections: dict[str, str] | None) -> dict[str, object]:
    requirements = _deployment_requirements(config_from_source(python_source))
    normalized = normalize_endpoint_selections(python_source, selections)
    selected_endpoints = {
        requirement.role: _endpoint_for_role(requirement.role, normalized)
        for requirement in requirements
    }
    missing_envs_by_role = {
        requirement.role: _missing_endpoint_envs(requirement.role, selected_endpoints[requirement.role])
        for requirement in requirements
    }
    binding_missing_roles = {
        requirement.role: selected_endpoints[requirement.role] is None
        for requirement in requirements
    }
    credential_missing_roles = {
        requirement.role: bool(missing_envs_by_role[requirement.role]) and not binding_missing_roles[requirement.role]
        for requirement in requirements
    }
    configured_roles = {
        requirement.role: not missing_envs_by_role[requirement.role]
        for requirement in requirements
    }
    return {
        "requirements": [
            {
                **asdict(requirement),
                "options": [asdict(endpoint) for endpoint in _endpoint_options_for_role(requirement.role)],
            }
            for requirement in requirements
        ],
        "endpoints": endpoint_options(),
        "selections": normalized,
        "selected_endpoints": {
            role: asdict(endpoint) if endpoint else None
            for role, endpoint in selected_endpoints.items()
        },
        "missing_envs_by_role": missing_envs_by_role,
        "binding_missing_roles": binding_missing_roles,
        "credential_missing_roles": credential_missing_roles,
        "configured": all(configured_roles.values()) if requirements else True,
        "configured_roles": configured_roles,
    }


def normalize_endpoint_selections(python_source: str | None, selections: dict[str, str] | None) -> dict[str, str]:
    requirements = _deployment_requirements(config_from_source(python_source))
    if not requirements:
        return {}

    raw = selections or {}
    normalized: dict[str, str] = {}
    for requirement in requirements:
        endpoints_by_id = _endpoints_by_id(_endpoint_options_for_role(requirement.role))
        if not endpoints_by_id:
            continue
        endpoint_id = str(raw.get(requirement.role) or "")
        if endpoint_id in endpoints_by_id:
            normalized[requirement.role] = endpoint_id
    return normalized


def endpoint_params_for_role(role: str, selections: dict[str, str] | None) -> dict[str, str]:
    endpoint = _endpoint_for_role(role, selections or {})
    if endpoint is None:
        raise MissingEndpointBinding(_role_label(role))
    missing_envs = _missing_endpoint_envs(role, endpoint)
    if missing_envs:
        raise MissingEndpointCredentials(_role_label(role), endpoint, missing_envs)
    api_key = _api_key_for_role(endpoint, role)
    if role == "retrieve":
        return {"api_key": api_key, "base_url": endpoint.base_url, "embedding_model": endpoint.model}
    return {"api_key": api_key, "base_url": endpoint.base_url, "model": endpoint.model}


def endpoint_env_bindings_for_source(python_source: str | None, selections: dict[str, str] | None) -> dict[str, dict[str, str]]:
    requirements = _deployment_requirements(config_from_source(python_source))
    normalized = normalize_endpoint_selections(python_source, selections)
    bindings: dict[str, dict[str, str]] = {}
    for requirement in requirements:
        endpoint = _endpoint_for_role(requirement.role, normalized)
        if endpoint is None:
            continue
        bindings[requirement.role] = {
            "api_key_env": endpoint.api_key_env,
            "base_url_env": endpoint.base_url_env,
            "model_env": endpoint.model_env,
        }
    return bindings


def _deployment_requirements(config: BuilderSourceConfig) -> list[OpenAIRequirement]:
    requirements: list[OpenAIRequirement] = []
    reachable_llm_roles = reachable_openai_roles(config)
    reachable_roles = reachable_workflow_roles(config)
    if "perceive" in reachable_llm_roles:
        requirements.append(OpenAIRequirement("perceive", "輸入解析器", config.perceive_module, "Perceive"))
    if "retrieve" in reachable_roles and config.retrieve_module == "SemanticRetrieve":
        requirements.append(OpenAIRequirement("retrieve", "語意搜尋", config.retrieve_module, "Retrieve"))
    if "action" in reachable_llm_roles:
        requirements.append(OpenAIRequirement("action", "模型回覆器", config.action_module, "Action"))
    if "reflect" in reachable_llm_roles:
        requirements.append(OpenAIRequirement("reflect", "回覆檢核器", "ResponseCheckReflect", "Reflect"))
    return requirements


def _endpoint_for_role(role: str, selections: dict[str, str]) -> ModelEndpoint | None:
    endpoints_by_id = _endpoints_by_id(_endpoint_options_for_role(role))
    endpoint_id = selections.get(role, "")
    return endpoints_by_id.get(endpoint_id)


def _missing_endpoint_envs(role: str, endpoint: ModelEndpoint | None) -> list[str]:
    if endpoint is None:
        if role == "retrieve":
            return ["<PREFIX>_DEPLOYMENT_NAME", "<PREFIX>_ENDPOINT", "<PREFIX>_API_KEY"]
        return ["<PREFIX>_MODEL", "<PREFIX>_BASE_URL", "<PREFIX>_API_KEY"]
    missing: list[str] = []
    if not endpoint.model.strip():
        missing.append(endpoint.model_env)
    if not endpoint.base_url.strip():
        missing.append(endpoint.base_url_env)
    if not _api_key_for_role(endpoint, ""):
        missing.append(endpoint.api_key_env)
    return missing


def _api_key_for_role(endpoint: ModelEndpoint, role: str) -> str:
    settings = key_vault_settings()
    for configured_endpoint in (*settings.chat_endpoints, *settings.embedding_endpoints):
        if configured_endpoint.id == endpoint.id:
            return configured_endpoint.api_key
    return ""


def _role_label(role: str) -> str:
    return {
        "perceive": "輸入解析器",
        "retrieve": "語意搜尋",
        "action": "模型回覆器",
        "reflect": "回覆檢核器",
    }.get(role, role)


def _model_endpoints() -> tuple[ModelEndpoint, ...]:
    return tuple(
        ModelEndpoint(
            id=endpoint.id,
            label=_display_label_for_model(endpoint.model),
            model=endpoint.model,
            model_env=f"{endpoint.id.upper().replace('-', '_')}_MODEL",
            base_url=endpoint.base_url,
            base_url_env=f"{endpoint.id.upper().replace('-', '_')}_BASE_URL",
            api_key_env=f"{endpoint.id.upper().replace('-', '_')}_API_KEY",
        )
        for endpoint in key_vault_settings().chat_endpoints
    )


def _embedding_endpoints() -> tuple[ModelEndpoint, ...]:
    return tuple(
        ModelEndpoint(
            id=endpoint.id,
            label=_display_label_for_model(endpoint.deployment_name),
            model=endpoint.deployment_name,
            model_env=f"{endpoint.id.upper().replace('-', '_')}_DEPLOYMENT_NAME",
            base_url=endpoint.endpoint,
            base_url_env=f"{endpoint.id.upper().replace('-', '_')}_ENDPOINT",
            api_key_env=f"{endpoint.id.upper().replace('-', '_')}_API_KEY",
        )
        for endpoint in key_vault_settings().embedding_endpoints
    )


def _endpoint_options_for_role(role: str) -> tuple[ModelEndpoint, ...]:
    if role == "retrieve":
        return _embedding_endpoints()
    return _model_endpoints()


def _endpoints_by_id(endpoints: tuple[ModelEndpoint, ...]) -> dict[str, ModelEndpoint]:
    return {endpoint.id: endpoint for endpoint in endpoints}


def _display_label_for_model(model: str) -> str:
    return model.removeprefix("agentic-sdk-")
