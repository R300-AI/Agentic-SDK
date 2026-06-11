import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ReactFlow,
  Background,
  BackgroundVariant,
  Controls,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  ConnectionMode,
  MarkerType,
  type Connection,
  type Edge,
  type Node,
} from "@xyflow/react";

import { NODE_TYPES } from "./nodes";
import { EditableElbowEdge } from "./edges/EditableElbowEdge";

const EDGE_TYPES = { elbow: EditableElbowEdge };
import { AccordionPanel } from "./panels/AccordionPanel";
import { PythonModal } from "./panels/NodePalette";
import { ChatPanel } from "./panels/ChatPanel";
import { DEFAULT_WORKFLOW, DEFAULT_WORKFLOW_YAML } from "./defaultWorkflow";
import { configToPython } from "./export";
import {
  configToFlow,
  configToYaml,
  flowToConfig,
  isLegalEdge,
} from "./adapter";
import type { NodeSpec, WorkflowConfig } from "./types";
import { FIVE_NODE_NAMES } from "./types";
import type { ChatMessage, NodeStatus, TelemetryEvent } from "./runtime/types";
import { runWorkflow, subscribeStream, fetchWorkflowResult } from "./runtime/api";
import { getGatewayUrl, setGatewayUrl } from "./runtime/gatewayUrl";
import { createNodeAnimator } from "./runtime/nodeAnimator";
import {
  EVENT_NODE_DELTA,
  EVENT_NODE_FINISH,
  EVENT_NODE_START,
  EVENT_NODE_THOUGHT,
  EVENT_WORKFLOW_FALLBACK,
} from "./runtime/eventNames";

export function App() {
  return (
    <ReactFlowProvider>
      <EditorRoot />
    </ReactFlowProvider>
  );
}

function EditorRoot() {
  const initial = useMemo(() => configToFlow(DEFAULT_WORKFLOW), []);
  const [config, setConfig] = useState<WorkflowConfig>(DEFAULT_WORKFLOW);
  const [nodes, setNodes, onNodesChange] = useNodesState<Node>(initial.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState<Edge>(initial.edges);
  const [selectedId, setSelectedId] = useState<string | null>(null);

  // ── 動畫 + 對話框狀態 ────────────────────────────────────────────────────
  const [isRunning, setIsRunning] = useState(false);
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [gatewayUrl, setGatewayUrlState] = useState(() => getGatewayUrl());

  const handleGatewayUrlChange = useCallback((url: string) => {
    setGatewayUrl(url);
    setGatewayUrlState(url.replace(/\/+$/, ""));
  }, []);
  const closeStreamRef = useRef<(() => void) | null>(null);
  const startTimeRef = useRef<number>(0);

  // ── M6-10 Python 程式碼 modal ─────────────────────────────────────────────
  const [pythonCode, setPythonCode] = useState<string | null>(null);

  // ── M7-3 面板拖曳縮放 / M8-1 LEFT 為主面板 ─────────────────────────────
  const [leftWidth, setLeftWidth] = useState(360);
  const [chatHeight, setChatHeight] = useState(440);
  const dragDir = useRef<'v' | 'h' | null>(null);

  const startResizeV = useCallback((e: React.MouseEvent) => {
    dragDir.current = 'v';
    e.preventDefault();
  }, []);

  const startResizeH = useCallback((e: React.MouseEvent) => {
    dragDir.current = 'h';
    e.preventDefault();
  }, []);

  useEffect(() => {
    const onMove = (e: MouseEvent) => {
      if (dragDir.current === 'v') {
        setLeftWidth(Math.max(280, Math.min(600, e.clientX)));
      } else if (dragDir.current === 'h') {
        setChatHeight(Math.max(160, Math.min(500, window.innerHeight - e.clientY)));
      }
    };
    const onUp = () => { dragDir.current = null; };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
    return () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
    };
  }, []);
  const handleShowPython = useCallback(() => {
    const merged = flowToConfig(nodes, config);
    setPythonCode(configToPython(merged));
  }, [nodes, config]);

  const updateNodeStatus = useCallback(
    (nodeId: string, status: NodeStatus) => {
      setNodes((curr) =>
        curr.map((n) => (n.id === nodeId ? { ...n, data: { ...n.data, status } } : n))
      );
    },
    [setNodes]
  );

  const resetAllNodeStatus = useCallback(() => {
    setNodes((curr) => curr.map((n) => ({ ...n, data: { ...n.data, status: "idle" } })));
  }, [setNodes]);

  // 動畫佇列:保證每個節點的 running 狀態都有最低可見時長,不被 React/SSE batching 吞掉
  const animator = useMemo(() => createNodeAnimator(updateNodeStatus), [updateNodeStatus]);

  // ── 屬性面板更新 ──────────────────────────────────────────────────────────
  const handleSpecUpdate = useCallback(
    (nodeId: string, newSpec: NodeSpec) => {
      setNodes((curr) =>
        curr.map((n) => (n.id === nodeId ? { ...n, data: { ...n.data, spec: newSpec } } : n))
      );
      setConfig((c) => ({ ...c, nodes: { ...c.nodes, [nodeId]: newSpec } }));
    },
    [setNodes]
  );

  // ── 邊連線白名單 ──────────────────────────────────────────────────────────
  const onConnect = useCallback(
    (conn: Connection) => {
      if (!conn.source || !conn.target) return;
      if (!isLegalEdge(conn.source, conn.target)) {
        alert(`非法連線:${conn.source} → ${conn.target}`);
        return;
      }
      setEdges((curr) => [
        ...curr,
        {
          id: `${conn.source}-${conn.target}`,
          source: conn.source!,
          target: conn.target!,
          sourceHandle: conn.sourceHandle ?? undefined,
          targetHandle: conn.targetHandle ?? undefined,
          markerEnd: { type: MarkerType.ArrowClosed },
        },
      ]);
    },
    [setEdges]
  );

  // ── 跑一次 + SSE 動畫 ─────────────────────────────────────────────────────
  const handleSend = useCallback(
    async (text: string, attachments?: import("./types").Attachment[]) => {
      // 上一次的 stream 若未關,先關
      closeStreamRef.current?.();
      closeStreamRef.current = null;

      resetAllNodeStatus();
      animator.reset();
      // 樂觀亮起 entry 節點黃燈，給「我送出了」即時視覺反饋。
      // 安全性:嚴格序列 animator 會 dedupe 相同 status，因此後端真實送來
      // start(entry) 時不會重複套用；finish(entry) 抵達後才會接著走 green。
      // 即使 Cloud Run cold start 長達 10+ 秒，使用者也持續看到 entry 黃燈
      // 而非死寂的畫面。
      const entryNodeId = config.entry || "perceive";
      animator.enqueue(entryNodeId, "running");
      setIsRunning(true);
      startTimeRef.current = performance.now();

      const displayText = attachments && attachments.length > 0
        ? `${text}${text ? "\n" : ""}[已附上 ${attachments.length} 個附件]`
        : text;

      setMessages((prev) => [
        ...prev,
        { role: "user", content: displayText },
        { role: "assistant", content: "" },
      ]);

      const merged = flowToConfig(nodes, config);
      const yamlText = configToYaml(merged);

      let runResult: { workflow_id: string; stream_url: string };
      try {
        runResult = await runWorkflow(yamlText, text, attachments);
      } catch (err) {
        setIsRunning(false);
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = {
            role: "assistant",
            content: `錯誤:${err instanceof Error ? err.message : String(err)}`,
          };
          return next;
        });
        return;
      }

      const finalize = (assistantContent: string, meta: ChatMessage["metadata"]) => {
        const elapsed = Math.round(performance.now() - startTimeRef.current);
        setMessages((prev) => {
          const next = [...prev];
          next[next.length - 1] = {
            role: "assistant",
            content: assistantContent,
            metadata: { ...meta, elapsed_ms: elapsed },
          };
          return next;
        });
        setIsRunning(false);
      };

      let lastModel: string | undefined;
      let lastInputTokens: number | undefined;
      let lastOutputTokens: number | undefined;
      let lastPlanThought: string | undefined;
      let lastPlanNextNode: string | undefined;
      let streamedContent = "";

      closeStreamRef.current = subscribeStream(
        runResult.workflow_id,
        (ev: TelemetryEvent) => {
          // 誊斷用：在瀏覽器 console 印出所有事件，可以看 SSE 抵達順序與間隔
          // eslint-disable-next-line no-console
          console.debug("[SSE]", ev.event_name, ev.workflow_node, ev);
          // Plan 推理軌跡 — 寫入最後一條 assistant metadata 讓 ChatPanel 顯示
          if (ev.event_name === EVENT_NODE_THOUGHT && ev.workflow_node === "plan") {
            lastPlanThought = typeof ev.plan_thought === "string" ? ev.plan_thought : undefined;
            lastPlanNextNode = typeof ev.plan_next_node === "string" ? ev.plan_next_node : undefined;
            setMessages((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              if (last && last.role === "assistant") {
                next[next.length - 1] = {
                  ...last,
                  metadata: {
                    ...last.metadata,
                    plan_thought: lastPlanThought,
                    plan_next_node: lastPlanNextNode,
                  },
                };
              }
              return next;
            });
            return;
          }

          if (ev.event_name === EVENT_NODE_DELTA) {
            const delta = typeof ev.delta_text === "string" ? ev.delta_text : "";
            if (!delta) return;
            streamedContent += delta;
            setMessages((prev) => {
              const next = [...prev];
              const last = next[next.length - 1];
              if (last && last.role === "assistant") {
                next[next.length - 1] = { ...last, content: streamedContent };
              }
              return next;
            });
            return;
          }

          const node = ev.workflow_node;
          if (!node || !FIVE_NODE_NAMES.includes(node as (typeof FIVE_NODE_NAMES)[number])) return;

          if (ev.event_name === EVENT_NODE_START) {
            animator.enqueue(node, "running");
          } else if (ev.event_name === EVENT_NODE_FINISH) {
            const status: NodeStatus =
              ev.workflow_status === "ok" || ev.workflow_status === undefined ? "ok" : "fail";
            animator.enqueue(node, status);
            if (ev.gen_ai_response_model) lastModel = ev.gen_ai_response_model;
            if (typeof ev.gen_ai_usage_input_tokens === "number")
              lastInputTokens = ev.gen_ai_usage_input_tokens;
            if (typeof ev.gen_ai_usage_output_tokens === "number")
              lastOutputTokens = ev.gen_ai_usage_output_tokens;
          } else if (ev.event_name === EVENT_WORKFLOW_FALLBACK) {
            animator.enqueue(node, "fail");
          }
        },
        () => {
          // SSE 異常關閉
        },
        async () => {
          // SSE 結束 → 拉 /v1/workflow/{id}/result 取最終回應;串流已有內容則優先使用串流
          try {
            const data = await fetchWorkflowResult(runResult.workflow_id);
            const finalMsg = data.aborted
              ? `(中止:${data.abort_reason ?? "unknown"})`
              : streamedContent || String(data.final_message ?? "");
            finalize(finalMsg, {
              model: lastModel ?? data.usage?.model,
              input_tokens: lastInputTokens ?? data.usage?.input_tokens,
              output_tokens: lastOutputTokens ?? data.usage?.output_tokens,
              plan_thought: lastPlanThought,
              plan_next_node: lastPlanNextNode,
            });
          } catch (err) {
            finalize(`(完成,但取結果失敗:${err instanceof Error ? err.message : String(err)})`, {
              model: lastModel,
              input_tokens: lastInputTokens,
              output_tokens: lastOutputTokens,
            });
          }
        }
      );
    },
    [config, nodes, resetAllNodeStatus, animator]
  );

  useEffect(() => {
    return () => {
      closeStreamRef.current?.();
    };
  }, []);

  const nodeSpecs = useMemo(() => {
    const ids = ["perceive", "plan", "retrieve", "reflect", "action"] as const;
    return Object.fromEntries(
      ids.map((id) => {
        const n = nodes.find((nn) => nn.id === id);
        return [id, ((n?.data as { spec?: NodeSpec })?.spec ?? null) as NodeSpec | null];
      })
    ) as Record<string, NodeSpec | null>;
  }, [nodes]);

  return (
    <div className="editor-shell">
      <aside className="left-column" style={{ width: leftWidth }}>
        <AccordionPanel
          selectedNodeId={selectedId}
          specs={nodeSpecs}
          onUpdate={handleSpecUpdate}
          onShowPython={handleShowPython}
        />
      </aside>
      <div className="resize-v" onMouseDown={startResizeV} />
      <div className="right-column">
        <main className="canvas-area">
          <ReactFlow
            nodes={nodes}
            edges={edges}
            nodeTypes={NODE_TYPES}
            edgeTypes={EDGE_TYPES}
            onNodesChange={onNodesChange}
            onEdgesChange={onEdgesChange}
            onConnect={onConnect}
            onNodeClick={(_, n) => setSelectedId(n.id)}
            onPaneClick={() => setSelectedId(null)}
            connectionMode={ConnectionMode.Loose}
            defaultEdgeOptions={{ type: "elbow", markerEnd: { type: MarkerType.ArrowClosed }, style: { strokeWidth: 2 } }}
            snapToGrid
            snapGrid={[20, 20]}
            fitView
          >
            <Background variant={BackgroundVariant.Dots} gap={20} size={1.5} />
            <Controls />
          </ReactFlow>
        </main>
        <div className="resize-h" onMouseDown={startResizeH} />
        <footer className="footer-area" style={{ height: chatHeight }}>
          <ChatPanel
            messages={messages}
            isRunning={isRunning}
            onSend={handleSend}
            perceiveSpec={nodeSpecs["perceive"]}
            gatewayUrl={gatewayUrl}
            onGatewayUrlChange={handleGatewayUrlChange}
          />
        </footer>
      </div>
      {pythonCode !== null && (
        <PythonModal code={pythonCode} onClose={() => setPythonCode(null)} />
      )}
    </div>
  );
}

// 兜底,避免 import 失敗
void DEFAULT_WORKFLOW_YAML;
