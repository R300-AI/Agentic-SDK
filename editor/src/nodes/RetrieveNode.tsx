import { NodeBase } from "./NodeBase";
import type { NodeProps } from "@xyflow/react";
import type { NodeStatus } from "../runtime/types";
import type { NodeSpec } from "../types";

export function RetrieveNode({ data }: NodeProps) {
  const d = data as { spec?: NodeSpec; status?: NodeStatus };
  const status = (d.status ?? "idle") as NodeStatus;
  const topK = (d.spec?.params?.top_k as number | undefined) ?? 3;
  return (
    <NodeBase
      title="Retrieve"
      subtitle={`semantic, top_k=${topK}`}
      status={status}
      computeTarget={d.spec?.compute_target}
    />
  );
}
