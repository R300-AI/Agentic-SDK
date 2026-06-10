import { NodeBase } from "./NodeBase";
import type { NodeProps } from "@xyflow/react";
import type { NodeStatus } from "../runtime/types";
import type { NodeSpec } from "../types";
import { detectNodeClass } from "../types";

export function RetrieveNode({ data }: NodeProps) {
  const d = data as { spec?: NodeSpec; status?: NodeStatus; leftCount?: number; rightCount?: number };
  const status = (d.status ?? "idle") as NodeStatus;
  const klass = d.spec ? detectNodeClass("retrieve", d.spec).label : "Retrieve";
  const topK = (d.spec?.params?.top_k as number | undefined) ?? 3;
  return (
    <NodeBase
      title={klass}
      subtitle={`取前 ${topK} 筆參考`}
      status={status}
      computeTarget={d.spec?.compute_target}
      leftCount={d.leftCount}
      rightCount={d.rightCount}
    />
  );
}
