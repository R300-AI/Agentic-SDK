/** M8-1 — 左側下半部工具區：Memory Stream 指示 + YAML/Python 輸出。
 * 已不再是獨立的 aside，而是 LEFT 主面板下半段；屬性編輯器在其上方。
 */

import { useState } from "react";

interface Props {
  onDownload: () => void;
  onLoad: (yaml: string) => void;
  onShowPython: () => void;
}

export function NodePalette({ onDownload, onLoad, onShowPython }: Props) {
  const handleFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      const text = String(reader.result ?? "");
      onLoad(text);
    };
    reader.readAsText(file, "utf-8");
    e.target.value = "";
  };

  return (
    <div className="left-tools">
      <h3>Memory Stream</h3>
      <div className="memory-indicator">
        <div className="memory-indicator-icon">⛁</div>
        <div className="memory-indicator-body">
          <div>跨 run 持久化</div>
          <small>workflow_name 隔離</small>
        </div>
      </div>

      <hr />
      <h3>輸出</h3>
      <div className="left-tools-buttons">
        <button onClick={onDownload}>下載 YAML</button>
        <button onClick={onShowPython}>顯示 Python</button>
        <label className="file-button">
          載入 YAML
          <input type="file" accept=".yaml,.yml" onChange={handleFile} />
        </label>
      </div>
    </div>
  );
}

interface PythonModalProps {
  code: string;
  onClose: () => void;
}

export function PythonModal({ code, onClose }: PythonModalProps) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // 部分瀏覽器在 http 環境無 clipboard,fallback 為 select
      const el = document.getElementById("python-code-pre");
      if (el) {
        const r = document.createRange();
        r.selectNodeContents(el);
        const sel = window.getSelection();
        sel?.removeAllRanges();
        sel?.addRange(r);
      }
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-panel" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h3>Python 程式碼(M6-10)</h3>
          <div className="modal-actions">
            <button onClick={handleCopy}>{copied ? "已複製" : "複製"}</button>
            <button onClick={onClose}>關閉</button>
          </div>
        </div>
        <pre id="python-code-pre" className="modal-code">{code}</pre>
      </div>
    </div>
  );
}
