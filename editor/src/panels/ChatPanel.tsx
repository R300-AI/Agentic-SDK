/** M6-7 + M8-3 — Chat Panel：由 Perceive 節點屬性驅動的對話介面。
 *
 * 開場與引導選項從 Perceive spec 讀取。
 * M8-3：點選引導按鈕只「填入」輸入框（BingChat 風格），不自動送出；使用者按下 Enter 才啟動。
 */

import { useEffect, useRef, useState, type FormEvent } from "react";
import type { ChatMessage } from "../runtime/types";
import type { NodeSpec, PerceiveOption } from "../types";

interface Props {
  messages: ChatMessage[];
  isRunning: boolean;
  onSend: (text: string) => void;
  perceiveSpec: NodeSpec | null;
}

export function ChatPanel({ messages, isRunning, onSend, perceiveSpec }: Props) {
  const [input, setInput] = useState("");
  const inputRef = useRef<HTMLInputElement | null>(null);

  const welcome = (perceiveSpec?.params?.welcome_message as string | undefined) ?? "";
  const options = (perceiveSpec?.params?.options as PerceiveOption[] | undefined) ?? [];

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || isRunning) return;
    onSend(text);
    setInput("");
  };

  const handleOption = (opt: PerceiveOption) => {
    if (isRunning) return;
    setInput(opt.label);
    inputRef.current?.focus();
  };

  const showWelcome = messages.length === 0 && (welcome || options.length > 0);

  // 進入時自動聚焦輸入框
  useEffect(() => { inputRef.current?.focus(); }, []);

  return (
    <div className="chat-panel">
      <div className="chat-stream">
        {showWelcome ? (
          <div className="chat-welcome">
            {welcome && <div className="chat-welcome-text">{welcome}</div>}
          </div>
        ) : messages.length === 0 ? (
          <div className="chat-empty">在下方輸入框送出訊息開始一次工作流。</div>
        ) : null}

        {messages.map((m, i) => (
          <div key={i} className={`chat-msg chat-msg-${m.role}`}>
            <div className="chat-msg-role">{m.role}</div>
            <div className="chat-msg-content">
              {m.content || (isRunning && i === messages.length - 1 ? "執行中…" : "")}
            </div>
            {m.metadata && (
              <div className="chat-msg-meta">
                {m.metadata.model && <span>{m.metadata.model}</span>}
                {m.metadata.input_tokens !== undefined && (
                  <span>↑{m.metadata.input_tokens}</span>
                )}
                {m.metadata.output_tokens !== undefined && (
                  <span>↓{m.metadata.output_tokens}</span>
                )}
                {m.metadata.elapsed_ms !== undefined && (
                  <span>{m.metadata.elapsed_ms}ms</span>
                )}
              </div>
            )}
          </div>
        ))}
      </div>

      {options.length > 0 && (
        <div className="chat-suggestions">
          {options.map((opt, i) => (
            <button
              key={i}
              className="chat-suggestion-btn"
              onClick={() => handleOption(opt)}
              disabled={isRunning}
              type="button"
              title={`填入「${opt.label}」`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      )}

      <form className="chat-input" onSubmit={submit}>
        <input
          ref={inputRef}
          type="text"
          placeholder={isRunning ? "工作流執行中…" : "輸入訊息，Enter 送出（點上方按鈕僅填入文字）"}
          disabled={isRunning}
          value={input}
          onChange={(e) => setInput(e.target.value)}
        />
        <button type="submit" disabled={isRunning || !input.trim()}>
          跑一次
        </button>
      </form>
    </div>
  );
}
