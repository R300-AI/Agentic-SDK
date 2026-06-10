/** 五節點共用外殼 — 顯示標題、狀態描邊動畫、compute_target badge(M6-4)。 */

import { Handle, Position } from "@xyflow/react";
import type { ReactNode } from "react";
import type { NodeStatus } from "../runtime/types";
import { COMPUTE_TARGET_OPTIONS } from "../types";

interface Props {
  title: string;
  subtitle?: string;
  status: NodeStatus;
  computeTarget?: string;
  children?: ReactNode;
  hasInput?: boolean;
  hasOutput?: boolean;
}

const STATUS_CLASS: Record<NodeStatus, string> = {
  idle: "node-idle",
  running: "node-running",
  ok: "node-ok",
  fail: "node-fail",
};

export function NodeBase({
  title,
  subtitle,
  status,
  computeTarget,
  children,
  hasInput = true,
  hasOutput = true,
}: Props) {
  const tgt = computeTarget ?? "local_cpu";
  const tgtLabel = COMPUTE_TARGET_OPTIONS.find((o) => o.value === tgt)?.label ?? tgt;
  return (
    <div className={`node-shell ${STATUS_CLASS[status]}`}>
      {hasInput && <Handle type="target" position={Position.Left} />}
      <div className="node-head">
        <span className="node-title">{title}</span>
        <span className={`node-badge badge-${tgt}`}>{tgtLabel}</span>
      </div>
      {subtitle && <div className="node-subtitle">{subtitle}</div>}
      {children && <div className="node-body">{children}</div>}
      {hasOutput && <Handle type="source" position={Position.Right} />}
    </div>
  );
}
