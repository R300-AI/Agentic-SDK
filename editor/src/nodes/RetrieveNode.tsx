import { NodeBase } from "./NodeBase";
import type { NodeProps } from "@xyflow/react";
import type { NodeStatus } from "../runtime/types";

export function RetrieveNode({ data }: NodeProps) {
  const status = ((data as { status?: NodeStatus })?.status ?? "idle") as NodeStatus;
  return <NodeBase title="Retrieve" subtitle="stub" status={status} />;
}
