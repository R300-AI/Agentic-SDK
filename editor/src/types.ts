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
      hint: "RuleBased 代表以可預定的 SOP 流程進行意圖判斷，不依賴 LLM。\n系統直接比對使用者輸入與選項 value，將對應的 intent 寫入 Working Memory，再路由至 Plan 節點。適合意圖分類有限、需要零延遲回應的場景。",
    },
  ],
  plan: [
    {
      value: "react",
      label: "ReActPlan",
      type: "builtin.plan",
      enforceParams: { system_prompt: PLAN_PROMPT_TEMPLATES.react },
      hint: "ReAct（Yao et al., 2022）推理 ↔ 行動交替典範。\nPlan 節點依據 Perceive 傳入的 intent 與現有 context，先在 thought 欄位推理，再決定 next_node 為 retrieve（需外部知識）或 action（可直接產出）。",
    },
    {
      value: "cot",
      label: "ChainOfThoughtPlan",
      type: "builtin.plan",
      enforceParams: { system_prompt: PLAN_PROMPT_TEMPLATES.cot },
      hint: "Chain-of-Thought（Wei et al., 2022）逐步推理後決策。\nPlan 節點在 thought 欄位以條列式推理：(1) 使用者問什麼、(2) 已有什麼資訊、(3) 缺什麼，再選擇 next_node。適合需要可讀推理鏈、便於 debug 的場景。",
    },
    {
      value: "plan_and_solve",
      label: "PlanAndSolvePlan",
      type: "builtin.plan",
      enforceParams: { system_prompt: PLAN_PROMPT_TEMPLATES.plan_and_solve },
      hint: "Plan-and-Solve（Wang et al., 2023）顯式分離規劃與執行。\nPlan 節點先列出完成任務的子步驟清單，再判斷第一個子步驟屬於 retrieve 還是 action，確保大目標被分解後再執行。",
    },
  ],
  retrieve: [
    {
      value: "semantic",
      label: "SemanticRetrieve",
      type: "builtin.retrieve",
      hint: "從 Working Memory 中以語意相似度取回最相關的上下文片段。\n評分 = similarity_weight × 語意相似度 + recency_weight × 時近性 + importance_weight × 重要性（三權重總和應為 1）。top_k 控制最多取回幾筆。\n對應學理：RAG（Lewis et al., 2020）、DPR（Karpukhin et al., 2020）。",
    },
  ],
  reflect: [
    {
      value: "rule_based",
      label: "RuleBasedReflect",
      type: "builtin.reflect",
      enforceParams: { mode: "rule_based" },
      hint: "以預定規則即時評判 Action 輸出品質，無 LLM 呼叫、成本為零。\n判斷結果為 pass（流程繼續）或 fail（依 on_failure 設定回 Plan 重試或終止）。適合有明確成功 / 失敗定義、需要嚴格控制推論成本的場景。",
    },
    {
      value: "reflexion",
      label: "ReflexionReflect",
      type: "builtin.reflect",
      enforceParams: { mode: "llm" },
      hint: "LLM 自我反思（Reflexion, Shinn et al., 2023）。\n以 LLM 審查 Action 輸出，產出文字形式的改進建議（verbal reinforcement），並寫回 Memory 供下一輪 Plan 參考。適合開放式任務、需要迭代優化輸出品質的場景。",
    },
  ],
  action: [
    {
      value: "foundry",
      label: "CompletionAction",
      type: "foundry_completion",
      hint: "向 compute_target 指定的後端發送 Chat Completion 請求，產出本輪對話的最終回應。\n後端選擇由 compute_target 控制（Azure Foundry / AMD NPU / 本機 CPU），Action 模組本身不與任何特定後端耦合。",
    },
    {
      value: "upstream",
      label: "UpstreamCompletionAction",
      type: "upstream_completion",
      hint: "向上游 AMD NPU 邊緣服務（OpenAI 相容端點）發送 Chat Completion 請求。\ncompute_target 應設為 ryzen_ai，請求走本地邊緣推論，延遲最低、資料不出節點。",
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
