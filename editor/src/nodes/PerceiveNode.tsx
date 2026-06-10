import { NodeBase } from "./NodeBase";
import type { NodeProps } from "@xyflow/react";
import type { NodeStatus } from "../runtime/types";
import type { NodeSpec, PerceiveOption } from "../types";

export function PerceiveNode({ data }: NodeProps) {
  const d = data as { spec?: NodeSpec; status?: NodeStatus };
  const status = (d.status ?? "idle") as NodeStatus;
  const options = (d.spec?.params?.options as PerceiveOption[] | undefined) ?? [];
  const subtitle = options.length > 0 ? `${options.length} 個引導選項` : "rule_based(無 LLM)";
  return (
    <NodeBase
      title="Perceive"
      subtitle={subtitle}
      status={status}
      computeTarget={d.spec?.compute_target}
      hasInput={false}
    />
  );
}
