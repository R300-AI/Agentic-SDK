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

/** M8-2 — 節點 class 概念：使用者可在屬性面板切換實際 class，
 * 切換後 NodeSpec.type / params 對應更新；canvas 上的節點標題顯示 class label。
 *
 * 每個 NodeClass 描述一個可選的實作（後端 import path 對應到 SDK 真實存在的 class）。
 */
export interface NodeClass {
  /** 內部 key — 不外露 */
  value: string;
  /** Canvas / 下拉清單上顯示的 class 名（對齊 SDK 端類別） */
  label: string;
  /** 對應 NodeSpec.type 字串 */
  type: string;
  /** 切到此 class 時要強制 set 的 params；其餘保留 */
  enforceParams?: Record<string, unknown>;
  /** 額外提示 */
  hint?: string;
}

export const NODE_CLASSES: Record<NodeName, NodeClass[]> = {
  perceive: [
    {
      value: "rule_based",
      label: "RuleBasedPerceive",
      type: "builtin.perceive",
      hint: "以預先設定好的選項表對應使用者意圖，不需要呼叫 AI。適合流程固定、希望回應最快的場景。",
    },
  ],
  plan: [
    {
      value: "react",
      label: "ReActPlan",
      type: "builtin.plan",
      enforceParams: { system_prompt: PLAN_PROMPT_TEMPLATES.react },
      hint: "AI 先思考再行動，每步推理都會記錄下來。適合一般問答、需要判斷要查資料還是直接回答的場景。（<a href='https://arxiv.org/abs/2210.03629' target='_blank'>ReAct 論文</a>）",
    },
    {
      value: "cot",
      label: "ChainOfThoughtPlan",
      type: "builtin.plan",
      enforceParams: { system_prompt: PLAN_PROMPT_TEMPLATES.cot },
      hint: "AI 將思維途徑一步步列出再下結論，適合需要可追溯推理、便於檢查問題的場景。（<a href='https://arxiv.org/abs/2201.11903' target='_blank'>CoT 論文</a>）",
    },
    {
      value: "plan_and_solve",
      label: "PlanAndSolvePlan",
      type: "builtin.plan",
      enforceParams: { system_prompt: PLAN_PROMPT_TEMPLATES.plan_and_solve },
      hint: "AI 先把任務拆解成子步驟清單再逐步執行，適合工作流程複雜、目標需要多階段實現的場景。（<a href='https://arxiv.org/abs/2305.04091' target='_blank'>Plan-and-Solve 論文</a>）",
    },
  ],
  retrieve: [
    {
      value: "semantic",
      label: "SemanticRetrieve",
      type: "builtin.retrieve",
      hint: "從對話記憶中找出與目前問題最相關的資訊片段帶入下一步。top_k 決定取幾筆。（<a href='https://arxiv.org/abs/2005.11401' target='_blank'>RAG 論文</a>）",
    },
  ],
  reflect: [
    {
      value: "rule_based",
      label: "RuleBasedReflect",
      type: "builtin.reflect",
      enforceParams: { mode: "rule_based" },
      hint: "以預先定義的規則檢查 AI 回應是否合格，不需要呼叫 AI。適合檢查條件明確、要控制成本的場景。",
    },
    {
      value: "reflexion",
      label: "ReflexionReflect",
      type: "builtin.reflect",
      enforceParams: { mode: "llm" },
      hint: "AI 自我檢閱回應品質，不夠好會寫下改進建議並重試。適合輸出需要迭代優化的開放式任務。（<a href='https://arxiv.org/abs/2303.11366' target='_blank'>Reflexion 論文</a>）",
    },
  ],
  action: [
    {
      value: "foundry",
      label: "CompletionAction",
      type: "foundry_completion",
      hint: "將目前對話送出給 AI 產生最終回應，實際使用的 AI 模型由運算後端設定決定。",
    },
    {
      value: "upstream",
      label: "UpstreamCompletionAction",
      type: "upstream_completion",
      hint: "將對話送出給本機 AMD NPU 上的 AI 模型來回應，資料不離開裝置。",
    },
  ],
};

/** 由現有 NodeSpec 反推它屬於哪個 class。
 * 規則：先以 type 對齊；若 type 對齊到多個 class（例如 Plan 的三個 template），
 * 再以 enforceParams 是否完全成立判斷。
 */
export function detectNodeClass(nodeName: NodeName, spec: NodeSpec): NodeClass {
  const candidates = NODE_CLASSES[nodeName].filter((c) => c.type === spec.type);
  if (candidates.length === 0) return NODE_CLASSES[nodeName][0];
  if (candidates.length === 1) return candidates[0];
  // 多個 candidate（如 Plan 三個 template）— 比對 enforceParams
  const matched = candidates.find((c) => {
    if (!c.enforceParams) return false;
    return Object.entries(c.enforceParams).every(
      ([k, v]) => (spec.params ?? {})[k] === v
    );
  });
  return matched ?? candidates[0];
}

/** 切換 class：更新 type 與 enforceParams，其餘 params 原封不動。 */
export function applyNodeClass(spec: NodeSpec, klass: NodeClass): NodeSpec {
  return {
    ...spec,
    type: klass.type,
    params: { ...(spec.params ?? {}), ...(klass.enforceParams ?? {}) },
  };
}
