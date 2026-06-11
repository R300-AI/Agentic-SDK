/** Runtime 狀態 — 由 SSE 事件驅動的節點動畫狀態。 */

export type NodeStatus = "idle" | "running" | "ok" | "fail";

/** 由 SSE 推送的事件;對齊 `agentic_sdk/observability/events.py`。 */
export interface TelemetryEvent {
  ts?: number;
  event_name: string;
  workflow_id?: string;
  workflow_node?: string;
  workflow_next_node?: string;
  workflow_status?: string;
  workflow_reason?: string;
  workflow_node_visit?: number;
  gen_ai_response_model?: string;
  gen_ai_usage_input_tokens?: number;
  gen_ai_usage_output_tokens?: number;
  delta_text?: string;
  delta_index?: number;
  [key: string]: unknown;
}

export interface ChatMessage {
  role: "user" | "assistant" | "system";
  content: string;
  metadata?: {
    model?: string;
    elapsed_ms?: number;
    input_tokens?: number;
    output_tokens?: number;
  };
}
