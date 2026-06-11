import { NodeBase } from "./NodeBase";
import type { NodeProps } from "@xyflow/react";
import type { NodeStatus } from "../runtime/types";
import type { NodeSpec, PerceiveOption } from "../types";
import { detectNodeClass } from "../types";

export function PerceiveNode({ data }: NodeProps) {
  const d = data as { spec?: NodeSpec; status?: NodeStatus; leftCount?: number; rightCount?: number };
  const status = (d.status ?? "idle") as NodeStatus;
  const klass = d.spec ? detectNodeClass("perceive", d.spec).label : "Perceive";
  const options = (d.spec?.params?.options as PerceiveOption[] | undefined) ?? [];
  const subtitle = options.length > 0 ? `${options.length} 個引導選項` : "無選項";
  return (
    <NodeBase
      title={klass}
      subtitle={subtitle}
      status={status}
      computeTarget={d.spec?.compute_target}
      leftCount={d.leftCount}
      rightCount={d.rightCount}
    />
  );
}
