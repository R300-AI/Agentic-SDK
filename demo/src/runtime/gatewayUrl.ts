/** Runtime Gateway URL 管理。
 *
 * 優先順序：localStorage → VITE_GATEWAY_URL 環境變數 → ""（相對路徑，供 dev Vite proxy 使用）
 */

const STORAGE_KEY = "agentic_sdk.gateway_url";
const MODE_KEY = "agentic_sdk.runtime_mode";
const AGENT_ID_KEY = "agentic_sdk.agent_id";
const MEMORY_STORAGE = new Map<string, string>();

/** 建置時注入的預設值；可透過 VITE_GATEWAY_URL 設定。 */
const ENV_DEFAULT: string = (import.meta.env.VITE_GATEWAY_URL as string | undefined) ?? "";

export type RuntimeMode = "gateway" | "managed";

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
