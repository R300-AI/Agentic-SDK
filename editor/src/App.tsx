import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  ReactFlowProvider,
  useEdgesState,
  useNodesState,
  type Connection,
  type Edge,
  type Node,
} from "@xyflow/react";

import { NODE_TYPES } from "./nodes";
import { NodePalette } from "./panels/NodePalette";
import { PropertyPanel } from "./panels/PropertyPanel";
import { ChatPanel } from "./panels/ChatPanel";
import { DEFAULT_WORKFLOW, DEFAULT_WORKFLOW_YAML } from "./defaultWorkflow";
import {
  configToFlow,
  configToYaml,
  flowToConfig,
  isLegalEdge,
  yamlToConfig,
} from "./adapter";
import type { NodeSpec, WorkflowConfig } from "./types";
import { FIVE_NODE_NAMES } from "./types";
import type { ChatMessage, NodeStatus, TelemetryEvent } from "./runtime/types";
import { runWorkflow, subscribeStream, fetchWorkflowResult } from "./runtime/api";
import {
  EVENT_NODE_FINISH,
  EVENT_NODE_START,
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
  const closeStreamRef = useRef<(() => void) | null>(null);
  const startTimeRef = useRef<number>(0);

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

  // ── 屬性面板更新 ──────────────────────────────────────────────────────────
  const handleSpecUpdate = useCallback(
    (newSpec: NodeSpec) => {
      if (!selectedId) return;
      setNodes((curr) =>
        curr.map((n) => (n.id === selectedId ? { ...n, data: { ...n.data, spec: newSpec } } : n))
      );
      setConfig((c) => ({ ...c, nodes: { ...c.nodes, [selectedId]: newSpec } }));
    },
    [selectedId, setNodes]
  );

  // ── YAML 下載 / 載入 ──────────────────────────────────────────────────────
  const handleDownload = useCallback(() => {
    const merged = flowToConfig(nodes, config);
    const yamlText = configToYaml(merged);
    const blob = new Blob([yamlText], { type: "text/yaml;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `workflow-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "")}.yaml`;
    a.click();
    URL.revokeObjectURL(url);
  }, [nodes, config]);

  const handleLoad = useCallback(
    (yamlText: string) => {
      try {
        const next = yamlToConfig(yamlText);
        setConfig(next);
        const f = configToFlow(next);
        setNodes(f.nodes);
        setEdges(f.edges);
        setSelectedId(null);
      } catch (err) {
        alert(`YAML 載入失敗:${err instanceof Error ? err.message : String(err)}`);
      }
    },
    [setNodes, setEdges]
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
        { id: `${conn.source}-${conn.target}`, source: conn.source!, target: conn.target! },
      ]);
    },
    [setEdges]
  );

  // ── 跑一次 + SSE 動畫 ─────────────────────────────────────────────────────
  const handleSend = useCallback(
    async (text: string) => {
      // 上一次的 stream 若未關,先關
      closeStreamRef.current?.();
      closeStreamRef.current = null;

      resetAllNodeStatus();
      setIsRunning(true);
      startTimeRef.current = performance.now();

      setMessages((prev) => [
        ...prev,
        { role: "user", content: text },
        { role: "assistant", content: "" },
      ]);

      const merged = flowToConfig(nodes, config);
      const yamlText = configToYaml(merged);

      let runResult: { workflow_id: string; stream_url: string };
      try {
        runResult = await runWorkflow(yamlText, text);
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

      closeStreamRef.current = subscribeStream(
        runResult.workflow_id,
        (ev: TelemetryEvent) => {
          const node = ev.workflow_node;
          if (!node || !FIVE_NODE_NAMES.includes(node as (typeof FIVE_NODE_NAMES)[number])) return;

          if (ev.event_name === EVENT_NODE_START) {
            updateNodeStatus(node, "running");
          } else if (ev.event_name === EVENT_NODE_FINISH) {
            const status: NodeStatus =
              ev.workflow_status === "ok" || ev.workflow_status === undefined ? "ok" : "fail";
            updateNodeStatus(node, status);
            if (ev.gen_ai_response_model) lastModel = ev.gen_ai_response_model;
            if (typeof ev.gen_ai_usage_input_tokens === "number")
              lastInputTokens = ev.gen_ai_usage_input_tokens;
            if (typeof ev.gen_ai_usage_output_tokens === "number")
              lastOutputTokens = ev.gen_ai_usage_output_tokens;
          } else if (ev.event_name === EVENT_WORKFLOW_FALLBACK) {
            updateNodeStatus(node, "fail");
          }
        },
        () => {
          // SSE 異常關閉
        },
        async () => {
          // SSE 結束 → 拉 /v1/workflow/{id}/result 取最終回應
          try {
            const data = await fetchWorkflowResult(runResult.workflow_id);
            const finalMsg = data.aborted
              ? `(中止:${data.abort_reason ?? "unknown"})`
              : String(data.final_message ?? "");
            finalize(finalMsg, {
              model: lastModel ?? data.usage?.model,
              input_tokens: lastInputTokens ?? data.usage?.input_tokens,
              output_tokens: lastOutputTokens ?? data.usage?.output_tokens,
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
    [config, nodes, resetAllNodeStatus, updateNodeStatus]
  );

  useEffect(() => {
    return () => {
      closeStreamRef.current?.();
    };
  }, []);

  const selectedSpec: NodeSpec | null = useMemo(() => {
    if (!selectedId) return null;
    const n = nodes.find((nn) => nn.id === selectedId);
    return ((n?.data as { spec?: NodeSpec })?.spec ?? null) as NodeSpec | null;
  }, [selectedId, nodes]);

  return (
    <div className="editor-shell">
      <NodePalette
        onDownload={handleDownload}
        onLoad={handleLoad}
        selectedId={selectedId}
        onSelect={setSelectedId}
      />
      <main className="canvas-area">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={NODE_TYPES}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeClick={(_, n) => setSelectedId(n.id)}
          onPaneClick={() => setSelectedId(null)}
          fitView
        >
          <Background />
          <Controls />
        </ReactFlow>
      </main>
      <PropertyPanel
        selectedNodeId={selectedId}
        spec={selectedSpec}
        onUpdate={handleSpecUpdate}
      />
      <footer className="footer-area">
        <ChatPanel messages={messages} isRunning={isRunning} onSend={handleSend} />
      </footer>
    </div>
  );
}

// 兜底,避免 import 失敗
void DEFAULT_WORKFLOW_YAML;
