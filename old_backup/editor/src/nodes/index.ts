import { PerceiveNode } from "./PerceiveNode";
import { PlanNode } from "./PlanNode";
import { RetrieveNode } from "./RetrieveNode";
import { ReflectNode } from "./ReflectNode";
import { ActionNode } from "./ActionNode";

export const NODE_TYPES = {
  perceive: PerceiveNode,
  plan: PlanNode,
  retrieve: RetrieveNode,
  reflect: ReflectNode,
  action: ActionNode,
};
