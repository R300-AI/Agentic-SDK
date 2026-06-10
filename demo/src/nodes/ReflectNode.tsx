import { NodeBase } from "./NodeBase";
import type { NodeProps } from "@xyflow/react";
import type { NodeStatus } from "../runtime/types";
import type { NodeSpec } from "../types";
import { REFLECT_ON_FAILURE_OPTIONS, detectNodeClass } from "../types";

export function ReflectNode({ data }: NodeProps) {
  const d = data as { spec?: NodeSpec; status?: NodeStatus; leftCount?: number; rightCount?: number };
  const status = (d.status ?? "idle") as NodeStatus;
  const klass = d.spec ? detectNodeClass("reflect", d.spec).label : "Reflect";
  const onFailure = (d.spec?.params?.on_failure as string | undefined) ?? "retry_plan";
  const failLabel = REFLECT_ON_FAILURE_OPTIONS.find((o) => o.value === onFailure)?.label ?? onFailure;
  return (
    <NodeBase
      title={klass}
      subtitle={`規畫失敗時進行重試`}
      status={status}
      computeTarget={d.spec?.compute_target}
      leftCount={d.leftCount}
      rightCount={d.rightCount}
    />
  );
}
