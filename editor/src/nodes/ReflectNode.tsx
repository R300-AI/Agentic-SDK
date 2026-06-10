import { NodeBase } from "./NodeBase";
import type { NodeProps } from "@xyflow/react";
import type { NodeStatus } from "../runtime/types";
import type { NodeSpec } from "../types";
import { detectNodeClass } from "../types";

export function ReflectNode({ data }: NodeProps) {
  const d = data as { spec?: NodeSpec; status?: NodeStatus };
  const status = (d.status ?? "idle") as NodeStatus;
  const klass = d.spec ? detectNodeClass("reflect", d.spec).label : "Reflect";
  const onFailure = (d.spec?.params?.on_failure as string | undefined) ?? "retry_plan";
  return (
    <NodeBase
      title={klass}
      subtitle={`fail → ${onFailure}`}
      status={status}
      computeTarget={d.spec?.compute_target}
    />
  );
}
