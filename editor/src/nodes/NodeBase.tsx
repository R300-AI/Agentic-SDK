/** 五節點共用外殼 — 顯示標題、狀態描邊動畫、compute_target badge(M6-4)。
 *  左右各依 leftCount / rightCount 動態渲染多個等距連接點，搭配 connectionMode="loose"。
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
  leftCount?: number;
  rightCount?: number;
}

const STATUS_CLASS: Record<NodeStatus, string> = {
  idle: "node-idle",
  running: "node-running",
  ok: "node-ok",
  fail: "node-fail",
};

/** 在指定側渲染 n 個等距 Handle，n 最小為 1 */
function sideHandles(side: "left" | "right", count: number, position: Position) {
  const n = Math.max(1, count);
  return Array.from({ length: n }, (_, i) => (
    <Handle
      key={`${side}-${i}`}
      id={`${side}-${i}`}
      type="source"
      position={position}
      className="node-handle"
      style={{ top: `${((i + 1) / (n + 1)) * 100}%` }}
    />
  ));
}

export function NodeBase({
  title,
  subtitle,
  status,
  computeTarget,
  children,
  leftCount = 0,
  rightCount = 0,
}: Props) {
  const tgt = computeTarget ?? "local_cpu";
  const tgtLabel = COMPUTE_TARGET_OPTIONS.find((o) => o.value === tgt)?.label ?? tgt;
  const showBadge = tgt !== "local_cpu";
  return (
    <div className={`node-shell ${STATUS_CLASS[status]}`}>
      {sideHandles("left",  leftCount,  Position.Left)}
      {sideHandles("right", rightCount, Position.Right)}
      <div className="node-head">
        <span className="node-title">{title}</span>
        {showBadge && <span className={`node-badge badge-${tgt}`}>{tgtLabel}</span>}
      </div>
      {subtitle && <div className="node-subtitle">{subtitle}</div>}
      {children && <div className="node-body">{children}</div>}
    </div>
  );
}
