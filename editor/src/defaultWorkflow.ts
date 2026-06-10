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
      welcome_message: 您好!請選擇您要協助的項目,或直接輸入問題。
      options:
        - { label: 查訂單, value: order, intent: order_inquiry }
        - { label: 退款, value: refund, intent: refund_request }
        - { label: 一般詢問, value: general, intent: general }
    compute_target: local_cpu
  plan:
    type: builtin.plan
    compute_target: azure_foundry
  retrieve:
    type: builtin.retrieve
    params:
      top_k: 3
      similarity_weight: 0.5
      recency_weight: 0.3
      importance_weight: 0.2
    compute_target: local_cpu
  reflect:
    type: builtin.reflect
    params:
      on_failure: retry_plan
      mode: rule_based
    compute_target: local_cpu
  action:
    type: foundry_completion
    compute_target: azure_foundry
gates:
  max_node_hops: 20
  max_revisit: 3
  timeout_sec: 30
`;

export const DEFAULT_WORKFLOW: WorkflowConfig = {
  version: "1",
  name: "demo",
  entry: "perceive",
  nodes: {
    perceive: {
      type: "builtin.perceive",
      params: {
        welcome_message: "您好!請選擇您要協助的項目,或直接輸入問題。",
        options: [
          { label: "查訂單", value: "order", intent: "order_inquiry" },
          { label: "退款", value: "refund", intent: "refund_request" },
          { label: "一般詢問", value: "general", intent: "general" },
        ],
      },
      compute_target: "local_cpu",
    },
    plan: {
      type: "builtin.plan",
      compute_target: "azure_foundry",
    },
    retrieve: {
      type: "builtin.retrieve",
      params: {
        top_k: 3,
        similarity_weight: 0.5,
        recency_weight: 0.3,
        importance_weight: 0.2,
      },
      compute_target: "local_cpu",
    },
    reflect: {
      type: "builtin.reflect",
      params: { on_failure: "retry_plan", mode: "rule_based" },
      compute_target: "local_cpu",
    },
    action: {
      type: "foundry_completion",
      compute_target: "azure_foundry",
    },
  },
  gates: { max_node_hops: 20, max_revisit: 3, timeout_sec: 30 },
};
