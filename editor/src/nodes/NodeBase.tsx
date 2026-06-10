/** 五節點共用外殼 — 顯示標題、狀態描邊動畫、compute_target badge(M6-4)。
 *  上下左右四側各一個連接點，搭配 connectionMode="loose" 可雙向連線。
 */

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
}: Props) {
  const tgt = computeTarget ?? "local_cpu";
  const tgtLabel = COMPUTE_TARGET_OPTIONS.find((o) => o.value === tgt)?.label ?? tgt;
  return (
    <div className={`node-shell ${STATUS_CLASS[status]}`}>
      <Handle className="node-handle" type="source" position={Position.Left}  id="left"  />
      <Handle className="node-handle" type="source" position={Position.Right} id="right" />
      <div className="node-head">
        <span className="node-title">{title}</span>
        <span className={`node-badge badge-${tgt}`}>{tgtLabel}</span>
      </div>
      {subtitle && <div className="node-subtitle">{subtitle}</div>}
      {children && <div className="node-body">{children}</div>}
    </div>
  );
}
