/** 左側三頁籤手風琴面板：屬性 / 記憶管理 / 部署流程。
 *
 * 每個頁籤有標題列（點擊折疊/展開），內容區以 max-height 動畫收合。
 * 三個頁籤可同時展開，也可全部收合。
 * 預設：屬性展開，其餘收合。
 */

import { useState } from "react";
import type React from "react";
import type { NodeName, NodeSpec, PerceiveOption } from "../types";
import {
  COMPUTE_TARGET_OPTIONS,
  FIVE_NODE_NAMES,
  NODE_CLASSES,
  REFLECT_ON_FAILURE_OPTIONS,
  applyNodeClass,
  detectNodeClass,
} from "../types";

// ── Accordion shell ─────────────────────────────────────────────────────────

interface SectionProps {
  title: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}

function Section({ title, open, onToggle, children }: SectionProps) {
  return (
    <div className={`accordion-section${open ? " accordion-open" : ""}`}>
      <button className="accordion-header" onClick={onToggle}>
        <span>{title}</span>
        <span className="accordion-chevron">{open ? "▲" : "▼"}</span>
      </button>
      <div className="accordion-body">
        {children}
      </div>
    </div>
  );
}

// ── 主元件 ─────────────────────────────────────────────────────────────────

interface Props {
  selectedNodeId: string | null;
  spec: NodeSpec | null;
  onUpdate: (spec: NodeSpec) => void;
  onDownload: () => void;
  onLoad: (yaml: string) => void;
  onShowPython: () => void;
  style?: React.CSSProperties;
}

export function AccordionPanel({
  selectedNodeId, spec, onUpdate,
  onDownload, onLoad, onShowPython,
  style,
}: Props) {
  const [open, setOpen] = useState<Record<string, boolean>>({
    props: true,
    memory: false,
    deploy: false,
  });

  const toggle = (key: string) =>
    setOpen((prev) => ({ ...prev, [key]: !prev[key] }));

  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => onLoad(String(reader.result ?? ""));
    reader.readAsText(file, "utf-8");
    e.target.value = "";
  };

  return (
    <aside className="accordion-panel" style={style}>

      {/* ── 屬性 ── */}
      <Section title="屬性" open={open.props} onToggle={() => toggle("props")}>
        <PropsContent
          selectedNodeId={selectedNodeId}
          spec={spec}
          onUpdate={onUpdate}
        />
      </Section>

      {/* ── 記憶管理 ── */}
      <Section title="記憶管理" open={open.memory} onToggle={() => toggle("memory")}>
        <div className="memory-indicator">
          <div className="memory-indicator-icon">⛁</div>
          <div className="memory-indicator-body">
            <div>跨 run 持久化</div>
            <small>workflow_name 隔離</small>
          </div>
        </div>
        <p className="hint">Working Memory 在五大節點間共享，Archived Memory 於 run 結束後寫入磁碟，下次執行可由 Retrieve 節點取回。</p>
      </Section>

      {/* ── 部署流程 ── */}
      <Section title="部署流程" open={open.deploy} onToggle={() => toggle("deploy")}>
        <div className="left-tools-buttons">
          <button onClick={onDownload}>下載 YAML</button>
          <button onClick={onShowPython}>顯示 Python</button>
          <label className="file-button">
            載入 YAML
            <input type="file" accept=".yaml,.yml" onChange={handleFile} />
          </label>
        </div>
      </Section>

    </aside>
  );
}

// ── 屬性頁籤內容（原 PropertyPanel 邏輯移入） ──────────────────────────────

function PropsContent({
  selectedNodeId,
  spec,
  onUpdate,
}: {
  selectedNodeId: string | null;
  spec: NodeSpec | null;
  onUpdate: (spec: NodeSpec) => void;
}) {
  if (!selectedNodeId || !spec) {
    return <p className="hint">點選畫布節點以編輯屬性。</p>;
  }

  const nodeName = selectedNodeId as NodeName;
  const isFiveNode = (FIVE_NODE_NAMES as readonly string[]).includes(selectedNodeId);
  if (!isFiveNode) {
    return <pre>{JSON.stringify(spec, null, 2)}</pre>;
  }

  return (
    <>
      <h3 className="props-node-title">{selectedNodeId}</h3>
      <ClassEditor nodeName={nodeName} spec={spec} onUpdate={onUpdate} />
      <ComputeTargetEditor spec={spec} onUpdate={onUpdate} />
      <hr className="prop-divider" />
      <NodeEditor nodeId={selectedNodeId} spec={spec} onUpdate={onUpdate} />
    </>
  );
}

// ── Class 下拉（含模組說明） ────────────────────────────────────────────────

const NODE_ROLE_LABEL: Record<string, string> = {
  perceive: "Perceive",
  plan: "Plan",
  retrieve: "Retrieve",
  reflect: "Reflect",
  action: "Action",
};

function ClassEditor({ nodeName, spec, onUpdate }: {
  nodeName: NodeName; spec: NodeSpec; onUpdate: (s: NodeSpec) => void;
}) {
  const klasses = NODE_CLASSES[nodeName];
  const current = detectNodeClass(nodeName, spec);
  return (
    <div className="prop-row">
      <label>{NODE_ROLE_LABEL[nodeName] ?? nodeName} 模組</label>
      <select
        value={current.value}
        onChange={(e) => {
          const next = klasses.find((k) => k.value === e.target.value);
          if (next) onUpdate(applyNodeClass(spec, next));
        }}
      >
        {klasses.map((k) => (
          <option key={k.value} value={k.value}>{k.label}</option>
        ))}
      </select>
      {current.hint && (
        <small className="hint module-desc">
          {current.hint.split("\n").map((line, i) => (
            <span key={i}>{line}<br /></span>
          ))}
        </small>
      )}
    </div>
  );
}

// ── Compute Target ───────────────────────────────────────────────────────────

function ComputeTargetEditor({ spec, onUpdate }: { spec: NodeSpec; onUpdate: (s: NodeSpec) => void }) {
  const current = spec.compute_target ?? "local_cpu";
  return (
    <div className="prop-row">
      <label>compute_target(M6-4)</label>
      <select value={current} onChange={(e) => onUpdate({ ...spec, compute_target: e.target.value })}>
        {COMPUTE_TARGET_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
      <small className="hint">節點實際 offload 至哪個計算資源。Phase 1 為靜態綁定。</small>
    </div>
  );
}

// ── 參數編輯區（依節點分派） ────────────────────────────────────────────────

function setParam(spec: NodeSpec, key: string, value: unknown): NodeSpec {
  return { ...spec, params: { ...spec.params, [key]: value } };
}

function NodeEditor({ nodeId, spec, onUpdate }: {
  nodeId: string; spec: NodeSpec; onUpdate: (s: NodeSpec) => void;
}) {
  switch (nodeId) {
    case "perceive": return <PerceiveEditor spec={spec} onUpdate={onUpdate} />;
    case "retrieve": return <RetrieveEditor spec={spec} onUpdate={onUpdate} />;
    case "plan":     return <PlanEditor spec={spec} onUpdate={onUpdate} />;
    case "reflect":  return <ReflectEditor spec={spec} onUpdate={onUpdate} />;
    case "action":   return <ActionEditor spec={spec} onUpdate={onUpdate} />;
    default:         return <pre>{JSON.stringify(spec, null, 2)}</pre>;
  }
}

function PerceiveEditor({ spec, onUpdate }: { spec: NodeSpec; onUpdate: (s: NodeSpec) => void }) {
  const welcome   = (spec.params?.welcome_message as string | undefined) ?? "";
  const options   = (spec.params?.options as PerceiveOption[] | undefined) ?? [];
  const importance = (spec.params?.importance as number | undefined) ?? 1.0;

  const updateOptions = (next: PerceiveOption[]) => onUpdate(setParam(spec, "options", next));
  const addOption = () => updateOptions([...options, { label: "新選項", value: "new", intent: "general" }]);
  const removeOption = (i: number) => updateOptions(options.filter((_, idx) => idx !== i));
  const updateOption = (i: number, patch: Partial<PerceiveOption>) =>
    updateOptions(options.map((o, idx) => (idx === i ? { ...o, ...patch } : o)));

  return (
    <>
      <div className="prop-row">
        <label>welcome_message</label>
        <textarea rows={3} value={welcome}
          onChange={(e) => onUpdate(setParam(spec, "welcome_message", e.target.value))}
          placeholder="進入工作流時 Chat Panel 顯示的開場白" />
      </div>
      <div className="prop-row">
        <label>options(引導選項)</label>
        {options.map((opt, i) => (
          <div key={i} className="perceive-option">
            <input type="text" value={opt.label} placeholder="顯示文字"
              onChange={(e) => updateOption(i, { label: e.target.value })} />
            <input type="text" value={opt.value} placeholder="送出值"
              onChange={(e) => updateOption(i, { value: e.target.value })} />
            <input type="text" value={opt.intent} placeholder="intent"
              onChange={(e) => updateOption(i, { intent: e.target.value })} />
            <button className="icon-btn" onClick={() => removeOption(i)} title="移除">×</button>
          </div>
        ))}
        <button className="add-btn" onClick={addOption}>+ 新增選項</button>
        <small className="hint">UI Chat Panel 會把這份清單渲染為按鈕。</small>
      </div>
      <div className="prop-row">
        <label>importance(寫入 Memory 的權重)</label>
        <input type="number" step="0.1" value={importance}
          onChange={(e) => onUpdate(setParam(spec, "importance", Number(e.target.value)))} />
      </div>
    </>
  );
}

function RetrieveEditor({ spec, onUpdate }: { spec: NodeSpec; onUpdate: (s: NodeSpec) => void }) {
  const topK = (spec.params?.top_k as number | undefined) ?? 3;
  const sim  = (spec.params?.similarity_weight as number | undefined) ?? 0.5;
  const rec  = (spec.params?.recency_weight as number | undefined) ?? 0.3;
  const imp  = (spec.params?.importance_weight as number | undefined) ?? 0.2;
  return (
    <>
      <div className="prop-row">
        <label>top_k</label>
        <input type="number" min="1" value={topK}
          onChange={(e) => onUpdate(setParam(spec, "top_k", Number(e.target.value)))} />
      </div>
      <div className="prop-row">
        <label>similarity_weight</label>
        <input type="number" step="0.1" value={sim}
          onChange={(e) => onUpdate(setParam(spec, "similarity_weight", Number(e.target.value)))} />
      </div>
      <div className="prop-row">
        <label>recency_weight</label>
        <input type="number" step="0.1" value={rec}
          onChange={(e) => onUpdate(setParam(spec, "recency_weight", Number(e.target.value)))} />
      </div>
      <div className="prop-row">
        <label>importance_weight</label>
        <input type="number" step="0.1" value={imp}
          onChange={(e) => onUpdate(setParam(spec, "importance_weight", Number(e.target.value)))} />
        <small className="hint">三項加權對齊 Generative Agents §4.1。</small>
      </div>
    </>
  );
}

function PlanEditor({ spec, onUpdate }: { spec: NodeSpec; onUpdate: (s: NodeSpec) => void }) {
  const current = (spec.params?.system_prompt as string | undefined) ?? "";
  return (
    <div className="prop-row">
      <label>system_prompt</label>
      <textarea rows={8} value={current}
        onChange={(e) => onUpdate(setParam(spec, "system_prompt", e.target.value))} />
      <small className="hint">切換 Class 會覆寫為該 Class 的標準模板；編輯文本可自訂。</small>
    </div>
  );
}

function ReflectEditor({ spec, onUpdate }: { spec: NodeSpec; onUpdate: (s: NodeSpec) => void }) {
  const onFailure = (spec.params?.on_failure as string | undefined) ?? "retry_plan";
  return (
    <div className="prop-row">
      <label>on_failure</label>
      <select value={onFailure}
        onChange={(e) => onUpdate(setParam(spec, "on_failure", e.target.value))}>
        {REFLECT_ON_FAILURE_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>{o.label}</option>
        ))}
      </select>
    </div>
  );
}

function ActionEditor({ spec, onUpdate }: { spec: NodeSpec; onUpdate: (s: NodeSpec) => void }) {
  const endpoint    = (spec.params?.endpoint as string | undefined) ?? "";
  const deployment  = (spec.params?.deployment as string | undefined) ?? "";
  const model       = (spec.params?.model as string | undefined) ?? "";
  const temperature = (spec.params?.temperature as number | undefined) ?? 0.2;
  return (
    <>
      <div className="prop-row">
        <label>endpoint</label>
        <input type="text" value={endpoint}
          placeholder="https://<resource>.openai.azure.com 或 NPU 服務 URL"
          onChange={(e) => onUpdate(setParam(spec, "endpoint", e.target.value))} />
      </div>
      <div className="prop-row">
        <label>deployment</label>
        <input type="text" value={deployment} placeholder="部署名稱(Foundry)或留空"
          onChange={(e) => onUpdate(setParam(spec, "deployment", e.target.value))} />
      </div>
      <div className="prop-row">
        <label>model</label>
        <input type="text" value={model} placeholder="gpt-4o 或留空沿用 deployment"
          onChange={(e) => onUpdate(setParam(spec, "model", e.target.value))} />
      </div>
      <div className="prop-row">
        <label>temperature</label>
        <input type="number" step="0.1" min="0" max="2" value={temperature}
          onChange={(e) => onUpdate(setParam(spec, "temperature", Number(e.target.value)))} />
      </div>
    </>
  );
}
