import { setHighlightedCode } from "../shared/code-highlight.js";
import { enhanceCodeBlocks } from "../shared/code-block-controls.js";

export function bindCodePreview(toggles, modal) {
  if (!modal || !toggles.length) {
    return;
  }
  const code = modal.querySelector("[data-code-preview-content]");
  const closeButtons = modal.querySelectorAll("[data-code-preview-close]");
  const closeButton = modal.querySelector(".code-preview-window [data-code-preview-close]");
  const scrollbar = modal.querySelector("[data-code-preview-scrollbar]");
  const scrollbarThumb = modal.querySelector("[data-code-preview-scrollbar-thumb]");
  let lastToggle = null;
  const customScrollbar = bindCustomScrollbar(code, scrollbar, scrollbarThumb);

  async function open(event, toggle) {
    event.preventDefault();
    lastToggle = toggle;
    modal.hidden = false;
    modal.classList.add("open");
    modal.dataset.open = "true";
    if (code) {
      const loading = document.createElement("p");
      loading.textContent = "正在載入程式碼...";
      code.replaceChildren(loading);
    }
    closeButton?.focus();
    const controller = new AbortController();
    const timeoutId = window.setTimeout(() => controller.abort(), 15000);
    try {
      const response = await fetch("/playground/source/preview", { cache: "no-store", signal: controller.signal });
      if (!response.ok) {
        throw new Error(`source preview failed with ${response.status}`);
      }
      if (code) {
        renderPreviewMarkdown(code, await response.text());
        enhanceCodeBlocks(code);
        customScrollbar.update();
      }
    } catch (error) {
      if (code) {
        const paragraph = document.createElement("p");
        paragraph.textContent = error.name === "AbortError" ? "程式碼載入逾時，請關閉後重新預覽。" : "程式碼載入失敗，請關閉後重新預覽。";
        code.replaceChildren(paragraph);
      }
    } finally {
      window.clearTimeout(timeoutId);
    }
  }

  function close() {
    modal.hidden = true;
    modal.classList.remove("open");
    modal.dataset.open = "false";
    customScrollbar.reset();
    lastToggle?.focus();
  }

  document.addEventListener("click", (event) => {
    const toggle = event.target.closest?.("[data-code-preview-open]");
    if (toggle && toggles instanceof NodeList && Array.from(toggles).includes(toggle)) {
      open(event, toggle);
    }
  });
  closeButtons.forEach((button) => button.addEventListener("click", close));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal.hidden) {
      close();
    }
  });
}

function bindCustomScrollbar(scroller, rail, thumb) {
  if (!scroller || !rail || !thumb) {
    return { update() {}, reset() {} };
  }

  let dragging = false;
  let dragStartY = 0;
  let scrollStartTop = 0;
  let resizeObserver = null;
  let mutationObserver = null;

  function scheduleUpdate() {
    window.requestAnimationFrame(update);
    window.setTimeout(update, 80);
    window.setTimeout(update, 240);
  }

  function updateRailBounds() {
    rail.style.removeProperty("top");
    rail.style.removeProperty("height");
  }

  function update() {
    updateRailBounds();
    const maxScroll = scroller.scrollHeight - scroller.clientHeight;
    if (maxScroll <= 1) {
      rail.classList.remove("is-visible");
      rail.getAnimations().forEach((animation) => animation.cancel());
      rail.style.opacity = "0";
      thumb.style.height = "0px";
      thumb.style.transform = "translateY(0)";
      return;
    }

    rail.classList.add("is-visible");
    rail.getAnimations().forEach((animation) => animation.cancel());
    rail.style.opacity = "1";
    const railHeight = rail.clientHeight;
    const thumbHeight = Math.max(36, Math.round((scroller.clientHeight / scroller.scrollHeight) * railHeight));
    const travel = Math.max(0, railHeight - thumbHeight);
    const top = Math.round((scroller.scrollTop / maxScroll) * travel);
    thumb.style.height = `${thumbHeight}px`;
    thumb.style.transform = `translateY(${top}px)`;
  }

  function scrollFromPointer(clientY) {
    const railHeight = rail.clientHeight;
    const thumbHeight = thumb.getBoundingClientRect().height;
    const travel = Math.max(1, railHeight - thumbHeight);
    const pointerDelta = clientY - dragStartY;
    const scrollRatio = (scrollStartTop + pointerDelta) / travel;
    scroller.scrollTop = scrollRatio * (scroller.scrollHeight - scroller.clientHeight);
    update();
  }

  function startDrag(clientY) {
    dragging = true;
    thumb.classList.add("is-dragging");
    dragStartY = clientY;
    const matrix = new DOMMatrixReadOnly(getComputedStyle(thumb).transform);
    scrollStartTop = Number.isFinite(matrix.m42) ? matrix.m42 : 0;
  }

  function stopDrag() {
    dragging = false;
    thumb.classList.remove("is-dragging");
  }

  thumb.addEventListener("pointerdown", (event) => {
    startDrag(event.clientY);
    thumb.setPointerCapture(event.pointerId);
    event.preventDefault();
  });

  thumb.addEventListener("pointermove", (event) => {
    if (!dragging) {
      return;
    }
    scrollFromPointer(event.clientY);
  });

  thumb.addEventListener("pointerup", (event) => {
    stopDrag();
    thumb.releasePointerCapture(event.pointerId);
  });

  thumb.addEventListener("pointercancel", () => {
    stopDrag();
  });

  thumb.addEventListener("mousedown", (event) => {
    startDrag(event.clientY);
    event.preventDefault();
  });

  thumb.onmousedown = (event) => {
    startDrag(event.clientY);
    event.preventDefault();
  };

  rail.addEventListener("pointerdown", (event) => {
    startDrag(event.clientY);
    event.preventDefault();
  });

  rail.addEventListener("mousedown", (event) => {
    startDrag(event.clientY);
    event.preventDefault();
  });

  window.addEventListener("mousemove", (event) => {
    if (!dragging) {
      return;
    }
    scrollFromPointer(event.clientY);
  });

  document.addEventListener("mousemove", (event) => {
    if (!dragging) {
      return;
    }
    scrollFromPointer(event.clientY);
  });

  window.addEventListener("mouseup", () => {
    if (!dragging) {
      return;
    }
    stopDrag();
  });

  document.addEventListener("mouseup", () => {
    if (!dragging) {
      return;
    }
    stopDrag();
  });

  scroller.addEventListener("scroll", update, { passive: true });
  scroller.onscroll = update;
  window.addEventListener("resize", update);
  if ("ResizeObserver" in window) {
    resizeObserver = new ResizeObserver(update);
    resizeObserver.observe(scroller);
  }
  if ("MutationObserver" in window) {
    mutationObserver = new MutationObserver(scheduleUpdate);
    mutationObserver.observe(scroller, { childList: true, subtree: true });
  }

  return {
    update() {
      scheduleUpdate();
    },
    reset() {
      dragging = false;
      thumb.classList.remove("is-dragging");
      rail.classList.remove("is-visible");
      rail.getAnimations().forEach((animation) => animation.cancel());
      rail.style.opacity = "0";
      scroller.scrollTop = 0;
    },
    disconnect() {
      resizeObserver?.disconnect();
      mutationObserver?.disconnect();
    },
  };
}

function renderPreviewMarkdown(element, markdown) {
  element.replaceChildren();
  const lines = String(markdown || "").split(/\r?\n/);
  let index = 0;
  let featureIndex = 0;
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
      const feature = document.createElement("section");
      feature.className = "code-preview-feature";
      feature.dataset.feature = String(featureIndex);
      const icon = document.createElement("span");
      icon.className = "code-preview-feature-icon";
      icon.setAttribute("aria-hidden", "true");
      const heading = document.createElement("h3");
      heading.textContent = line.slice(3).trim();
      feature.append(icon, heading);
      element.append(feature);
      featureIndex += 1;
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
    paragraph.append(...renderInlineText(line.trim()));
    element.append(paragraph);
    index += 1;
  }
}

function renderInlineText(text) {
  const parts = String(text || "").split(/(\*\*[^*]+\*\*)/g).filter(Boolean);
  return parts.map((part) => {
    if (part.startsWith("**") && part.endsWith("**")) {
      const highlight = document.createElement("strong");
      highlight.textContent = part.slice(2, -2);
      return highlight;
    }
    return document.createTextNode(part);
  });
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