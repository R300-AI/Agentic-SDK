/**
 * EditableElbowEdge — 直角肘形折線（PPT 肘形連接線效果）。
 *
 * 路徑：source → 水平出 → 垂直段 → 水平入 → target
 * 垂直段中點有一個圓形拖曳鈕，拖曳可左右平移整條垂直段。
 *
 * midX 持久化在 edge data.midX（透過 setEdges 更新），重新載入後保留位置。
 * 拖曳 delta 除以 zoom，確保縮放時位移量正確。
 */

import { useCallback, useRef } from "react";
import { BaseEdge, useReactFlow, type EdgeProps } from "@xyflow/react";

const HANDLE_R = 5;
const HANDLE_HIT = 14;

function elbowPath(
  sx: number, sy: number,
  tx: number, ty: number,
  mx: number,
) {
  return `M ${sx} ${sy} L ${mx} ${sy} L ${mx} ${ty} L ${tx} ${ty}`;
}

export function EditableElbowEdge({
  id,
  sourceX, sourceY,
  targetX, targetY,
  style = {},
  markerEnd,
  data,
}: EdgeProps) {
  const { setEdges, getZoom } = useReactFlow();

  // midX 儲存在 edge data 中，預設取中點
  const midX: number = (data as any)?.midX ?? (sourceX + targetX) / 2;
  const path = elbowPath(sourceX, sourceY, targetX, targetY, midX);

  // 垂直段中點 Y（拖曳鈕位置）
  const seg1MidY = (sourceY + targetY) / 2;

  const dragging = useRef(false);

  const onMouseDownHandle = useCallback((e: React.MouseEvent) => {
    e.preventDefault();
    e.stopPropagation();
    dragging.current = true;

    const startX = e.clientX;
    const startMidX = midX;

    const onMove = (mv: MouseEvent) => {
      if (!dragging.current) return;
      const dx = mv.clientX - startX;
      const zoom = getZoom();
      const newMidX = startMidX + dx / zoom;

      setEdges((eds) =>
        eds.map((ed) =>
          ed.id === id
            ? { ...ed, data: { ...(ed.data ?? {}), midX: newMidX } }
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
  }, [id, midX, getZoom, setEdges]);

  return (
    <>
      <BaseEdge
        id={id}
        path={path}
        style={{ ...style, strokeWidth: (style as any).strokeWidth ?? 2 }}
        markerEnd={markerEnd}
      />

      {/* 垂直段拖曳鈕（在 edge 的 SVG 層直接渲染） */}
      <g className="elbow-handle" style={{ cursor: "ew-resize" }}>
        {/* 透明大矩形擴大點擊區 */}
        <rect
          x={midX - HANDLE_HIT}
          y={seg1MidY - HANDLE_HIT}
          width={HANDLE_HIT * 2}
          height={HANDLE_HIT * 2}
          fill="transparent"
          stroke="none"
          style={{ pointerEvents: "all", cursor: "ew-resize" }}
          onMouseDown={onMouseDownHandle}
        />
        {/* 視覺圓點 */}
        <circle
          cx={midX}
          cy={seg1MidY}
          r={HANDLE_R}
          fill="#ffffff"
          stroke="#555555"
          strokeWidth={1.5}
          style={{ pointerEvents: "none" }}
        />
      </g>
    </>
  );
}
