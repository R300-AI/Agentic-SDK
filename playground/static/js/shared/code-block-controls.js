import { setHighlightedCode } from "./code-highlight.js";

export function enhanceCodeBlocks(root = document) {
  root.querySelectorAll("pre > code.language-python, pre > code.language-bash").forEach((code) => {
    const pre = code.parentElement;
    if (!pre || pre.dataset.codeControlsReady === "true") {
      return;
    }
    const language = code.classList.contains("language-python") ? "python" : "bash";
    const source = code.dataset.source || code.textContent || "";
    code.dataset.source = source;
    setHighlightedCode(code, source, language, { foldLongStrings: language === "python" });
    pre.dataset.codeControlsReady = "true";
    pre.classList.add("code-block-with-controls");
    pre.prepend(createCopyButton(source));
  });
}

function createCopyButton(source) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "code-copy-button";
  button.textContent = "⧉";
  button.setAttribute("aria-label", "複製完整程式碼");
  button.title = "複製完整程式碼";
  button.addEventListener("click", async () => {
    try {
      await copyText(source);
      button.dataset.copied = "true";
      button.textContent = "✓";
      window.setTimeout(() => {
        button.dataset.copied = "false";
        button.textContent = "⧉";
      }, 1400);
    } catch {
      button.dataset.copied = "false";
      button.textContent = "複製失敗";
    }
  });
  return button;
}

async function copyText(text) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement("textarea");
  textarea.value = text;
  textarea.setAttribute("readonly", "");
  textarea.style.position = "fixed";
  textarea.style.top = "-1000px";
  document.body.append(textarea);
  textarea.select();
  const copied = document.execCommand("copy");
  textarea.remove();
  if (!copied) {
    throw new Error("copy command failed");
  }
}