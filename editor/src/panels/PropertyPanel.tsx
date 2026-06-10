/** M6-9 — 白盒化屬性面板。
 *
 * 每個節點都有專屬編輯器;所有節點共用 compute_target 下拉(M6-4)。
 * Action 一律白盒:endpoint / deployment / api_key(明文)/ model / temperature 可直接編輯。
 */

import type React from "react";
import { useMemo } from "react";
import type { NodeSpec, PerceiveOption } from "../types";
import {
  ACTION_BACKEND_OPTIONS,
  COMPUTE_TARGET_OPTIONS,
  PLAN_PROMPT_TEMPLATES,
  REFLECT_MODE_OPTIONS,
  REFLECT_ON_FAILURE_OPTIONS,
} from "../types";

interface Props {
  selectedNodeId: string | null;
  spec: NodeSpec | null;
  onUpdate: (spec: NodeSpec) => void;
  style?: React.CSSProperties;
}

export function PropertyPanel({ selectedNodeId, spec, onUpdate, style }: Props) {
  if (!selectedNodeId || !spec) {
    return (
      <aside className="property-panel" style={style}>
        <h3>屬性</h3>
        <p className="hint">點選畫布節點以編輯屬性。</p>
      </aside>
    );
  }

  return (
    <aside className="property-panel" style={style}>
      <h3>{selectedNodeId}</h3>
      <ComputeTargetEditor spec={spec} onUpdate={onUpdate} />
      <hr className="prop-divider" />
      <Editor nodeId={selectedNodeId} spec={spec} onUpdate={onUpdate} />
    </aside>
  );
}

function Editor({
  nodeId,
  spec,
  onUpdate,
}: {
  nodeId: string;
  spec: NodeSpec;
  onUpdate: (spec: NodeSpec) => void;
}) {
  switch (nodeId) {
    case "perceive":
      return <PerceiveEditor spec={spec} onUpdate={onUpdate} />;
    case "retrieve":
      return <RetrieveEditor spec={spec} onUpdate={onUpdate} />;
    case "plan":
      return <PlanEditor spec={spec} onUpdate={onUpdate} />;
    case "reflect":
      return <ReflectEditor spec={spec} onUpdate={onUpdate} />;
    case "action":
      return <ActionEditor spec={spec} onUpdate={onUpdate} />;
    default:
      return <pre>{JSON.stringify(spec, null, 2)}</pre>;
  }
}

function ComputeTargetEditor({
  spec,
  onUpdate,
}: {
  spec: NodeSpec;
  onUpdate: (spec: NodeSpec) => void;
}) {
  const current = spec.compute_target ?? "local_cpu";
  return (
    <div className="prop-row">
      <label>compute_target(M6-4)</label>
      <select
        value={current}
        onChange={(e) => onUpdate({ ...spec, compute_target: e.target.value })}
      >
        {COMPUTE_TARGET_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <small className="hint">節點實際 offload 至哪個計算資源。Phase 1 為靜態綁定。</small>
    </div>
  );
}

function setParam(spec: NodeSpec, key: string, value: unknown): NodeSpec {
  return { ...spec, params: { ...spec.params, [key]: value } };
}

function PerceiveEditor({
  spec,
  onUpdate,
}: {
  spec: NodeSpec;
  onUpdate: (spec: NodeSpec) => void;
}) {
  const welcome = (spec.params?.welcome_message as string | undefined) ?? "";
  const options = (spec.params?.options as PerceiveOption[] | undefined) ?? [];
  const importance = (spec.params?.importance as number | undefined) ?? 1.0;

  const updateOptions = (next: PerceiveOption[]) => onUpdate(setParam(spec, "options", next));
  const addOption = () =>
    updateOptions([...options, { label: "新選項", value: "new", intent: "general" }]);
  const removeOption = (i: number) => updateOptions(options.filter((_, idx) => idx !== i));
  const updateOption = (i: number, patch: Partial<PerceiveOption>) =>
    updateOptions(options.map((o, idx) => (idx === i ? { ...o, ...patch } : o)));

  return (
    <>
      <div className="prop-row">
        <label>welcome_message</label>
        <textarea
          rows={3}
          value={welcome}
          onChange={(e) => onUpdate(setParam(spec, "welcome_message", e.target.value))}
          placeholder="進入工作流時 Chat Panel 顯示的開場白"
        />
      </div>

      <div className="prop-row">
        <label>options(引導選項)</label>
        {options.map((opt, i) => (
          <div key={i} className="perceive-option">
            <input
              type="text"
              value={opt.label}
              placeholder="顯示文字"
              onChange={(e) => updateOption(i, { label: e.target.value })}
            />
            <input
              type="text"
              value={opt.value}
              placeholder="送出值"
              onChange={(e) => updateOption(i, { value: e.target.value })}
            />
            <input
              type="text"
              value={opt.intent}
              placeholder="intent"
              onChange={(e) => updateOption(i, { intent: e.target.value })}
            />
            <button className="icon-btn" onClick={() => removeOption(i)} title="移除">×</button>
          </div>
        ))}
        <button className="add-btn" onClick={addOption}>+ 新增選項</button>
        <small className="hint">UI Chat Panel 會把這份清單渲染為按鈕。</small>
      </div>

      <div className="prop-row">
        <label>importance(寫入 Memory 的權重)</label>
        <input
          type="number"
          step="0.1"
          value={importance}
          onChange={(e) => onUpdate(setParam(spec, "importance", Number(e.target.value)))}
        />
      </div>
    </>
  );
}

function RetrieveEditor({
  spec,
  onUpdate,
}: {
  spec: NodeSpec;
  onUpdate: (spec: NodeSpec) => void;
}) {
  const topK = (spec.params?.top_k as number | undefined) ?? 3;
  const sim = (spec.params?.similarity_weight as number | undefined) ?? 0.5;
  const rec = (spec.params?.recency_weight as number | undefined) ?? 0.3;
  const imp = (spec.params?.importance_weight as number | undefined) ?? 0.2;

  return (
    <>
      <div className="prop-row">
        <label>top_k</label>
        <input
          type="number"
          min="1"
          value={topK}
          onChange={(e) => onUpdate(setParam(spec, "top_k", Number(e.target.value)))}
        />
      </div>
      <div className="prop-row">
        <label>similarity_weight</label>
        <input
          type="number"
          step="0.1"
          value={sim}
          onChange={(e) => onUpdate(setParam(spec, "similarity_weight", Number(e.target.value)))}
        />
      </div>
      <div className="prop-row">
        <label>recency_weight</label>
        <input
          type="number"
          step="0.1"
          value={rec}
          onChange={(e) => onUpdate(setParam(spec, "recency_weight", Number(e.target.value)))}
        />
      </div>
      <div className="prop-row">
        <label>importance_weight</label>
        <input
          type="number"
          step="0.1"
          value={imp}
          onChange={(e) => onUpdate(setParam(spec, "importance_weight", Number(e.target.value)))}
        />
        <small className="hint">三項加權對齊 Generative Agents §4.1。</small>
      </div>
    </>
  );
}

function PlanEditor({
  spec,
  onUpdate,
}: {
  spec: NodeSpec;
  onUpdate: (spec: NodeSpec) => void;
}) {
  const current = (spec.params?.system_prompt as string | undefined) ?? PLAN_PROMPT_TEMPLATES.react;
  const matchedTemplate = useMemo(() => {
    const entry = Object.entries(PLAN_PROMPT_TEMPLATES).find(([, v]) => v === current);
    return entry?.[0] ?? "custom";
  }, [current]);

  const updatePrompt = (next: string) => onUpdate(setParam(spec, "system_prompt", next));

  return (
    <>
      <div className="prop-row">
        <label>system_prompt 模板</label>
        <select
          value={matchedTemplate}
          onChange={(e) => {
            const k = e.target.value;
            if (k !== "custom" && PLAN_PROMPT_TEMPLATES[k]) {
              updatePrompt(PLAN_PROMPT_TEMPLATES[k]);
            }
          }}
        >
          {Object.keys(PLAN_PROMPT_TEMPLATES).map((k) => (
            <option key={k} value={k}>
              {k}
            </option>
          ))}
          <option value="custom">custom</option>
        </select>
      </div>
      <div className="prop-row">
        <label>system_prompt 內容</label>
        <textarea
          rows={8}
          value={current}
          onChange={(e) => updatePrompt(e.target.value)}
        />
        <small className="hint">儲存 YAML 時只存最終文字,不存模板名。</small>
      </div>
    </>
  );
}

function ReflectEditor({
  spec,
  onUpdate,
}: {
  spec: NodeSpec;
  onUpdate: (spec: NodeSpec) => void;
}) {
  const onFailure = (spec.params?.on_failure as string | undefined) ?? "retry_plan";
  const mode = (spec.params?.mode as string | undefined) ?? "rule_based";

  return (
    <>
      <div className="prop-row">
        <label>mode(M6-6)</label>
        <select
          value={mode}
          onChange={(e) => onUpdate(setParam(spec, "mode", e.target.value))}
        >
          {REFLECT_MODE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <small className="hint">LLM 反思走 Reflexion(Shinn 2023);規則式零成本即時判斷。</small>
      </div>
      <div className="prop-row">
        <label>on_failure</label>
        <select
          value={onFailure}
          onChange={(e) => onUpdate(setParam(spec, "on_failure", e.target.value))}
        >
          {REFLECT_ON_FAILURE_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>
    </>
  );
}

function ActionEditor({
  spec,
  onUpdate,
}: {
  spec: NodeSpec;
  onUpdate: (spec: NodeSpec) => void;
}) {
  const currentBackend = ACTION_BACKEND_OPTIONS.find((o) => o.typeString === spec.type)?.value ?? "foundry";
  const endpoint = (spec.params?.endpoint as string | undefined) ?? "";
  const deployment = (spec.params?.deployment as string | undefined) ?? "";
  const apiKey = (spec.params?.api_key as string | undefined) ?? "";
  const model = (spec.params?.model as string | undefined) ?? "";
  const temperature = (spec.params?.temperature as number | undefined) ?? 0.2;

  return (
    <>
      <div className="prop-row">
        <label>backend</label>
        <select
          value={currentBackend}
          onChange={(e) => {
            const opt = ACTION_BACKEND_OPTIONS.find((o) => o.value === e.target.value);
            if (!opt) return;
            onUpdate({ ...spec, type: opt.typeString });
          }}
        >
          {ACTION_BACKEND_OPTIONS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
      </div>
      <div className="prop-row">
        <label>endpoint</label>
        <input
          type="text"
          value={endpoint}
          placeholder="https://<resource>.openai.azure.com 或 NPU 服務 URL"
          onChange={(e) => onUpdate(setParam(spec, "endpoint", e.target.value))}
        />
      </div>
      <div className="prop-row">
        <label>deployment</label>
        <input
          type="text"
          value={deployment}
          placeholder="部署名稱(Foundry)或留空"
          onChange={(e) => onUpdate(setParam(spec, "deployment", e.target.value))}
        />
      </div>
      <div className="prop-row">
        <label>api_key(明文 — 僅 PoC)</label>
        <input
          type="text"
          value={apiKey}
          placeholder="留空則由 Gateway 後端讀環境變數"
          onChange={(e) => onUpdate(setParam(spec, "api_key", e.target.value))}
        />
      </div>
      <div className="prop-row">
        <label>model</label>
        <input
          type="text"
          value={model}
          placeholder="例:gpt-4o-mini、phi-3"
          onChange={(e) => onUpdate(setParam(spec, "model", e.target.value))}
        />
      </div>
      <div className="prop-row">
        <label>temperature</label>
        <input
          type="number"
          step="0.1"
          min="0"
          max="2"
          value={temperature}
          onChange={(e) => onUpdate(setParam(spec, "temperature", Number(e.target.value)))}
        />
        <small className="hint">空字串欄位儲存時自動忽略,讓 Gateway 走 settings 預設。</small>
      </div>
    </>
  );
}
