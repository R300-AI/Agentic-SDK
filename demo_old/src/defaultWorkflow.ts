import type { WorkflowConfig } from "./types";

/** 預設五節點工作流:Action 走 Azure Foundry,Plan 用 ReAct 模板,Reflect 失敗回 Plan。
 * Perceive 預設帶 welcome_message + 三個引導選項,展示 Chat Panel 由節點屬性驅動。
 * 各節點預設 compute_target,展示異質計算資源綁定可視化。
 */
export const DEFAULT_WORKFLOW_YAML = `version: "1"
name: demo
entry: perceive
nodes:
  perceive:
    type: builtin.perceive
    params:
      welcome_message: 您好！我是線上客服小幫手，可以協助您挑選合適的鞋款 👟
      options:
        - { label: "👟 推薦合適鞋款", intent: product_recommendation }
        - { label: "📏 我有足測報告想諮詢", intent: foot_analysis, expects_attachment: image }
        - { label: "📷 拍鞋現況比對", intent: size_inquiry, expects_attachment: image }
        - { label: "💬 試穿 / 尺寸問題", intent: size_inquiry }
    compute_target: local_cpu
  plan:
    type: builtin.plan
    compute_target: azure_foundry
  retrieve:
    type: builtin.retrieve
    params:
      retrieve_template_ref: shoe_store_catalog_search
      retrieve_strategy_ref: lexical_file_kb
      knowledge_base_ref: shoe_store
      top_k: 3
      similarity_weight: 0.5
      recency_weight: 0.3
      importance_weight: 0.2
      enable_vision_query: true
    compute_target: local_cpu
  reflect:
    type: builtin.reflect
    params:
      on_failure: retry_plan
      mode: rule_based
    compute_target: local_cpu
  action:
    type: completion
    params:
      backend: foundry
    compute_target: azure_foundry
gates:
  max_node_hops: 20
  max_revisit: 3
  timeout_sec: 300
`;

export const DEFAULT_WORKFLOW: WorkflowConfig = {
  version: "1",
  name: "demo",
  entry: "perceive",
  nodes: {
    perceive: {
      type: "builtin.perceive",
      params: {
        welcome_message: "您好！我是線上客服小幫手，可以協助您挑選合適的鞋款 👟",
        options: [
          { label: "👟 推薦合適鞋款", intent: "product_recommendation" },
          { label: "📏 我有足測報告想諮詢", intent: "foot_analysis", expects_attachment: "image" },
          { label: "📷 拍鞋現況比對", intent: "size_inquiry", expects_attachment: "image" },
          { label: "💬 試穿 / 尺寸問題", intent: "size_inquiry" },
        ],
      },
      compute_target: "local_cpu",
    },
    plan: {
      type: "builtin.plan",
      params: {},
      compute_target: "azure_foundry",
    },
    retrieve: {
      type: "builtin.retrieve",
      params: {
        retrieve_template_ref: "shoe_store_catalog_search",
        retrieve_strategy_ref: "lexical_file_kb",
        knowledge_base_ref: "shoe_store",
        top_k: 3,
        similarity_weight: 0.5,
        recency_weight: 0.3,
        importance_weight: 0.2,
        enable_vision_query: true,
      },
      compute_target: "local_cpu",
    },
    reflect: {
      type: "builtin.reflect",
      params: { on_failure: "retry_plan", mode: "rule_based" },
      compute_target: "local_cpu",
    },
    action: {
      type: "completion",
      params: { backend: "foundry" },
      compute_target: "azure_foundry",
    },
  },
  gates: { max_node_hops: 20, max_revisit: 3, timeout_sec: 300 },
};
