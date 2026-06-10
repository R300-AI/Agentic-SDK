/** Gateway API 呼叫薄封裝。 */

import type { TelemetryEvent } from "./types";

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

export async function runWorkflow(
  workflowYaml: string,
  userMessage: string
): Promise<RunResponse> {
  const resp = await fetch("/v1/workflow/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      workflow_yaml: workflowYaml,
      user_message: userMessage,
    }),
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
    const resp = await fetch(`/v1/workflow/${workflowId}/result`);
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
  const url = `/v1/workflow/${workflowId}/stream`;
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
