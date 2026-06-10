import { NodeBase } from "./NodeBase";
import type { NodeProps } from "@xyflow/react";
import type { NodeStatus } from "../runtime/types";

export function PerceiveNode({ data }: NodeProps) {
  const status = ((data as { status?: NodeStatus })?.status ?? "idle") as NodeStatus;
  return (
    <NodeBase
      title="Perceive"
      subtitle="rule_based(無 LLM)"
      status={status}
      hasInput={false}
    />
  );
}
