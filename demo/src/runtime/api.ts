/** Gateway API 呼叫薄封裝。 */

import type { Attachment } from "../types";
import type { TelemetryEvent } from "./types";
import {
  getGatewayUrl,
  getManagedAgentId,
  getManagedApiBase,
  getManagedBridgeToken,
  getRuntimeMode,
  type RuntimeMode,
} from "./gatewayUrl";

export interface CapabilityRef {
  ref: string;
  label?: string;
  enabled?: boolean;
  [key: string]: unknown;
}

export interface NodeDefinition {
  type: string;
  role: string;
  label: string;
  params_schema: Record<string, unknown>;
}

export interface CapabilityDocument {
  schema_version: number;
  node_definitions: NodeDefinition[];
  provider_refs: CapabilityRef[];
  profile_refs: CapabilityRef[];
  retrieve_strategy_refs: CapabilityRef[];
  retrieve_template_refs: CapabilityRef[];
  knowledge_base_refs: CapabilityRef[];
  execution_env_refs: CapabilityRef[];
  export_capabilities: Record<string, unknown>;
  feature_flags: Record<string, boolean>;
}

interface RunResponse {
  workflow_id: string;
  stream_url: string;
  result_url?: string;
}

export interface AgentSummary {
  agent_id: string;
  agent_name: string;
  description: string;
  execution_backend: string;
  updated_at: string | null;
  last_run_at: string | null;
}

export interface AgentDetail extends AgentSummary {
  workflow_yaml: string;
  entry_node?: string;
  owner_username?: string;
  created_at?: string | null;
}

export interface AgentListResponse {
  items: AgentSummary[];
}

export interface WorkflowResultData {
  workflow_id: string;
  final_message: string;
  aborted: boolean;
  abort_reason?: string;
  visit_counts?: Record<string, number>;
  usage?: { model?: string; input_tokens?: number; output_tokens?: number };
}

export interface KnowledgeBasePreviewHit {
  id: string;
  title: string;
  score: number;
  source: string;
}

export interface KnowledgeBasePreviewData {
  knowledge_base_ref: string;
  query: string;
  hits: KnowledgeBasePreviewHit[];
}

function getManagedCollectionBase(): string {
  const apiBase = getManagedApiBase();
  if (!apiBase) {
    throw new Error("Managed mode 缺少 AI Hub API base。請從 AI Hub 管理頁重新開啟 Playground。");
  }
  return `${apiBase}/api/agent-workspace-bridge/agents`;
}

function getManagedAgentBase(agentId: string): string {
  return `${getManagedCollectionBase()}/${encodeURIComponent(agentId)}`;
}

function getManagedHeaders(): HeadersInit {
  const token = getManagedBridgeToken();
  if (!token) {
    throw new Error("Managed mode 缺少 bridge token。請從 AI Hub 管理頁重新開啟 Playground。");
  }
  return { "X-Agent-Workspace-Token": token };
}

function withManagedStreamToken(url: string): string {
  const token = getManagedBridgeToken();
  if (!token) {
    throw new Error("Managed mode 缺少 bridge token。請從 AI Hub 管理頁重新開啟 Playground。");
  }
  const next = new URL(url, window.location.href);
  next.searchParams.set("token", token);
  return next.toString();
}

async function fetchJson(url: string, options?: RequestInit): Promise<Response> {
  return options ? fetch(url, options) : fetch(url);
}

function requireManagedAgentId(): string {
  const agentId = getManagedAgentId().trim();
  if (!agentId) {
    throw new Error("Managed mode 需要先選擇或建立一個已保存的 Agent。");
  }
  return agentId;
}

export async function fetchCapabilities(): Promise<CapabilityDocument> {
  const url = `${getGatewayUrl()}/v1/capabilities`;
  const resp = await fetch(url);
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`GET /v1/capabilities 失敗 (${resp.status}):${text}`);
  }
  return resp.json();
}

export async function previewKnowledgeBase(
  knowledgeBaseRef: string,
  query: string,
  topK = 3
): Promise<KnowledgeBasePreviewData> {
  const params = new URLSearchParams({ query, top_k: String(topK) });
  const baseUrl = `${getGatewayUrl()}/v1/knowledge-bases/${encodeURIComponent(knowledgeBaseRef)}/preview`;
  const resp = await fetch(`${baseUrl}?${params}`);
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`GET knowledge base preview 失敗 (${resp.status}):${text}`);
  }
  return resp.json();
}

export async function runWorkflow(
  workflowYaml: string,
  userMessage: string,
  attachments?: Attachment[]
): Promise<RunResponse> {
  const mode = getRuntimeMode();
  const managedAgentId = mode === "managed" ? requireManagedAgentId() : "";
  const body: Record<string, unknown> = {
    user_message: userMessage,
  };
  if (mode !== "managed") {
    body.workflow_yaml = workflowYaml;
  }
  if (attachments && attachments.length > 0) {
    body.attachments = attachments;
  }
  const runUrl = mode === "managed"
    ? `${getManagedAgentBase(managedAgentId)}/run`
    : `${getGatewayUrl()}/v1/workflow/run`;
  const resp = await fetch(runUrl, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(mode === "managed" ? getManagedHeaders() : {}),
    },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`POST runWorkflow 失敗 (${resp.status}):${text}`);
  }
  return resp.json();
}

/** 取工作流結果;backend 寫入有微小 race window,做 3 次 100ms backoff retry。 */
export async function fetchWorkflowResult(
  workflowId: string
): Promise<WorkflowResultData> {
  const mode = getRuntimeMode();
  const managedAgentId = mode === "managed" ? requireManagedAgentId() : "";
  const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
  for (let attempt = 0; attempt < 5; attempt++) {
    const resultUrl = mode === "managed"
      ? `${getManagedAgentBase(managedAgentId)}/runs/${encodeURIComponent(workflowId)}/result`
      : `${getGatewayUrl()}/v1/workflow/${workflowId}/result`;
      const resp = await fetchJson(resultUrl, mode === "managed" ? { headers: getManagedHeaders() } : undefined);
    if (resp.ok) return resp.json();
    if (resp.status !== 404) {
      throw new Error(`GET workflow result 失敗 (${resp.status})`);
    }
    await sleep(100 * (attempt + 1));
  }
  throw new Error("workflow result 5 次重試後仍未就緒");
}

/** 訂閱 SSE 事件;handler 回 true 代表自行 close;handler 回 false 由 stream 自行終止。 */
export function subscribeStream(
  workflowId: string,
  handler: (event: TelemetryEvent) => void,
  onError?: (err: Event) => void,
  onClose?: () => void
): () => void {
  const mode = getRuntimeMode();
  const managedAgentId = mode === "managed" ? requireManagedAgentId() : "";
  const url = mode === "managed"
    ? withManagedStreamToken(`${getManagedAgentBase(managedAgentId)}/runs/${encodeURIComponent(workflowId)}/stream`)
    : `${getGatewayUrl()}/v1/workflow/${workflowId}/stream`;
  const es = new EventSource(url);

  let closed = false;
  const close = () => {
    if (closed) return;
    closed = true;
    es.close();
    onClose?.();
  };

  es.onmessage = (msg) => {
    try {
      const data = JSON.parse(msg.data) as TelemetryEvent;
      handler(data);
    } catch {
      // 忽略無法解析的訊息(例如 timeout 自我訊號)
    }
  };
  es.onerror = (err) => {
    onError?.(err);
    close();
  };

  return close;
}

export async function listAgents(): Promise<AgentListResponse> {
  const mode = getRuntimeMode();
  const resp = await fetchJson(mode === "managed" ? getManagedCollectionBase() : '/api/me/agents', mode === "managed" ? { headers: getManagedHeaders() } : undefined);
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`GET /api/me/agents 失敗 (${resp.status}):${text}`);
  }
  return resp.json();
}

export async function loadAgent(agentId: string): Promise<AgentDetail> {
  const mode = getRuntimeMode();
  const url = mode === "managed" ? getManagedAgentBase(agentId) : `/api/me/agents/${encodeURIComponent(agentId)}`;
  const resp = await fetchJson(url, mode === "managed" ? { headers: getManagedHeaders() } : undefined);
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`GET /api/me/agents/${agentId} 失敗 (${resp.status}):${text}`);
  }
  return resp.json();
}

export async function saveAgent(payload: {
  agentId?: string;
  agentName: string;
  description: string;
  workflowYaml: string;
  executionBackend: string;
  csrfToken?: string;
}): Promise<AgentDetail> {
  const mode = getRuntimeMode();
  const url = mode === "managed"
    ? (payload.agentId ? getManagedAgentBase(payload.agentId) : getManagedCollectionBase())
    : (payload.agentId ? `/api/me/agents/${encodeURIComponent(payload.agentId)}` : '/api/me/agents');
  const resp = await fetch(
    url,
    {
      method: payload.agentId ? 'PUT' : 'POST',
      headers: {
        'Content-Type': 'application/json',
        ...(mode === "managed" ? getManagedHeaders() : {}),
        ...(payload.csrfToken ? { 'X-CSRF-Token': payload.csrfToken } : {}),
      },
      body: JSON.stringify({
        agent_name: payload.agentName,
        description: payload.description,
        workflow_yaml: payload.workflowYaml,
        execution_backend: payload.executionBackend,
      }),
    }
  );
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`SAVE /api/me/agents 失敗 (${resp.status}):${text}`);
  }
  return resp.json();
}

export async function deleteAgent(agentId: string, csrfToken?: string): Promise<void> {
  const mode = getRuntimeMode();
  const resp = await fetch(mode === "managed" ? getManagedAgentBase(agentId) : `/api/me/agents/${encodeURIComponent(agentId)}`, {
    method: 'DELETE',
    headers: {
      ...(mode === "managed" ? getManagedHeaders() : {}),
      ...(csrfToken ? { 'X-CSRF-Token': csrfToken } : {}),
    },
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`DELETE /api/me/agents/${agentId} 失敗 (${resp.status}):${text}`);
  }
}
