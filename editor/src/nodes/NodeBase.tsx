/** 五節點共用外殼 — 顯示標題、狀態描邊動畫,內容由子節點自填。 */

import { Handle, Position } from "@xyflow/react";
import type { ReactNode } from "react";
import type { NodeStatus } from "../runtime/types";

interface Props {
  title: string;
  subtitle?: string;
  status: NodeStatus;
  children?: ReactNode;
  /** 為 false 時不渲染 source / target handle(例如 perceive 沒入口、reflect 出口會多條)。 */
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
  children,
  hasInput = true,
  hasOutput = true,
}: Props) {
  return (
    <div className={`node-shell ${STATUS_CLASS[status]}`}>
      {hasInput && <Handle type="target" position={Position.Left} />}
      <div className="node-title">{title}</div>
      {subtitle && <div className="node-subtitle">{subtitle}</div>}
      {children && <div className="node-body">{children}</div>}
      {hasOutput && <Handle type="source" position={Position.Right} />}
    </div>
  );
}
