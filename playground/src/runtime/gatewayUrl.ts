/** Runtime Gateway URL 管理。
 *
 * 優先順序：localStorage → VITE_GATEWAY_URL 環境變數 → ""（相對路徑，供 dev Vite proxy 使用）
 */

const STORAGE_KEY = "agentic_sdk.gateway_url";
const MODE_KEY = "agentic_sdk.runtime_mode";
const AGENT_ID_KEY = "agentic_sdk.agent_id";
const MANAGED_API_BASE_KEY = "agentic_sdk.managed_api_base";
const MANAGED_TOKEN_KEY = "agentic_sdk.managed_bridge_token";
const MEMORY_STORAGE = new Map<string, string>();

/** 建置時注入的預設值；可透過 VITE_GATEWAY_URL 設定。 */
const ENV_DEFAULT: string = (import.meta.env.VITE_GATEWAY_URL as string | undefined) ?? "";

export type RuntimeMode = "gateway" | "managed";

export interface RuntimeBootstrap {
  runtimeMode?: RuntimeMode;
  agentId?: string;
  apiBase?: string;
  token?: string;
}

function readStorage(key: string): string {
  try {
    return localStorage.getItem(key) ?? "";
  } catch {
    return MEMORY_STORAGE.get(key) ?? "";
  }
}

function writeStorage(key: string, value: string): void {
  try {
    if (value) localStorage.setItem(key, value);
    else localStorage.removeItem(key);
  } catch {
    if (value) MEMORY_STORAGE.set(key, value);
    else MEMORY_STORAGE.delete(key);
  }
}

export function getGatewayUrl(): string {
  const stored = readStorage(STORAGE_KEY);
  return stored && stored.length > 0 ? stored : ENV_DEFAULT;
}

export function setGatewayUrl(url: string): void {
  const trimmed = url.replace(/\/+$/, "");
  writeStorage(STORAGE_KEY, trimmed);
}

function normalizeUrl(url: string): string {
  return String(url || "").trim().replace(/\/+$/, "");
}

export function getRuntimeMode(): RuntimeMode {
  const stored = readStorage(MODE_KEY);
  return stored === "managed" ? "managed" : "gateway";
}

export function setRuntimeMode(mode: RuntimeMode): void {
  writeStorage(MODE_KEY, mode);
}

export function getManagedAgentId(): string {
  return readStorage(AGENT_ID_KEY);
}

export function setManagedAgentId(agentId: string): void {
  writeStorage(AGENT_ID_KEY, agentId.trim());
}

export function getManagedApiBase(): string {
  return normalizeUrl(readStorage(MANAGED_API_BASE_KEY));
}

export function setManagedApiBase(url: string): void {
  writeStorage(MANAGED_API_BASE_KEY, normalizeUrl(url));
}

export function getManagedBridgeToken(): string {
  return readStorage(MANAGED_TOKEN_KEY).trim();
}

export function setManagedBridgeToken(token: string): void {
  writeStorage(MANAGED_TOKEN_KEY, String(token || "").trim());
}

export function parseRuntimeBootstrap(search: string): RuntimeBootstrap {
  const params = new URLSearchParams(search.startsWith("?") ? search : `?${search}`);
  const runtimeMode = params.get("runtimeMode") === "managed" ? "managed" : undefined;
  const agentId = params.get("agentId")?.trim() ?? "";
  const apiBase = normalizeUrl(params.get("apiBase") ?? "");
  const token = (params.get("token") ?? "").trim();
  return {
    runtimeMode: runtimeMode || (agentId || apiBase || token ? "managed" : undefined),
    agentId: agentId || undefined,
    apiBase: apiBase || undefined,
    token: token || undefined,
  };
}

function applyRuntimeBootstrap(bootstrap: RuntimeBootstrap): void {
  if (bootstrap.runtimeMode) setRuntimeMode(bootstrap.runtimeMode);
  if (bootstrap.agentId !== undefined) setManagedAgentId(bootstrap.agentId);
  if (bootstrap.apiBase !== undefined) setManagedApiBase(bootstrap.apiBase);
  if (bootstrap.token !== undefined) setManagedBridgeToken(bootstrap.token);
}

function stripBootstrapParams(): void {
  if (typeof window === "undefined" || !window.history?.replaceState) return;
  const url = new URL(window.location.href);
  let changed = false;
  ["runtimeMode", "agentId", "apiBase", "token"].forEach((key) => {
    if (url.searchParams.has(key)) {
      url.searchParams.delete(key);
      changed = true;
    }
  });
  if (changed) {
    const next = `${url.pathname}${url.search}${url.hash}`;
    window.history.replaceState({}, document.title, next);
  }
}

if (typeof window !== "undefined") {
  const bootstrap = parseRuntimeBootstrap(window.location.search);
  if (bootstrap.runtimeMode || bootstrap.agentId || bootstrap.apiBase || bootstrap.token) {
    applyRuntimeBootstrap(bootstrap);
    stripBootstrapParams();
  }
}
