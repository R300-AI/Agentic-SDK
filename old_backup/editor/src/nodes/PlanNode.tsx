import { NodeBase } from "./NodeBase";
import type { NodeProps } from "@xyflow/react";
import type { NodeStatus } from "../runtime/types";
import type { NodeSpec } from "../types";
import { detectNodeClass } from "../types";

export function PlanNode({ data }: NodeProps) {
  const d = data as { spec?: NodeSpec; status?: NodeStatus; leftCount?: number; rightCount?: number };
  const status = (d.status ?? "idle") as NodeStatus;
  const klass = d.spec ? detectNodeClass("plan", d.spec).label : "Plan";
  return (
    <NodeBase
      title={klass}
      status={status}
      computeTarget={d.spec?.compute_target}
      leftCount={d.leftCount}
      rightCount={d.rightCount}
    />
  );
}
