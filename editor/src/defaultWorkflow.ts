import type { WorkflowConfig } from "./types";

/** 預設五節點工作流:Action 走 Azure Foundry,Plan 用 ReAct 模板,Reflect 失敗回 Plan。 */
export const DEFAULT_WORKFLOW_YAML = `version: "1"
entry: perceive
nodes:
  perceive:
    type: builtin.perceive
  plan:
    type: builtin.plan
  retrieve:
    type: builtin.retrieve
  reflect:
    type: builtin.reflect
    params:
      on_failure: retry_plan
  action:
    type: foundry_completion
gates:
  max_node_hops: 20
  max_revisit: 3
  timeout_sec: 30
`;

export const DEFAULT_WORKFLOW: WorkflowConfig = {
  version: "1",
  entry: "perceive",
  nodes: {
    perceive: { type: "builtin.perceive" },
    plan: { type: "builtin.plan" },
    retrieve: { type: "builtin.retrieve" },
    reflect: { type: "builtin.reflect", params: { on_failure: "retry_plan" } },
    action: { type: "foundry_completion" },
  },
  gates: { max_node_hops: 20, max_revisit: 3, timeout_sec: 30 },
};
