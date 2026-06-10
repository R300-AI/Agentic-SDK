import { NodeBase } from "./NodeBase";
import type { NodeProps } from "@xyflow/react";
import type { NodeStatus } from "../runtime/types";
import type { NodeSpec } from "../types";
import { ACTION_BACKEND_OPTIONS } from "../types";

export function ActionNode({ data }: NodeProps) {
  const d = data as { spec?: NodeSpec; status?: NodeStatus };
  const status = (d.status ?? "idle") as NodeStatus;
  const typeStr = d.spec?.type ?? "foundry_completion";
  const backend = ACTION_BACKEND_OPTIONS.find((opt) => opt.typeString === typeStr);
  return (
    <NodeBase title="Action" subtitle={backend?.label ?? typeStr} status={status} />
  );
}
