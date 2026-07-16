/**
 * EditableElbowEdge — smoothstep 圓弧折線，整條線可按住自由拖曳。
 *
 * - 視覺：getSmoothStepPath（borderRadius=8，與原預設完全相同）
 * - 拖曳：寬透明筆觸覆蓋整條路徑，按住任意位置拖曳
 *         dx → centerXOffset（左右平移垂直段）
 *         dy → centerYOffset（上下平移水平段）
 * - 無任何可見控制點
 * - 持久化：偏移量存在 edge data.centerXOffset / centerYOffset
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
  const centerYOffset: number = (data as any)?.centerYOffset ?? 0;

  const [edgePath] = getSmoothStepPath({
    sourceX, sourceY, sourcePosition,
    targetX, targetY, targetPosition,
    centerX: (sourceX + targetX) / 2 + centerXOffset,
    centerY: (sourceY + targetY) / 2 + centerYOffset,
    borderRadius: 8,
  });

  const dragging = useRef(false);

  const onMouseDown = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragging.current = true;

    const startClientX = e.clientX;
    const startClientY = e.clientY;
    const startXOffset = centerXOffset;
    const startYOffset = centerYOffset;

    const onMove = (mv: MouseEvent) => {
      if (!dragging.current) return;
      const zoom = getZoom();
      setEdges((eds) =>
        eds.map((ed) =>
          ed.id === id
            ? {
                ...ed,
                data: {
                  ...(ed.data ?? {}),
                  centerXOffset: startXOffset + (mv.clientX - startClientX) / zoom,
                  centerYOffset: startYOffset + (mv.clientY - startClientY) / zoom,
                },
              }
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
  }, [id, centerXOffset, centerYOffset, getZoom, setEdges]);

  return (
    <>
      <BaseEdge id={id} path={edgePath} style={style} markerEnd={markerEnd} />
      {/* 寬透明筆觸，讓整條線任意位置都能按住拖曳 */}
      <path
        d={edgePath}
        fill="none"
        stroke="transparent"
        strokeWidth={20}
        style={{ cursor: "move", pointerEvents: "stroke" }}
        onMouseDown={onMouseDown}
      />
    </>
  );
}



