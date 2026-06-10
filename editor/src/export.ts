/** M7-4 — Python Builder 模式輸出。
 *
 * 生成逐節點明確建構的 Python 片段，讓讀者直接看懂 SDK 組裝方式，
 * 不依賴 YAML 字串中介載入。
 *
 * 每個節點型別對應明確的 class + import 路徑，參數直接展開為 kwargs。
 */

import type { WorkflowConfig } from "./types";

// ── 值序列化 ─────────────────────────────────────────────────────────────────

function toPyStr(s: string): string {
  return `"${s.replace(/\\/g, "\\\\").replace(/"/g, '\\"').replace(/\n/g, "\\n")}"`;
}

function toPyValue(v: unknown, depth = 0): string {
  if (v === null || v === undefined) return "None";
  if (typeof v === "boolean") return v ? "True" : "False";
  if (typeof v === "number") return String(v);
  if (typeof v === "string") return toPyStr(v);
  if (Array.isArray(v)) {
    if (v.length === 0) return "[]";
    const items = v.map((item) => toPyValue(item, depth + 1));
    const inner = items.join(", ");
    if (depth < 1 && inner.length <= 80) return `[${inner}]`;
    const ind = "    ".repeat(depth + 2);
    const closing = "    ".repeat(depth + 1);
    return `[\n${v.map((item) => `${ind}${toPyValue(item, depth + 1)}`).join(",\n")},\n${closing}]`;
  }
  if (typeof v === "object") {
    const entries = Object.entries(v as Record<string, unknown>);
    const kvs = entries.map(([k, val]) => `${toPyStr(k)}: ${toPyValue(val, depth + 1)}`);
    return `{${kvs.join(", ")}}`;
  }
  return String(v);
}

function buildKwargs(params: Record<string, unknown>, baseIndent = 8): string {
  const ind = " ".repeat(baseIndent);
  const lines = Object.entries(params)
    .filter(([, v]) => v !== undefined && v !== null && v !== "")
    .map(([k, v]) => `${ind}${k}=${toPyValue(v)},`);
  return lines.join("\n");
}

// ── 節點 → Python 建構式 ──────────────────────────────────────────────────────

interface NodePy {
  /** import 行，可能多行，確保唯一 */
  imports: string[];
  /** constructor call，含換行格式（不含賦值左側） */
  call: string;
}

function perceiveNodePy(params: Record<string, unknown>): NodePy {
  const kw = buildKwargs(params);
  const call = kw
    ? `RuleBasedPerceive(\n${kw}\n    )`
    : "RuleBasedPerceive()";
  return {
    imports: ["from agentic_sdk.workflow.nodes.perceive.rule_based import RuleBasedPerceive"],
    call,
  };
}

function retrieveNodePy(params: Record<string, unknown>): NodePy {
  const kw = buildKwargs(params);
  const call = kw ? `SemanticRetrieve(\n${kw}\n    )` : "SemanticRetrieve()";
  return {
    imports: ["from agentic_sdk.workflow.nodes.retrieve.semantic import SemanticRetrieve"],
    call,
  };
}

function planNodePy(params: Record<string, unknown>): NodePy {
  const kw = buildKwargs(params);
  const call = kw ? `ReActPlan(\n${kw}\n    )` : "ReActPlan()";
  return {
    imports: ["from agentic_sdk.workflow.nodes.plan.react import ReActPlan"],
    call,
  };
}

function reflectNodePy(params: Record<string, unknown>): NodePy {
  const { mode, ...rest } = params as Record<string, unknown>;
  if (mode === "llm") {
    const kw = buildKwargs(rest);
    return {
      imports: ["from agentic_sdk.workflow.nodes.reflect.llm_reflexion import ReflexionReflect"],
      call: kw ? `ReflexionReflect(\n${kw}\n    )` : "ReflexionReflect()",
    };
  }
  const kw = buildKwargs(rest);
  return {
    imports: ["from agentic_sdk.workflow.nodes.reflect.rule_based import RuleBasedReflect"],
    call: kw ? `RuleBasedReflect(\n${kw}\n    )` : "RuleBasedReflect()",
  };
}

function actionNodePy(type: string, params: Record<string, unknown>): NodePy {
  const kw = buildKwargs(params);
  if (type === "foundry_completion") {
    return {
      imports: ["from agentic_sdk.workflow.nodes.action.foundry_completion import FoundryCompletionAction"],
      call: kw ? `FoundryCompletionAction(\n${kw}\n    )` : "FoundryCompletionAction()",
    };
  }
  return {
    imports: ["from agentic_sdk.workflow.nodes.action.upstream_completion import UpstreamCompletionAction"],
    call: kw ? `UpstreamCompletionAction(\n${kw}\n    )` : "UpstreamCompletionAction()",
  };
}

function nodeSpecToPy(nodeId: string, spec: { type: string; params?: Record<string, unknown> }): NodePy {
  const params = spec.params ?? {};
  switch (nodeId) {
    case "perceive": return perceiveNodePy(params);
    case "retrieve": return retrieveNodePy(params);
    case "plan":     return planNodePy(params);
    case "reflect":  return reflectNodePy(params);
    default:         return actionNodePy(spec.type, params);
  }
}

// ── 主函式 ───────────────────────────────────────────────────────────────────

export function configToPython(config: WorkflowConfig): string {
  const NODE_ORDER = ["perceive", "retrieve", "plan", "reflect", "action"];

  const nodeSpecs: Record<string, NodePy> = {};
  const allImports = new Set<string>([
    "from agentic_sdk.memory import MemoryStore",
    "from agentic_sdk.workflow.engine import Workflow",
    "from agentic_sdk.workflow.gates import Gates",
  ]);

  for (const nodeId of NODE_ORDER) {
    const spec = config.nodes[nodeId];
    if (!spec) continue;
    const py = nodeSpecToPy(nodeId, spec);
    nodeSpecs[nodeId] = py;
    py.imports.forEach((imp) => allImports.add(imp));
  }

  const wfName = config.name ?? "demo";

  const gateKw = [
    `        max_node_hops=${config.gates.max_node_hops},`,
    `        max_revisit=${config.gates.max_revisit},`,
    `        timeout_sec=${config.gates.timeout_sec},`,
  ].join("\n");

  const nodeArgs = NODE_ORDER
    .filter((id) => nodeSpecs[id])
    .map((id) => `    ${id}=${nodeSpecs[id].call},`)
    .join("\n");

  const importSection = [...allImports].sort().join("\n");

  return `"""由 Agentic SDK Editor 自動生成。"""

import asyncio

${importSection}


wf = Workflow(
${nodeArgs}
    gates=Gates(
${gateKw}
    ),
    workflow_name=${toPyStr(wfName)},
    memory_store=MemoryStore(db_path=".memory/${wfName}.sqlite"),
)


async def main(user_message: str) -> str:
    result = await asyncio.to_thread(wf.run, user_message)
    return result.final_message or ""


if __name__ == "__main__":
    answer = asyncio.run(main("你好，我想了解這個 workflow"))
    print(answer)
`;
}
