import { setHighlightedCode } from "../shared/code-highlight.js";
import { enhanceCodeBlocks } from "../shared/code-block-controls.js";

export function bindCodePreview(toggles, modal) {
  if (!modal || !toggles.length) {
    return;
  }
  const code = modal.querySelector("[data-code-preview-content]");
  const closeButtons = modal.querySelectorAll("[data-code-preview-close]");
  const closeButton = modal.querySelector(".code-preview-window [data-code-preview-close]");
  let lastToggle = null;

  async function open(event) {
    event.preventDefault();
    lastToggle = event.currentTarget;
    modal.hidden = false;
    modal.classList.add("open");
    modal.dataset.open = "true";
    code?.replaceChildren();
    closeButton?.focus();
    try {
      const response = await fetch("/playground/source/preview", { cache: "no-store" });
      if (!response.ok) {
        throw new Error(`source preview failed with ${response.status}`);
      }
      if (code) {
        renderPreviewMarkdown(code, await response.text());
        enhanceCodeBlocks(code);
      }
    } catch (error) {
      if (code) {
        const paragraph = document.createElement("p");
        paragraph.textContent = "程式碼載入失敗，請關閉後重新預覽。";
        code.replaceChildren(paragraph);
      }
    }
  }

  function close() {
    modal.hidden = true;
    modal.classList.remove("open");
    modal.dataset.open = "false";
    lastToggle?.focus();
  }

  toggles.forEach((toggle) => toggle.addEventListener("click", open));
  closeButtons.forEach((button) => button.addEventListener("click", close));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal.hidden) {
      close();
    }
  });
}

function renderPreviewMarkdown(element, markdown) {
  element.replaceChildren();
  const lines = String(markdown || "").split(/\r?\n/);
  let index = 0;
  while (index < lines.length) {
    const line = lines[index];
    if (!line.trim()) {
      index += 1;
      continue;
    }
    if (line.startsWith("```")) {
      const language = line.slice(3).trim().toLowerCase();
      const codeLines = [];
      index += 1;
      while (index < lines.length && !lines[index].startsWith("```")) {
        codeLines.push(lines[index]);
        index += 1;
      }
      index += 1;
      element.append(createCodeBlock(codeLines.join("\n"), language));
      continue;
    }
    if (line.startsWith("## ")) {
      const heading = document.createElement("h3");
      heading.textContent = line.slice(3).trim();
      element.append(heading);
      index += 1;
      continue;
    }
    if (/^\d+\.\s+/.test(line)) {
      const list = document.createElement("ol");
      const firstNumber = line.match(/^(\d+)\.\s+/);
      if (firstNumber) {
        list.start = Number(firstNumber[1]);
      }
      while (index < lines.length && /^\d+\.\s+/.test(lines[index])) {
        const item = document.createElement("li");
        item.textContent = lines[index].replace(/^\d+\.\s+/, "");
        list.append(item);
        index += 1;
      }
      element.append(list);
      continue;
    }
    const paragraph = document.createElement("p");
    paragraph.textContent = line.trim();
    element.append(paragraph);
    index += 1;
  }
}

function createCodeBlock(source, language) {
  const block = document.createElement("pre");
  const code = document.createElement("code");
  if (language) {
    code.className = `language-${language}`;
  }
  code.dataset.source = source;
  setHighlightedCode(code, source, language);
  block.append(code);
  return block;
}