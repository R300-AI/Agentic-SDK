/** Runtime Gateway URL 管理。
 *
 * 優先順序：localStorage → VITE_GATEWAY_URL 環境變數 → ""（相對路徑，供 dev Vite proxy 使用）
 */

const STORAGE_KEY = "agentic_sdk.gateway_url";

/** 建置時注入的預設值；可透過 VITE_GATEWAY_URL 設定。 */
const ENV_DEFAULT: string = (import.meta.env.VITE_GATEWAY_URL as string | undefined) ?? "";

export function getGatewayUrl(): string {
  try {
    const stored = localStorage.getItem(STORAGE_KEY);
    return stored && stored.length > 0 ? stored : ENV_DEFAULT;
  } catch {
    return ENV_DEFAULT;
  }
}

export function setGatewayUrl(url: string): void {
  try {
    const trimmed = url.replace(/\/+$/, ""); // 移除結尾斜線
    if (trimmed) localStorage.setItem(STORAGE_KEY, trimmed);
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    /* localStorage 不可用時靜默失敗 */
  }
}
