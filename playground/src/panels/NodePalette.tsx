/** M8-1 — 左側下半部工具區：Memory Stream 指示 + YAML/Python 輸出。
 * 已不再是獨立的 aside，而是 LEFT 主面板下半段；屬性編輯器在其上方。
 */

import { useState } from "react";
import type { BundleFile } from "../bundleExport";

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
  bundleFiles: BundleFile[];
  onClose: () => void;
}

const PY_KEYWORDS = new Set([
  "False", "None", "True", "and", "as", "assert", "async", "await",
  "break", "class", "continue", "def", "del", "elif", "else", "except",
  "finally", "for", "from", "global", "if", "import", "in", "is",
  "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "try",
  "while", "with", "yield", "match", "case",
]);

const PY_BUILTINS = new Set([
  "print", "len", "range", "list", "dict", "set", "tuple", "str", "int",
  "float", "bool", "isinstance", "type", "open", "enumerate", "zip",
  "map", "filter", "any", "all", "sum", "min", "max", "sorted", "reversed",
  "Exception", "ValueError", "TypeError", "KeyError", "RuntimeError",
  "__name__", "__main__", "self", "cls",
]);

const escapeHtml = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");

/** 極簡 Python 高亮：line-by-line，先抽掉 comments/strings 再標記 keywords/numbers。 */
function highlightPython(src: string): string {
  return src.split("\n").map((line) => highlightLine(line)).join("\n");
}

function highlightLine(line: string): string {
  const tokens: string[] = [];
  let i = 0;
  while (i < line.length) {
    const ch = line[i];

    // 註解
    if (ch === "#") {
      tokens.push(`<span class="hl-com">${escapeHtml(line.slice(i))}</span>`);
      i = line.length;
      break;
    }

    // 字串（單行三引號簡化處理為一般字串）
    if (ch === '"' || ch === "'") {
      const quote = ch;
      let j = i + 1;
      // 三引號
      if (line.slice(i, i + 3) === quote.repeat(3)) {
        j = i + 3;
        while (j < line.length && line.slice(j, j + 3) !== quote.repeat(3)) j++;
        j = Math.min(j + 3, line.length);
      } else {
        while (j < line.length && line[j] !== quote) {
          if (line[j] === "\\" && j + 1 < line.length) j += 2;
          else j++;
        }
        if (j < line.length) j++;
      }
      tokens.push(`<span class="hl-str">${escapeHtml(line.slice(i, j))}</span>`);
      i = j;
      continue;
    }

    // 數字
    if (/[0-9]/.test(ch) && (i === 0 || !/[A-Za-z_]/.test(line[i - 1]))) {
      let j = i;
      while (j < line.length && /[0-9_.eE+\-xXoObB]/.test(line[j])) j++;
      tokens.push(`<span class="hl-num">${escapeHtml(line.slice(i, j))}</span>`);
      i = j;
      continue;
    }

    // 識別字
    if (/[A-Za-z_]/.test(ch)) {
      let j = i;
      while (j < line.length && /[A-Za-z0-9_]/.test(line[j])) j++;
      const word = line.slice(i, j);
      if (PY_KEYWORDS.has(word)) {
        tokens.push(`<span class="hl-kw">${escapeHtml(word)}</span>`);
      } else if (PY_BUILTINS.has(word)) {
        tokens.push(`<span class="hl-bi">${escapeHtml(word)}</span>`);
      } else if (line[j] === "(") {
        tokens.push(`<span class="hl-fn">${escapeHtml(word)}</span>`);
      } else {
        tokens.push(escapeHtml(word));
      }
      i = j;
      continue;
    }

    // 裝飾子 @decorator
    if (ch === "@") {
      let j = i + 1;
      while (j < line.length && /[A-Za-z0-9_.]/.test(line[j])) j++;
      tokens.push(`<span class="hl-dec">${escapeHtml(line.slice(i, j))}</span>`);
      i = j;
      continue;
    }

    tokens.push(escapeHtml(ch));
    i++;
  }
  return tokens.join("");
}

export function PythonModal({ code, bundleFiles, onClose }: PythonModalProps) {
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

  const downloadBundle = () => {
    for (const file of bundleFiles) {
      const blob = new Blob([file.content], { type: file.mime });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = file.path;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    }
  };

  return (
    <div className="modal-backdrop" onClick={onClose}>
      <div className="deploy-modal" onClick={(e) => e.stopPropagation()}>
        <button className="deploy-close" onClick={onClose} aria-label="關閉">×</button>

        <div className="deploy-icon">⬇</div>
        <h2 className="deploy-title">部署到 Python 環境</h2>
        <p className="deploy-subtitle">
          下載 bundle 檔案或複製 Python 主程式，即可在本地 Python 環境執行此工作流。
        </p>

        <div className="deploy-file-list">
          {bundleFiles.map((file) => (
            <code key={file.path}>{file.path}</code>
          ))}
        </div>

        <div className="deploy-code-card">
          <div className="deploy-code-lang">python</div>
          <button className="deploy-code-copy" onClick={handleCopy} aria-label="複製">
            {copied ? "✓" : "⧉"}
          </button>
          <pre id="python-code-pre" className="deploy-code">
            <code
              className="hl-python"
              dangerouslySetInnerHTML={{ __html: highlightPython(code) }}
            />
          </pre>
        </div>

        <div className="deploy-notice">
          <span className="deploy-notice-icon">⚠</span>
          <span>請確認 <code>.env</code> 已設定模型對應的 API 金鑰與端點。</span>
        </div>

        <div className="deploy-actions">
          <button className="deploy-primary" onClick={downloadBundle}>下載 Bundle 檔案</button>
          <button className="deploy-secondary" onClick={handleCopy}>
            {copied ? "已複製到剪貼簿" : "複製主程式"}
          </button>
        </div>
      </div>
    </div>
  );
}
