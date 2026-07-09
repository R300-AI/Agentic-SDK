/** 左側七頁籤手風琴面板：Perceive / Plan / Retrieve / Reflect / Action / 記憶管理 / 部署流程。
 *
 * 點選畫布節點時，對應頁籤自動展開；手動點標題列可切換。
 * 同一時間只有一個頁籤展開（互斥）。
 */

import { useState, useEffect } from "react";
import type React from "react";
import type { NodeName, NodeSpec, PerceiveOption } from "../types";
import type { CapabilityDocument, CapabilityRef } from "../runtime/api";
import { previewKnowledgeBase, type KnowledgeBasePreviewHit } from "../runtime/api";
import {
  MODEL_PRESETS,
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
  variant?: "memory" | "deploy";
}

function Section({ title, open, onToggle, children, variant }: SectionProps) {
  const accentClass = variant ? ` accent-${variant}` : "";
  return (
    <div className={`accordion-section${open ? " accordion-open" : ""}`}>
      <button className={`accordion-header${accentClass}`} onClick={onToggle}>
        <span className="accordion-chevron">{open ? "▼" : "▶"}</span>
        <span>{title}</span>
      </button>
      <div className="accordion-body">
        {children}
      </div>
    </div>
  );
}

// ── 節點分欄常數 ──────────────────────────────────────────────────────────

const NODE_SECTION_KEYS = ["perceive", "plan", "retrieve", "reflect", "action"] as const;
type NodeSectionKey = typeof NODE_SECTION_KEYS[number];

const NODE_SECTION_LABELS: Record<NodeSectionKey, string> = {
  perceive: "Perceive",
  plan: "Plan",
  retrieve: "Retrieve",
  reflect: "Reflect",
  action: "Action",
};

// ── 主元件 ─────────────────────────────────────────────────────────────────

interface Props {
  selectedNodeId: string | null;
  specs: Record<string, NodeSpec | null>;
  capabilities: CapabilityDocument | null;
  capabilityError?: string | null;
  onUpdate: (nodeId: string, spec: NodeSpec) => void;
  onShowPython: () => void;
  style?: React.CSSProperties;
}

export function AccordionPanel({
  selectedNodeId, specs, onUpdate,
  capabilities,
  capabilityError,
  onShowPython,
  style,
}: Props) {
  const [open, setOpen] = useState<string>("");

  // 選到畫布節點時，自動展開對應分欄
  useEffect(() => {
    if (selectedNodeId && (NODE_SECTION_KEYS as readonly string[]).includes(selectedNodeId)) {
      setOpen(selectedNodeId);
    }
  }, [selectedNodeId]);

  const toggle = (key: string) =>
    setOpen((prev) => (prev === key ? "" : key));

  return (
    <aside className="accordion-panel" style={style}>

      {/* ── 五大節點分欄 ── */}
      {NODE_SECTION_KEYS.map((nodeId) => (
        <Section
          key={nodeId}
          title={NODE_SECTION_LABELS[nodeId]}
          open={open === nodeId}
          onToggle={() => toggle(nodeId)}
        >
          <NodePropsContent
            nodeId={nodeId}
            spec={specs[nodeId] ?? null}
            capabilities={capabilities}
            capabilityError={capabilityError}
            onUpdate={(s) => onUpdate(nodeId, s)}
          />
        </Section>
      ))}

      {/* ── MEMORY ── */}
      <Section title="MEMORY" open={open === "memory"} onToggle={() => toggle("memory")}>
        <div className="memory-indicator">
          <div className="memory-indicator-icon">⛁</div>
          <div className="memory-indicator-body">
            <div>工作流執行期間共享</div>
            <small>依工作流名稱隔離</small>
          </div>
        </div>
        <p className="hint">工作機流中各節點的對話狀態在執行期間共享，結束後自動存檔，下次執行由知識查詢節點取回。</p>
      </Section>

      {/* ── GO TO DEPLOY ── */}
      <button className="accordion-header accent-deploy" onClick={onShowPython}>
        <span>GO TO DEPLOY</span>
      </button>

    </aside>
  );
}

// ── 單一節點屬性內容 ────────────────────────────────────────────────────────

function NodePropsContent({
  nodeId,
  spec,
  capabilities,
  capabilityError,
  onUpdate,
}: {
  nodeId: string;
  spec: NodeSpec | null;
  capabilities: CapabilityDocument | null;
  capabilityError?: string | null;
  onUpdate: (spec: NodeSpec) => void;
}) {
  if (!spec) {
    return <p className="hint">節點尚未初始化。</p>;
  }
  const nodeName = nodeId as NodeName;
  return (
    <>
      <ClassEditor nodeName={nodeName} spec={spec} onUpdate={onUpdate} />
      <hr className="prop-divider" />
      <NodeEditor
        nodeId={nodeId}
        spec={spec}
        capabilities={capabilities}
        capabilityError={capabilityError}
        onUpdate={onUpdate}
      />
    </>
  );
}

// ── Class 下拉（含模組說明） ────────────────────────────────────────────────

function ClassEditor({ nodeName, spec, onUpdate }: {
  nodeName: NodeName; spec: NodeSpec; onUpdate: (s: NodeSpec) => void;
}) {
  const klasses = NODE_CLASSES[nodeName];
  const current = detectNodeClass(nodeName, spec);
  return (
    <div className="prop-row">
      <label>模組</label>
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
        <small className="hint module-desc"
          dangerouslySetInnerHTML={{ __html: current.hint }} />
      )}
    </div>
  );
}


// ── 參數編輯區（依節點分派） ────────────────────────────────────────────────

function setParam(spec: NodeSpec, key: string, value: unknown): NodeSpec {
  return { ...spec, params: { ...spec.params, [key]: value } };
}

function setParams(spec: NodeSpec, patch: Record<string, unknown>): NodeSpec {
  const params = { ...spec.params };
  Object.entries(patch).forEach(([key, value]) => {
    if (value === undefined) delete params[key];
    else params[key] = value;
  });
  return { ...spec, params };
}

function NodeEditor({
  nodeId,
  spec,
  capabilities,
  capabilityError,
  onUpdate,
}: {
  nodeId: string;
  spec: NodeSpec;
  capabilities: CapabilityDocument | null;
  capabilityError?: string | null;
  onUpdate: (s: NodeSpec) => void;
}) {
  switch (nodeId) {
    case "perceive": return <PerceiveEditor spec={spec} onUpdate={onUpdate} />;
    case "retrieve": return <RetrieveEditor spec={spec} capabilities={capabilities} capabilityError={capabilityError} onUpdate={onUpdate} />;
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
  const addOption = () => updateOptions([...options, { label: "新選項" }]);
  const removeOption = (i: number) => updateOptions(options.filter((_, idx) => idx !== i));
  const updateOption = (i: number, patch: Partial<PerceiveOption>) =>
    updateOptions(options.map((o, idx) => (idx === i ? { ...o, ...patch } : o)));

  return (
    <>
      <div className="prop-row">
        <label>開場訊息</label>
        <textarea rows={3} value={welcome}
          onChange={(e) => onUpdate(setParam(spec, "welcome_message", e.target.value))}
          placeholder="使用者進入對話時的第一句話" />
      </div>
      <div className="prop-row">
      <label>引導選項</label>
        {options.map((opt, i) => (
          <div key={i} className="perceive-option">
              <input type="text" value={opt.label} placeholder="選項文字"
                onChange={(e) => updateOption(i, { label: e.target.value })} />
              <input type="text" value={opt.intent ?? ""} placeholder="intent（如 product_recommendation）"
                onChange={(e) => updateOption(i, { intent: e.target.value || undefined })} />
              <button className="icon-btn" onClick={() => removeOption(i)} title="移除">×</button>
            </div>
        ))}
        <button className="add-btn" onClick={addOption}>+ 新增選項</button>
        <small className="hint">使用者進入對話時顯示的延伸選項按鈕。</small>
      </div>
      <div className="prop-row">
        <label>記憶權重</label>
        <input type="number" step="0.1" value={importance}
          onChange={(e) => onUpdate(setParam(spec, "importance", Number(e.target.value)))} />
      </div>
    </>
  );
}

function RetrieveEditor({
  spec,
  capabilities,
  capabilityError,
  onUpdate,
}: {
  spec: NodeSpec;
  capabilities: CapabilityDocument | null;
  capabilityError?: string | null;
  onUpdate: (s: NodeSpec) => void;
}) {
  const topK = (spec.params?.top_k as number | undefined) ?? 3;
  const sim  = (spec.params?.similarity_weight as number | undefined) ?? 0.5;
  const rec  = (spec.params?.recency_weight as number | undefined) ?? 0.3;
  const imp  = (spec.params?.importance_weight as number | undefined) ?? 0.2;
  const kb   = (spec.params?.knowledge_base as string | undefined) ?? "";
  const kbRef = (spec.params?.knowledge_base_ref as string | undefined) ?? "";
  const templateRef = (spec.params?.retrieve_template_ref as string | undefined) ?? "";
  const strategyRef = (spec.params?.retrieve_strategy_ref as string | undefined) ?? "";
  const vis  = Boolean(spec.params?.enable_vision_query);
  const [previewQuery, setPreviewQuery] = useState("久站 扁平足");
  const [previewHits, setPreviewHits] = useState<KnowledgeBasePreviewHit[]>([]);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [isPreviewing, setIsPreviewing] = useState(false);

  const templates = capabilities?.retrieve_template_refs ?? [];
  const strategies = capabilities?.retrieve_strategy_refs ?? [];
  const knowledgeBases = capabilities?.knowledge_base_refs ?? [];

  const applyTemplate = (ref: string) => {
    const template = templates.find((item) => item.ref === ref);
    const defaults = (template?.defaults as Record<string, unknown> | undefined) ?? {};
    onUpdate(setParams(spec, {
      ...defaults,
      retrieve_template_ref: ref || undefined,
      retrieve_strategy_ref: (template?.strategy_ref as string | undefined) ?? strategyRef,
      knowledge_base: undefined,
    }));
  };

  const runPreview = async () => {
    if (!kbRef || !previewQuery.trim()) return;
    setIsPreviewing(true);
    setPreviewError(null);
    try {
      const data = await previewKnowledgeBase(kbRef, previewQuery.trim(), topK);
      setPreviewHits(data.hits);
    } catch (err) {
      setPreviewHits([]);
      setPreviewError(err instanceof Error ? err.message : String(err));
    } finally {
      setIsPreviewing(false);
    }
  };

  return (
    <>
      {capabilityError && (
        <div className="prop-row">
          <small className="hint">Capability discovery 暫時無法連線，以下保留本機 fallback 欄位。</small>
        </div>
      )}
      <div className="prop-row">
        <label>檢索模板</label>
        <select value={templateRef} onChange={(e) => applyTemplate(e.target.value)}>
          <option value="">自訂設定</option>
          {templates.map((item) => (
            <option key={item.ref} value={item.ref}>{item.label ?? item.ref}</option>
          ))}
        </select>
        <small className="hint">模板由 Gateway capability discovery 提供，會帶入策略與預設知識庫。</small>
      </div>
      <div className="prop-row">
        <label>檢索策略</label>
        <select value={strategyRef} onChange={(e) => onUpdate(setParam(spec, "retrieve_strategy_ref", e.target.value || undefined))}>
          <option value="">自動</option>
          {strategies.map((item) => (
            <option key={item.ref} value={item.ref} disabled={item.enabled === false}>
              {item.label ?? item.ref}{item.enabled === false ? "（尚未啟用）" : ""}
            </option>
          ))}
        </select>
      </div>
      <div className="prop-row">
        <label>知識庫</label>
        <select value={kbRef} onChange={(e) => onUpdate(setParams(spec, { knowledge_base_ref: e.target.value || undefined, knowledge_base: undefined }))}>
          <option value="">使用檔案路徑</option>
          {knowledgeBases.map((item: CapabilityRef) => (
            <option key={item.ref} value={item.ref}>{(item.name as string | undefined) ?? item.label ?? item.ref}</option>
          ))}
        </select>
        <small className="hint">選 registry ref 時，SDK 會由 KnowledgeBaseRegistry 載入對應資料源。</small>
      </div>
      {kbRef && (
        <div className="prop-row">
          <label>知識庫預覽</label>
          <div className="inline-action-row">
            <input type="text" value={previewQuery} onChange={(e) => setPreviewQuery(e.target.value)} />
            <button className="add-btn" onClick={runPreview} disabled={isPreviewing}>
              {isPreviewing ? "查詢中" : "預覽"}
            </button>
          </div>
          {previewError && <small className="hint">{previewError}</small>}
          {previewHits.length > 0 && (
            <div className="preview-hit-list">
              {previewHits.map((hit) => (
                <div key={hit.id} className="preview-hit">
                  <strong>{hit.title}</strong>
                  <small>{hit.id} · score {hit.score.toFixed(3)}</small>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      <div className="prop-row">
        <label>知識庫檔案</label>
        <input type="text" value={kb} placeholder="examples/knowledge/shoe_store.json"
          disabled={Boolean(kbRef)}
          onChange={(e) => onUpdate(setParam(spec, "knowledge_base", e.target.value))} />
        <small className="hint">領域知識（產品型錄、SOP、FAQ）的 JSON 檔路徑；預先建立、不隨對話變動。與對話記憶預設並用。</small>
      </div>
      <div className="prop-row">
        <label>取回筆數</label>
        <input type="number" min="1" value={topK}
          onChange={(e) => onUpdate(setParam(spec, "top_k", Number(e.target.value)))} />
      </div>
      <div className="prop-row">
        <label>相似度權重</label>
        <input type="number" step="0.1" value={sim}
          onChange={(e) => onUpdate(setParam(spec, "similarity_weight", Number(e.target.value)))} />
      </div>
      <div className="prop-row">
        <label>時間權重</label>
        <input type="number" step="0.1" value={rec}
          onChange={(e) => onUpdate(setParam(spec, "recency_weight", Number(e.target.value)))} />
      </div>
      <div className="prop-row">
        <label>重要性權重</label>
        <input type="number" step="0.1" value={imp}
          onChange={(e) => onUpdate(setParam(spec, "importance_weight", Number(e.target.value)))} />
        <small className="hint">三項權重相加應為 1；僅套用於對話記憶、不影響知識庫。</small>
      </div>
      <div className="prop-row">
        <label>啟用圖像摘要</label>
        <label style={{ display: "flex", alignItems: "center", gap: 8, fontWeight: "normal" }}>
          <input type="checkbox" checked={vis}
            onChange={(e) => onUpdate(setParam(spec, "enable_vision_query", e.target.checked))} />
          使用者上傳圖片時，先由 Foundry 圖文模型萃取檢索關鍵字
        </label>
        <small className="hint">啟用後，輸出的 Python 會自動注入 FoundryVisionQuery；未上傳圖片時不會額外耗用 token。</small>
      </div>
    </>
  );
}

function PlanEditor({ spec, onUpdate }: { spec: NodeSpec; onUpdate: (s: NodeSpec) => void }) {
  const model        = (spec.params?.model as string | undefined) ?? MODEL_PRESETS[0].value;
  const systemPrompt = (spec.params?.system_prompt as string | undefined) ?? "";

  const handleModel = (value: string) => {
    const p = MODEL_PRESETS.find((m) => m.value === value);
    if (!p) return;
    onUpdate({
      ...spec,
      compute_target: p.compute_target,
      params: {
        ...spec.params,
        model: p.value,
        endpoint: p.endpoint,
        deployment: p.deployment,
      },
    });
  };

  return (
    <>
      <div className="prop-row">
        <label>模型</label>
        <select value={model} onChange={(e) => handleModel(e.target.value)}>
          {MODEL_PRESETS.map((p) => (
            <option key={p.value} value={p.value}>{p.label}（{p.platform}）</option>
          ))}
        </select>
        <small className="hint">Plan 節點用於分析意圖並決策路由，建議使用推理能力較強的模型。</small>
      </div>
      <div className="prop-row">
        <label>路由指令</label>
        <textarea rows={8} value={systemPrompt}
          onChange={(e) => onUpdate(setParam(spec, "system_prompt", e.target.value))}
          placeholder="告訴 Plan LLM 什麼情況走 retrieve、什麼情況直接 action" />
        <small className="hint">切換模組時自動填入預設指令，可手動調整。</small>
      </div>
    </>
  );
}

function ReflectEditor({ spec, onUpdate }: { spec: NodeSpec; onUpdate: (s: NodeSpec) => void }) {
  const onFailure = (spec.params?.on_failure as string | undefined) ?? "retry_plan";
  return (
    <div className="prop-row">
      <label>失敗處理</label>
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
  const model         = (spec.params?.model as string | undefined) ?? MODEL_PRESETS[0].value;
  const temperature   = (spec.params?.temperature as number | undefined) ?? 0.2;
  const systemPrompt  = (spec.params?.system_prompt as string | undefined) ?? "";

  const handleModel = (value: string) => {
    const p = MODEL_PRESETS.find((m) => m.value === value);
    if (!p) return;
    onUpdate({
      ...spec,
      compute_target: p.compute_target,
      params: {
        ...spec.params,
        model: p.value,
        endpoint: p.endpoint,
        deployment: p.deployment,
      },
    });
  };

  return (
    <>
      <div className="prop-row">
        <label>模型</label>
        <select value={model} onChange={(e) => handleModel(e.target.value)}>
          {MODEL_PRESETS.map((p) => (
            <option key={p.value} value={p.value}>{p.label}（{p.platform}）</option>
          ))}
        </select>
      </div>
      <div className="prop-row">
        <label>角色設定</label>
        <textarea rows={6} value={systemPrompt}
          placeholder="例：你是親切專業的鞋店門市專員……"
          onChange={(e) => onUpdate(setParam(spec, "system_prompt", e.target.value))} />
        <small className="hint">對應到 LLM 的 system prompt，定義回應者的身分、語氣與表達原則。</small>
      </div>
      <div className="prop-row">
        <label>回應多樣性</label>
        <input type="number" step="0.1" min="0" max="2" value={temperature}
          onChange={(e) => onUpdate(setParam(spec, "temperature", Number(e.target.value)))} />
      </div>
    </>
  );
}
