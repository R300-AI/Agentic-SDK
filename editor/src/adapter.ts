/** WorkflowConfig ⇄ React Flow nodes/edges 雙向轉換。
 *
 * 邊白名單與 Python `agentic_sdk/workflow/engine.py` 的拓樸保持一致:
 *   perceive → plan
 *   plan → retrieve | action
 *   retrieve → plan
 *   action → reflect
 *   reflect → plan | END
 *
 * 邊在畫布上是視覺輔助,實際 next_node 由節點執行時決定;但拖曳新邊時應擋下非法連線。
 */

import { dump, load } from "js-yaml";
import { MarkerType, type Edge, type Node } from "@xyflow/react";
import {
  ACTION_BACKEND_OPTIONS,
  FIVE_NODE_NAMES,
  NODE_DISPLAY_ORDER,
  type NodeSpec,
  type WorkflowConfig,
} from "./types";

const NODE_POSITIONS: Record<string, { x: number; y: number }> = {
  perceive: { x: 50, y: 200 },
  plan: { x: 280, y: 200 },
  retrieve: { x: 510, y: 80 },
  action: { x: 510, y: 320 },
  reflect: { x: 740, y: 320 },
};

const EDGE_WHITELIST: Array<[string, string]> = [
  ["perceive", "plan"],
  ["plan", "retrieve"],
  ["plan", "action"],
  ["retrieve", "plan"],
  ["action", "reflect"],
  ["reflect", "plan"],
];

export function isLegalEdge(source: string, target: string): boolean {
  return EDGE_WHITELIST.some(([s, t]) => s === source && t === target);
}

/** WorkflowConfig → React Flow */
export function configToFlow(config: WorkflowConfig): { nodes: Node[]; edges: Edge[] } {
  const nodes: Node[] = NODE_DISPLAY_ORDER.map((name) => {
    const spec = config.nodes[name] ?? { type: defaultTypeFor(name) };
    return {
      id: name,
      type: name,
      position: NODE_POSITIONS[name],
      data: { name, spec },
    };
  });
const ARROW = { type: MarkerType.ArrowClosed } as const;

/** 每條初始邊的 source/target handle，依節點佈局指定最短路徑側 */
const EDGE_HANDLES: Record<string, { sourceHandle: string; targetHandle: string }> = {
  "perceive-plan":  { sourceHandle: "right", targetHandle: "left"  },
  "plan-retrieve":  { sourceHandle: "right", targetHandle: "left"  },
  "plan-action":    { sourceHandle: "right", targetHandle: "left"  },
  "retrieve-plan":  { sourceHandle: "left",  targetHandle: "right" },
  "action-reflect": { sourceHandle: "right", targetHandle: "left"  },
  "reflect-plan":   { sourceHandle: "left",  targetHandle: "right" },
};

  const edges: Edge[] = EDGE_WHITELIST.map(([s, t]) => {
    const key = `${s}-${t}`;
    const handles = EDGE_HANDLES[key] ?? { sourceHandle: "right", targetHandle: "left" };
    return {
      id: key,
      source: s,
      target: t,
      animated: false,
      markerEnd: ARROW,
      style: { strokeWidth: 2 },
      ...handles,
    };
  });
  return { nodes, edges };
}

/** React Flow → WorkflowConfig
 *
 * 只信任 nodes 內的 spec 資料;邊是視覺,實際拓樸由 SDK 端引擎控制。
 */
export function flowToConfig(
  nodes: Node[],
  baseConfig: WorkflowConfig
): WorkflowConfig {
  const out: WorkflowConfig = {
    version: "1",
    name: baseConfig.name,
    entry: baseConfig.entry,
    nodes: {},
    gates: { ...baseConfig.gates },
  };
  for (const n of nodes) {
    if (!FIVE_NODE_NAMES.includes(n.id as (typeof FIVE_NODE_NAMES)[number])) continue;
    const spec = (n.data?.spec as NodeSpec) ?? { type: defaultTypeFor(n.id) };
    out.nodes[n.id] = stripEmptyParams(spec);
  }
  return out;
}

/** YAML 序列化:把 WorkflowConfig 轉成 SDK 端能讀的 YAML 字串。 */
export function configToYaml(config: WorkflowConfig): string {
  return dump(config, { sortKeys: false, lineWidth: 120 });
}

/** YAML 反序列化:接受 YAML 文字,失敗時 throw 帶 line/column 的錯。 */
export function yamlToConfig(yaml: string): WorkflowConfig {
  const parsed = load(yaml) as unknown;
  if (!parsed || typeof parsed !== "object") {
    throw new Error("YAML 內容不是 object");
  }
  const obj = parsed as Record<string, unknown>;
  if (obj.version !== "1") {
    throw new Error(`不支援的 version=${String(obj.version)},僅接受 "1"`);
  }
  const entry = typeof obj.entry === "string" ? obj.entry : "perceive";
  const name = typeof obj.name === "string" ? obj.name : undefined;
  const nodesRaw = (obj.nodes ?? {}) as Record<string, NodeSpec>;
  const gatesRaw = (obj.gates ?? {}) as Partial<WorkflowConfig["gates"]>;
  return {
    version: "1",
    name,
    entry,
    nodes: nodesRaw,
    gates: {
      max_node_hops: Number(gatesRaw.max_node_hops ?? 20),
      max_revisit: Number(gatesRaw.max_revisit ?? 3),
      timeout_sec: Number(gatesRaw.timeout_sec ?? 30),
    },
  };
}

function defaultTypeFor(name: string): string {
  if (name === "action") return ACTION_BACKEND_OPTIONS[1].typeString; // foundry
  return `builtin.${name}`;
}

function stripEmptyParams(spec: NodeSpec): NodeSpec {
  const out: NodeSpec = { type: spec.type };
  if (spec.params && Object.keys(spec.params).length > 0) out.params = spec.params;
  if (spec.compute_target) out.compute_target = spec.compute_target;
  return out;
}
