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
      setTimeout(() => setCopied(false), 1800);
    } catch {
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
      <div className="deploy-modal" onClick={(e) => e.stopPropagation()}>
        <button className="deploy-close" onClick={onClose} aria-label="關閉">×</button>

        <div className="deploy-icon">⬇</div>
        <h2 className="deploy-title">部署到 Python 環境</h2>
        <p className="deploy-subtitle">
          複製以下程式碼到您的 Python 專案，即可執行此工作流。
        </p>

        <div className="deploy-code-card">
          <button className="deploy-code-copy" onClick={handleCopy} aria-label="複製">
            {copied ? "✓" : "⧉"}
          </button>
          <pre id="python-code-pre" className="deploy-code">{code}</pre>
        </div>

        <div className="deploy-notice">
          <span className="deploy-notice-icon">⚠</span>
          <span>請確認 <code>.env</code> 已設定模型對應的 API 金鑰與端點。</span>
        </div>

        <button className="deploy-primary" onClick={handleCopy}>
          {copied ? "已複製到剪貼簿" : "複製程式碼"}
        </button>
      </div>
    </div>
  );
}
