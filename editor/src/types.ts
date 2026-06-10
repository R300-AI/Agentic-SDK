/** Python `agentic_sdk/workflow/config.py` 的 TypeScript 對應。 */

export interface NodeSpec {
  type: string;
  params?: Record<string, unknown>;
  compute_target?: string;
}

export interface GateConfig {
  max_node_hops: number;
  max_revisit: number;
  timeout_sec: number;
}

export interface WorkflowConfig {
  version: "1";
  name?: string;
  entry: string;
  nodes: Record<string, NodeSpec>;
  gates: GateConfig;
}

export interface PerceiveOption {
  label: string;
  value: string;
  intent: string;
}

/** M6-4 — 節點計算資源綁定。對應 NodeSpec.compute_target。 */
export const COMPUTE_TARGET_OPTIONS = [
  { label: "Ryzen AI NPU", value: "ryzen_ai" },
  { label: "Azure Foundry", value: "azure_foundry" },
  { label: "本機 CPU", value: "local_cpu" },
] as const;

export const REFLECT_MODE_OPTIONS = [
  { label: "規則式(零成本)", value: "rule_based" },
  { label: "LLM 反思(Reflexion)", value: "llm" },
] as const;

export const FIVE_NODE_NAMES = ["perceive", "plan", "retrieve", "reflect", "action"] as const;
export type NodeName = (typeof FIVE_NODE_NAMES)[number];

/** UI 顯示順序固定;與 SDK 端 entry 與邊白名單對齊。 */
export const NODE_DISPLAY_ORDER: NodeName[] = [
  "perceive",
  "plan",
  "retrieve",
  "action",
  "reflect",
];

/** UI 端「Action backend 下拉」與 SDK `NodeSpec.type` 字串映射(M5-1 設計決策)。 */
export const ACTION_BACKEND_OPTIONS = [
  { label: "AMD NPU 上游", value: "upstream", typeString: "upstream_completion" },
  { label: "Azure Foundry", value: "foundry", typeString: "foundry_completion" },
] as const;

/** Plan system_prompt 三模板;與 `ReActPlan.SYSTEM_PROMPT_TEMPLATES` 一致。 */
export const PLAN_PROMPT_TEMPLATES: Record<string, string> = {
  react:
    "PLAN. 你是 Agent 工作流的規劃節點。閱讀 user message 與 perceived intent 後," +
    "決定下一個節點為 'retrieve'(需要外部知識)或 'action'(可直接產出回應)。" +
    "只回 JSON,欄位:thought (string)、next_node (string)。",
  cot:
    "PLAN (Chain-of-Thought). 在決定下一節點前,先在 thought 欄位以條列式逐步推理:" +
    "(1) 使用者問什麼、(2) 已有什麼資訊、(3) 缺什麼。再選 'retrieve' 或 'action'。" +
    "只回 JSON,欄位:thought (string)、next_node (string)。",
  plan_and_solve:
    "PLAN (Plan-and-Solve, Wang 2023). 在 thought 欄位先列出完成本任務的子步驟," +
    "然後判斷第一個子步驟是需要 'retrieve' 還是可直接 'action'。" +
    "只回 JSON,欄位:thought (string)、next_node (string)。",
};

export const REFLECT_ON_FAILURE_OPTIONS = [
  { label: "失敗時回 Plan 重試", value: "retry_plan" },
  { label: "失敗時直接結束", value: "end" },
] as const;
