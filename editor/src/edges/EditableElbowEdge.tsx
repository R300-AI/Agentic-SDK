/**
 * EditableElbowEdge — smoothstep 圓弧折線，整條線可按住拖曳調整垂直段位置。
 *
 * - 視覺：getSmoothStepPath（borderRadius=8，與原預設完全相同）
 * - 拖曳：在線路徑上疊一條寬透明筆觸（strokeWidth=20），按住線的任意位置左右拖
 *         即可平移 centerX，驅動 getSmoothStepPath 重算路徑
 * - 無任何可見控制點
 * - 持久化：偏移量存在 edge data.centerXOffset
 */

import { useCallback, useRef } from "react";
import {
  BaseEdge,
  getSmoothStepPath,
  useReactFlow,
  type EdgeProps,
} from "@xyflow/react";

export function EditableElbowEdge({
  id,
  sourceX, sourceY, sourcePosition,
  targetX, targetY, targetPosition,
  style = {},
  markerEnd,
  data,
}: EdgeProps) {
  const { setEdges, getZoom } = useReactFlow();

  const centerXOffset: number = (data as any)?.centerXOffset ?? 0;

  const [edgePath] = getSmoothStepPath({
    sourceX, sourceY, sourcePosition,
    targetX, targetY, targetPosition,
    centerX: (sourceX + targetX) / 2 + centerXOffset,
    borderRadius: 8,
  });

  const dragging = useRef(false);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragging.current = true;

    const startClientX = e.clientX;
    const startOffset = centerXOffset;

    const onMove = (mv: MouseEvent) => {
      if (!dragging.current) return;
      const dx = mv.clientX - startClientX;
      setEdges((eds) =>
        eds.map((ed) =>
          ed.id === id
            ? { ...ed, data: { ...(ed.data ?? {}), centerXOffset: startOffset + dx / getZoom() } }
            : ed
        )
      );
    };

    const onUp = () => {
      dragging.current = false;
      window.removeEventListener("mousemove", onMove);
      window.removeEventListener("mouseup", onUp);
    };

    window.addEventListener("mousemove", onMove);
    window.addEventListener("mouseup", onUp);
  }, [id, centerXOffset, getZoom, setEdges]);

  return (
    <>
      <BaseEdge id={id} path={edgePath} style={style} markerEnd={markerEnd} />
      {/* 寬透明筆觸覆蓋整條線，讓任意位置都可拖曳 */}
      <path
        d={edgePath}
        fill="none"
        stroke="transparent"
        strokeWidth={20}
        style={{ cursor: "ew-resize", pointerEvents: "stroke" }}
        onMouseDown={onMouseDown}
      />
    </>
  );
}


