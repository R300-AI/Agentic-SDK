import { useMemo } from "react";
import type { NodeSpec } from "../types";
import {
  ACTION_BACKEND_OPTIONS,
  PLAN_PROMPT_TEMPLATES,
  REFLECT_ON_FAILURE_OPTIONS,
} from "../types";

interface Props {
  selectedNodeId: string | null;
  spec: NodeSpec | null;
  onUpdate: (spec: NodeSpec) => void;
}

export function PropertyPanel({ selectedNodeId, spec, onUpdate }: Props) {
  if (!selectedNodeId || !spec) {
    return (
      <aside className="property-panel">
        <h3>屬性</h3>
        <p className="hint">點選畫布節點以編輯屬性。</p>
      </aside>
    );
  }

  return (
    <aside className="property-panel">
      <h3>{selectedNodeId}</h3>
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
      return <ReadOnlyEditor type={spec.type} note="rule_based(無 LLM)" />;
    case "retrieve":
      return <ReadOnlyEditor type={spec.type} note="PoC 階段僅 stub backend" />;
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

function ReadOnlyEditor({ type, note }: { type: string; note: string }) {
  return (
    <div className="prop-row">
      <label>type</label>
      <code>{type}</code>
      <small className="hint">{note}</small>
    </div>
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

  const updatePrompt = (next: string) => {
    onUpdate({
      type: spec.type,
      params: { ...spec.params, system_prompt: next },
    });
  };

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
  const current = (spec.params?.on_failure as string | undefined) ?? "retry_plan";

  return (
    <div className="prop-row">
      <label>on_failure</label>
      <select
        value={current}
        onChange={(e) =>
          onUpdate({
            type: spec.type,
            params: { ...spec.params, on_failure: e.target.value },
          })
        }
      >
        {REFLECT_ON_FAILURE_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </div>
  );
}

function ActionEditor({
  spec,
  onUpdate,
}: {
  spec: NodeSpec;
  onUpdate: (spec: NodeSpec) => void;
}) {
  const current = ACTION_BACKEND_OPTIONS.find((o) => o.typeString === spec.type)?.value ?? "foundry";

  return (
    <div className="prop-row">
      <label>backend</label>
      <select
        value={current}
        onChange={(e) => {
          const opt = ACTION_BACKEND_OPTIONS.find((o) => o.value === e.target.value);
          if (!opt) return;
          onUpdate({ type: opt.typeString, params: spec.params });
        }}
      >
        {ACTION_BACKEND_OPTIONS.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
      <small className="hint">
        實際模型由 Gateway 端 settings 決定;UI 只切 upstream / foundry 兩種 class。
      </small>
    </div>
  );
}
