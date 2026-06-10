/**
 * EditableElbowEdge — smoothstep 圓弧折線（視覺與原本完全相同），
 * 垂直段中間放不可見拖曳熱區，拖曳可左右平移垂直段。
 *
 * - 視覺：getSmoothStepPath（borderRadius=8，與預設 smoothstep 一致）
 * - 拖曳：透明 rect 覆蓋垂直段中點，cursor 變 ew-resize；無可見圓點
 * - 持久化：偏移量存在 edge data.centerXOffset，重繪後保留
 */

import { useCallback, useRef } from "react";
import {
  BaseEdge,
  getSmoothStepPath,
  useReactFlow,
  type EdgeProps,
} from "@xyflow/react";

const HIT_HALF = 16; // 不可見點擊區半寬/半高（px，flow 座標）

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
  const centerX = (sourceX + targetX) / 2 + centerXOffset;

  const [edgePath] = getSmoothStepPath({
    sourceX, sourceY, sourcePosition,
    targetX, targetY, targetPosition,
    centerX,
    borderRadius: 8,
  });

  // 拖曳熱區位置：垂直段中點
  const handleX = centerX;
  const handleY = (sourceY + targetY) / 2;

  const dragging = useRef(false);

  const onMouseDownHandle = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragging.current = true;

    const startClientX = e.clientX;
    const startOffset = centerXOffset;

    const onMove = (mv: MouseEvent) => {
      if (!dragging.current) return;
      const dx = mv.clientX - startClientX;
      const zoom = getZoom();
      setEdges((eds) =>
        eds.map((ed) =>
          ed.id === id
            ? { ...ed, data: { ...(ed.data ?? {}), centerXOffset: startOffset + dx / zoom } }
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
      {/* 不可見拖曳熱區，只改變 cursor，不繪製任何視覺元素 */}
      <rect
        x={handleX - HIT_HALF}
        y={handleY - HIT_HALF}
        width={HIT_HALF * 2}
        height={HIT_HALF * 2}
        fill="transparent"
        stroke="none"
        style={{ cursor: "ew-resize", pointerEvents: "all" }}
        onMouseDown={onMouseDownHandle}
      />
    </>
  );
}

