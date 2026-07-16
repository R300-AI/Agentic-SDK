/** 明確繞路邊 — 從 source 往右、往下繞過所有節點底部、往左、往上到 target。
 *  用於 action → perceive 這條需要從下方繞回頭的回環邊。
 */

import { BaseEdge, type EdgeProps } from "@xyflow/react";

/** 所有節點底部最低點（action y=320，節點高度約 80px）留 80px 緩衝 */
const BYPASS_Y = 480;
/** 離開/進入 handle 的水平偏移，讓折角不貼著節點邊框 */
const H_OFFSET = 40;

export function BypassEdge({ sourceX, sourceY, targetX, targetY, markerEnd, style }: EdgeProps) {
  // 路徑：source → 右偏 → 下到 BYPASS_Y → 左偏到 target → 上到 targetY → target
  const path = [
    `M ${sourceX} ${sourceY}`,
    `L ${sourceX + H_OFFSET} ${sourceY}`,
    `L ${sourceX + H_OFFSET} ${BYPASS_Y}`,
    `L ${targetX - H_OFFSET} ${BYPASS_Y}`,
    `L ${targetX - H_OFFSET} ${targetY}`,
    `L ${targetX} ${targetY}`,
  ].join(" ");

  return <BaseEdge path={path} markerEnd={markerEnd} style={style} />;
}
