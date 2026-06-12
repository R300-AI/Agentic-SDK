/** Gateway API 呼叫薄封裝。 */

import type { Attachment } from "../types";
import type { TelemetryEvent } from "./types";
import { getGatewayUrl } from "./gatewayUrl";

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

export async function fetchCapabilities(): Promise<CapabilityDocument> {
  const resp = await fetch(`${getGatewayUrl()}/v1/capabilities`);
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
  const resp = await fetch(
    `${getGatewayUrl()}/v1/knowledge-bases/${encodeURIComponent(knowledgeBaseRef)}/preview?${params}`
  );
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`GET /v1/knowledge-bases/${knowledgeBaseRef}/preview 失敗 (${resp.status}):${text}`);
  }
  return resp.json();
}

export async function runWorkflow(
  workflowYaml: string,
  userMessage: string,
  attachments?: Attachment[]
): Promise<RunResponse> {
  const body: Record<string, unknown> = {
    workflow_yaml: workflowYaml,
    user_message: userMessage,
  };
  if (attachments && attachments.length > 0) {
    body.attachments = attachments;
  }
  const resp = await fetch(`${getGatewayUrl()}/v1/workflow/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!resp.ok) {
    const text = await resp.text();
    throw new Error(`POST /v1/workflow/run 失敗 (${resp.status}):${text}`);
  }
  return resp.json();
}

/** 取工作流結果;backend 寫入有微小 race window,做 3 次 100ms backoff retry。 */
export async function fetchWorkflowResult(
  workflowId: string
): Promise<WorkflowResultData> {
  const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
  for (let attempt = 0; attempt < 5; attempt++) {
    const resp = await fetch(`${getGatewayUrl()}/v1/workflow/${workflowId}/result`);
    if (resp.ok) return resp.json();
    if (resp.status !== 404) {
      throw new Error(`GET /v1/workflow/${workflowId}/result 失敗 (${resp.status})`);
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
  const url = `${getGatewayUrl()}/v1/workflow/${workflowId}/stream`;
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
