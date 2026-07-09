/** Chat Panel：由 Perceive 節點屬性驅動的對話介面。
 *
 * D6 設計原則：
 * 1. 引導選項每輪（使用者輪）顯示，不只首輪。
 * 2. 圖片附件採 Open WebUI 風格大縮圖（64px）預覽。
 * 3. Assistant 訊息以 marked 渲染 Markdown。
 */

import { useEffect, useRef, useState, type FormEvent } from "react";
import { marked } from "marked";
import type { ChatMessage } from "../runtime/types";
import type { Attachment, NodeSpec, PerceiveOption } from "../types";
import type { RuntimeMode } from "../runtime/gatewayUrl";

interface Props {
  messages: ChatMessage[];
  isRunning: boolean;
  onSend: (text: string, attachments?: Attachment[]) => void;
  perceiveSpec: NodeSpec | null;
  gatewayUrl: string;
  onGatewayUrlChange: (url: string) => void;
  runtimeMode: RuntimeMode;
  onRuntimeModeChange: (mode: RuntimeMode) => void;
}

async function fileToAttachment(file: File): Promise<Attachment> {
  const data_url = await new Promise<string>((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result as string);
    r.onerror = () => reject(r.error);
    r.readAsDataURL(file);
  });
  return {
    kind: file.type.startsWith("image/") ? "image" : "file",
    mime: file.type || "application/octet-stream",
    data_url,
    name: file.name,
  };
}

/** 最後一輪是 user 還是 assistant？用來決定是否顯示選項列 */
function lastRoleIs(messages: ChatMessage[], role: "user" | "assistant") {
  if (messages.length === 0) return false;
  return messages[messages.length - 1].role === role;
}

export function ChatPanel({ messages, isRunning, onSend, perceiveSpec, gatewayUrl, onGatewayUrlChange, runtimeMode, onRuntimeModeChange }: Props) {
  const [input, setInput] = useState("");
  const [pending, setPending] = useState<Attachment[]>([]);
  const [lightbox, setLightbox] = useState<string | null>(null);
  const [gwInput, setGwInput] = useState(gatewayUrl);
  const [gwEditing, setGwEditing] = useState(false);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const fileRef = useRef<HTMLInputElement | null>(null);
  const streamRef = useRef<HTMLDivElement | null>(null);

  const welcome = (perceiveSpec?.params?.welcome_message as string | undefined) ?? "";
  const options = (perceiveSpec?.params?.options as PerceiveOption[] | undefined) ?? [];

  const showPlaceholder = messages.length === 0;
  // 選項列：首輪（佔位區）或每次輪到使用者（上一輪是 assistant 且非執行中）
  const showOptions = options.length > 0 && (showPlaceholder || (!isRunning && lastRoleIs(messages, "assistant")));

  // 自動捲動到底
  useEffect(() => {
    if (streamRef.current) {
      streamRef.current.scrollTop = streamRef.current.scrollHeight;
    }
  }, [messages]);

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if ((!text && pending.length === 0) || isRunning) return;
    onSend(text, pending.length > 0 ? pending : undefined);
    setInput("");
    setPending([]);
  };

  const handleOption = (opt: PerceiveOption) => {
    if (isRunning) return;
    setInput(opt.label);
    inputRef.current?.focus();
    if (opt.expects_attachment) {
      fileRef.current?.click();
    }
  };

  const handleFiles = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = Array.from(e.target.files ?? []);
    if (!files.length) return;
    const atts = await Promise.all(files.map(fileToAttachment));
    setPending((prev) => [...prev, ...atts]);
    if (fileRef.current) fileRef.current.value = "";
  };

  const removePending = (idx: number) => {
    setPending((prev) => prev.filter((_, i) => i !== idx));
  };

  useEffect(() => { inputRef.current?.focus(); }, []);

  const gwMissing = false; // same-origin 部署時空字串即合法，不顯示警告

  const handleGwSubmit = (e: FormEvent) => {
    e.preventDefault();
    onGatewayUrlChange(gwInput.trim());
    setGwEditing(false);
  };

  return (
    <div className="chat-panel">
      {/* ── Lightbox ── */}
      {lightbox && (
        <div className="chat-lightbox" onClick={() => setLightbox(null)}>
          <img src={lightbox} alt="preview" onClick={(e) => e.stopPropagation()} />
        </div>
      )}

      {/* ── Gateway URL 列 ── */}
      <div className={`chat-gateway-bar ${gwMissing ? "chat-gateway-bar--warn" : ""}`}>
        <div className="chat-mode-switch" role="group" aria-label="runtime mode switch">
          <button
            type="button"
            className={`chat-mode-btn${runtimeMode === "gateway" ? " active" : ""}`}
            onClick={() => onRuntimeModeChange("gateway")}
          >Gateway</button>
          <button
            type="button"
            className={`chat-mode-btn${runtimeMode === "managed" ? " active" : ""}`}
            onClick={() => onRuntimeModeChange("managed")}
          >Managed</button>
        </div>
        {gwEditing ? (
          <form className="chat-gateway-form" onSubmit={handleGwSubmit}>
            <input
              autoFocus
              type="url"
              placeholder="http://localhost:8080"
              value={gwInput}
              onChange={(e) => setGwInput(e.target.value)}
              className="chat-gateway-input"
            />
            <button type="submit" className="chat-gateway-btn">確定</button>
            <button type="button" className="chat-gateway-btn" onClick={() => { setGwInput(gatewayUrl); setGwEditing(false); }}>取消</button>
          </form>
        ) : (
          <span
            className="chat-gateway-label"
            onClick={() => {
              if (runtimeMode === "gateway") setGwEditing(true);
            }}
            title="點擊修改 Gateway URL"
          >
            {runtimeMode === "managed"
              ? `Managed AI Hub mode • build ${__BUILD_TIME__}`
              : gwMissing
              ? "⚠ 未設定 Gateway URL，點此輸入（如 http://localhost:8080）"
              : `Gateway: ${gatewayUrl || "dev proxy"} • build ${__BUILD_TIME__}`}
          </span>
        )}
      </div>

      <div className="chat-stream" ref={streamRef}>
        {showPlaceholder ? (
          <div className="chat-placeholder">
            {welcome && <div className="chat-placeholder-title">{welcome}</div>}
            {!welcome && !options.length && (
              <div className="chat-placeholder-title">在下方輸入訊息開始工作流</div>
            )}
            {options.length > 0 && (
              <div className="chat-placeholder-grid">
                {options.map((opt, i) => (
                  <button
                    key={i}
                    className="chat-placeholder-card"
                    style={{ animationDelay: `${i * 60}ms` }}
                    onClick={() => handleOption(opt)}
                    disabled={isRunning}
                    type="button"
                    title={opt.expects_attachment ? "點此填入並開啟附件選擇器" : undefined}
                  >
                    <div className="chat-placeholder-card-label">{opt.label}</div>
                  </button>
                ))}
              </div>
            )}
          </div>
        ) : (
          messages.map((m, i) => (
            <div key={i} className={`chat-msg chat-msg-${m.role}`}>
              <div className="chat-msg-role">{m.role}</div>
              {m.role === "assistant" ? (
                <div
                  className="chat-msg-content chat-msg-markdown"
                  dangerouslySetInnerHTML={{
                    __html: marked.parse(
                      m.content || (isRunning && i === messages.length - 1 ? "執行中…" : "")
                    ) as string,
                  }}
                />
              ) : (
                <div className="chat-msg-content">
                  {m.content || (isRunning && i === messages.length - 1 ? "執行中…" : "")}
                </div>
              )}
              {m.metadata && (
                <>
                  {m.metadata.plan_thought && (
                    <details className="chat-plan-thought">
                      <summary>💭 Plan 推理</summary>
                      <p>{m.metadata.plan_thought}</p>
                      {m.metadata.plan_next_node && (
                        <span className="chat-plan-next">→ {m.metadata.plan_next_node}</span>
                      )}
                    </details>
                  )}
                  <div className="chat-msg-meta">
                    {m.metadata.model && <span>{m.metadata.model}</span>}
                    {m.metadata.input_tokens !== undefined && <span>↑{m.metadata.input_tokens}</span>}
                    {m.metadata.output_tokens !== undefined && <span>↓{m.metadata.output_tokens}</span>}
                    {m.metadata.elapsed_ms !== undefined && <span>{m.metadata.elapsed_ms}ms</span>}
                  </div>
                </>
              )}
            </div>
          ))
        )}
      </div>

      {/* ── 每輪選項列（非首輪、輪到使用者時） ── */}
      {showOptions && !showPlaceholder && (
        <div className="chat-options-bar">
          {options.map((opt, i) => (
            <button
              key={i}
              className="chat-option-chip"
              onClick={() => handleOption(opt)}
              disabled={isRunning}
              type="button"
              title={opt.expects_attachment ? "點此填入並開啟附件選擇器" : undefined}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}

      {/* ── 附件預覽列（Open WebUI 風格大縮圖） ── */}
      {pending.length > 0 && (
        <div className="chat-attachments">
          {pending.map((a, i) => (
            <div key={i} className="chat-attachment-preview">
              {a.kind === "image" ? (
                <img
                  src={a.data_url}
                  alt={a.name ?? ""}
                  className="chat-attachment-thumb"
                  onClick={() => setLightbox(a.data_url)}
                  title="點擊放大"
                />
              ) : (
                <div className="chat-attachment-file-icon">📎</div>
              )}
              <div className="chat-attachment-label">{a.name ?? a.mime}</div>
              <button
                type="button"
                className="chat-attachment-remove"
                onClick={() => removePending(i)}
                aria-label="移除附件"
              >×</button>
            </div>
          ))}
        </div>
      )}

      <form className="chat-input" onSubmit={submit}>
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          multiple
          style={{ display: "none" }}
          onChange={handleFiles}
        />
        <button
          type="button"
          className="chat-attach-btn"
          onClick={() => fileRef.current?.click()}
          disabled={isRunning}
          aria-label="附加圖片"
          title="附加圖片"
        >+</button>
        <input
          ref={inputRef}
          type="text"
          placeholder={isRunning ? "工作流執行中…" : "輸入訊息，Enter 送出"}
          disabled={isRunning}
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <button
          type="submit"
          disabled={isRunning || (!input.trim() && pending.length === 0)}
        >
          跑一次
        </button>
      </form>
    </div>
  );
}


