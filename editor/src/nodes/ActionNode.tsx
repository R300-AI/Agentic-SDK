import { NodeBase } from "./NodeBase";
import type { NodeProps } from "@xyflow/react";
import type { NodeStatus } from "../runtime/types";
import type { NodeSpec } from "../types";
import { detectNodeClass } from "../types";

export function ActionNode({ data }: NodeProps) {
  const d = data as { spec?: NodeSpec; status?: NodeStatus; leftCount?: number; rightCount?: number };
  const status = (d.status ?? "idle") as NodeStatus;
  const klass = d.spec ? detectNodeClass("action", d.spec).label : "Action";
  const model = (d.spec?.params?.model as string | undefined) ?? "";
  return (
    <NodeBase
      title={klass}
      subtitle={model || undefined}
      status={status}
      computeTarget={d.spec?.compute_target}
      leftCount={d.leftCount}
      rightCount={d.rightCount}
    />
  );
}
