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
  const model = (d.spec?.params?.model as string | undefined) ?? "";
  const subtitle = model ? `${backend?.label ?? typeStr} · ${model}` : (backend?.label ?? typeStr);
  return (
    <NodeBase
      title="Action"
      subtitle={subtitle}
      status={status}
      computeTarget={d.spec?.compute_target}
    />
  );
}
