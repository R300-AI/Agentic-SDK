import { NodeBase } from "./NodeBase";
import type { NodeProps } from "@xyflow/react";
import type { NodeStatus } from "../runtime/types";
import type { NodeSpec } from "../types";
import { detectNodeClass } from "../types";

export function PlanNode({ data }: NodeProps) {
  const d = data as { spec?: NodeSpec; status?: NodeStatus };
  const status = (d.status ?? "idle") as NodeStatus;
  const klass = d.spec ? detectNodeClass("plan", d.spec).label : "Plan";
  return (
    <NodeBase
      title={klass}
      status={status}
      computeTarget={d.spec?.compute_target}
    />
  );
}
