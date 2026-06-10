import { NodeBase } from "./NodeBase";
import type { NodeProps } from "@xyflow/react";
import type { NodeStatus } from "../runtime/types";
import type { NodeSpec } from "../types";

export function PlanNode({ data }: NodeProps) {
  const d = data as { spec?: NodeSpec; status?: NodeStatus };
  const status = (d.status ?? "idle") as NodeStatus;
  const prompt = (d.spec?.params?.system_prompt as string | undefined) ?? "(react 模板)";
  const preview = prompt.slice(0, 22) + (prompt.length > 22 ? "…" : "");
  return (
    <NodeBase
      title="Plan"
      subtitle={preview}
      status={status}
      computeTarget={d.spec?.compute_target}
    />
  );
}
