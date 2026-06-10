import { useState, type FormEvent } from "react";
import type { ChatMessage } from "../runtime/types";

interface Props {
  messages: ChatMessage[];
  isRunning: boolean;
  onSend: (text: string) => void;
}

export function ChatPanel({ messages, isRunning, onSend }: Props) {
  const [input, setInput] = useState("");

  const submit = (e: FormEvent) => {
    e.preventDefault();
    const text = input.trim();
    if (!text || isRunning) return;
    onSend(text);
    setInput("");
  };

  return (
    <div className="chat-panel">
      <div className="chat-stream">
        {messages.length === 0 && (
          <div className="chat-empty">在下方輸入框送出訊息開始一次工作流。</div>
        )}
        {messages.map((m, i) => (
          <div key={i} className={`chat-msg chat-msg-${m.role}`}>
            <div className="chat-msg-role">{m.role}</div>
            <div className="chat-msg-content">{m.content || (isRunning && i === messages.length - 1 ? "執行中…" : "")}</div>
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
      <form className="chat-input" onSubmit={submit}>
        <input
          type="text"
          placeholder={isRunning ? "工作流執行中…" : "輸入訊息,Enter 送出"}
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
