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
  /** Perceive 傳給 Plan 的意圖識別碼，用於路由決策（如 product_recommendation）。 */
  intent?: string;
  /** 點該選項時是否引導使用者上傳附件（M9-5）。 */
  expects_attachment?: "image" | "file";
}

/** M9 — 多模態使用者輸入附件。 */
export interface Attachment {
  kind: "image" | "file";
  mime: string;
  /** RFC 2397 data URL 或 https URL。 */
  data_url: string;
  name?: string;
}

/** M6-4 — 節點計算資源綁定。對應 NodeSpec.compute_target。 */
export const COMPUTE_TARGET_OPTIONS = [
  { label: "雲端平台", value: "cloud" },
  { label: "工作站 / 伺服器", value: "workstation" },
  { label: "SoC 邊縁裝置", value: "soc_edge" },
] as const;

export interface ModelPreset {
  value: string;
  label: string;      // 主標題：模型名
  platform: string;   // 註解：平台名
  compute_target: string;
  endpoint: string;
  deployment: string;
}

export const MODEL_PRESETS: ModelPreset[] = [
  {
    value: "gpt-5.2",
    label: "GPT-5.2",
    platform: "Azure AI Foundry",
    compute_target: "cloud",
    endpoint: "https://<resource>.services.ai.azure.com",
    deployment: "gpt-5.2",
  },
  {
    value: "gemma-3-4b",
    label: "Gemma-3-4b",
    platform: "AMD Ryzen AI",
    compute_target: "soc_edge",
    endpoint: "http://localhost:11434",
    deployment: "gemma-3-4b",
  },
];

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
  { label: "回到規劃重試", value: "retry_plan" },
  { label: "結束工作流", value: "end" },
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
  /** 此模組是否呼叫 LLM（決定是否顯示運算後端選項） */
  usesLLM?: boolean;
  /** 額外提示 */
  hint?: string;
}

export const NODE_CLASSES: Record<NodeName, NodeClass[]> = {
  perceive: [
    {
      value: "rule_based",
      label: "RuleBasedPerceive",
      type: "builtin.perceive",
      usesLLM: false,
      hint: "呈現你設定的歡迎語與服務選項，每個選項對應一條預定義的服務 SOP，使用者選擇後自動進入對應流程。",
    },
  ],
  plan: [
    {
      value: "react",
      label: "ReActPlan",
      type: "builtin.plan",
      usesLLM: true,
      enforceParams: { system_prompt: PLAN_PROMPT_TEMPLATES.react },
      hint: "依使用者問題情境決定走知識查詢還是直接回應，並記錄每次決策依據。（<a href='https://arxiv.org/abs/2210.03629' target='_blank'>參考文獻</a>）",
    },
    {
      value: "cot",
      label: "ChainOfThoughtPlan",
      type: "builtin.plan",
      usesLLM: true,
      enforceParams: { system_prompt: PLAN_PROMPT_TEMPLATES.cot },
      hint: "決策過程逐步記錄，適合需要合規稽核或決策可追溯的服務情境。（<a href='https://arxiv.org/abs/2201.11903' target='_blank'>參考文獻</a>）",
    },
    {
      value: "plan_and_solve",
      label: "PlanAndSolvePlan",
      type: "builtin.plan",
      usesLLM: true,
      enforceParams: { system_prompt: PLAN_PROMPT_TEMPLATES.plan_and_solve },
      hint: "將使用者目標拆解成多個服務步驟後依序推進，適合跨流程的複雜服務。（<a href='https://arxiv.org/abs/2305.04091' target='_blank'>參考文獻</a>）",
    },
  ],
  retrieve: [
    {
      value: "semantic",
      label: "SemanticRetrieve",
      type: "builtin.retrieve",
      usesLLM: false,
      hint: "從你匯入的知識文件（如 FAQ、產品資訊、政策手冊）中找出與使用者問題最相關的內容，作為後續回應的依據。（<a href='https://arxiv.org/abs/2005.11401' target='_blank'>參考文獻</a>）",
    },
  ],
  reflect: [
    {
      value: "rule_based",
      label: "RuleBasedReflect",
      type: "builtin.reflect",
      usesLLM: false,
      enforceParams: { mode: "rule_based" },
      hint: "依你設定的服務標準逐條驗收回應，不符合則退回流程重試，不產生額外費用。",
    },
    {
      value: "reflexion",
      label: "ReflexionReflect",
      type: "builtin.reflect",
      usesLLM: true,
      enforceParams: { mode: "llm" },
      hint: "由系統自我評估回應是否符合服務標準，不足則自動修正後重試，適合標準較彈性的情境。（<a href='https://arxiv.org/abs/2303.11366' target='_blank'>參考文獻</a>）",
    },
  ],
  action: [
    {
      value: "foundry",
      label: "CompletionAction",
      type: "foundry_completion",
      usesLLM: true,
      hint: "彙整前面各服務環節的結果，產出送給使用者的完整回應。",
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
