export function setResultMessage(element, message) {
  if (element) {
    renderMarkdown(element, message || "");
  }
}

export function setToolCallPanels(element, panels) {
  if (!element) {
    return;
  }
  const normalizedPanels = normalizeToolCallPanels(panels);
  element.replaceChildren();
  element.hidden = normalizedPanels.length === 0;
  if (!normalizedPanels.length) {
    return;
  }
  normalizedPanels.forEach((panel) => element.append(createToolCallPanel(panel)));
}

export function setProcessSummary(element, events) {
  if (!element) {
    return;
  }
  const processEvents = normalizeProcessEvents(events);
  element.replaceChildren();
  element.hidden = processEvents.length === 0;
  if (!processEvents.length) {
    return;
  }

  const summaryRoot = document.createElement("details");
  summaryRoot.className = "process-summary";
  summaryRoot.open = true;
  summaryRoot.dataset.processSummary = "";

  const summaryLabel = document.createElement("summary");
  summaryLabel.className = "process-summary-title";
  const titleText = document.createElement("span");
  titleText.textContent = "推論過程";
  const titleChevron = document.createElement("span");
  titleChevron.className = "process-summary-chevron";
  titleChevron.setAttribute("aria-hidden", "true");
  titleChevron.textContent = ">";
  summaryLabel.append(titleText, titleChevron);

  const list = document.createElement("div");
  list.className = "process-summary-list";
  processEvents.forEach((event) => list.append(createProcessSummaryItem(event)));

  summaryRoot.append(summaryLabel, list);
  element.append(summaryRoot);
}

export function clearProcessEvents(element) {
  if (!element) {
    return;
  }
  element.replaceChildren();
  element._processEvents = [];
  element.hidden = true;
}

export function setProcessEvents(element, events, { active = false, collapsible = false, latestOnly = false, preserveOpen = false, onUpdate } = {}) {
  if (!element) {
    return;
  }
  const processEvents = normalizeProcessEvents(events);
  const wasOpen = preserveOpen && element.querySelector(".process-trace-disclosure")?.open;
  clearProcessEvents(element);
  if (!processEvents.length) {
    return;
  }
  element._processEvents = processEvents;
  element.hidden = false;
  if (collapsible) {
    element.append(createProcessTraceDisclosure(processEvents, { active, latestOnly, open: wasOpen }));
  } else {
    element.append(...processEvents.map(createProcessEvent));
  }
  onUpdate?.();
}

export async function streamProcessEvents(element, events, { onUpdate } = {}) {
  if (!element) {
    return;
  }
  const processEvents = normalizeProcessEvents(events);
  clearProcessEvents(element);
  if (!processEvents.length) {
    return;
  }
  element.hidden = false;
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
    element.append(...processEvents.map(createProcessEvent));
    onUpdate?.();
    return;
  }
  for (const event of processEvents) {
    element.append(createProcessEvent(event));
    onUpdate?.();
    await wait(180);
  }
}

export function showLiveProcessEvent(element, event, { onUpdate } = {}) {
  if (!element) {
    return;
  }
  const processEvent = normalizeProcessEvents([event])[0];
  if (!processEvent) {
    return;
  }
  const processEvents = [...(Array.isArray(element._processEvents) ? element._processEvents : []), processEvent];
  setProcessEvents(element, processEvents, {
    active: true,
    collapsible: true,
    latestOnly: true,
    preserveOpen: true,
  });
  onUpdate?.();
}

export async function streamResultMarkdown(element, message, { onUpdate } = {}) {
  if (!element) {
    return;
  }
  const content = String(message || "");
  if (!content) {
    element.replaceChildren();
    return;
  }
  if (window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
    renderMarkdown(element, content);
    onUpdate?.();
    return;
  }
  const chunks = streamChunks(content);
  let rendered = "";
  for (const chunk of chunks) {
    rendered += chunk;
    renderMarkdown(element, rendered);
    onUpdate?.();
    await wait(streamDelayFor(chunk));
  }
}

const TOOL_CALL_PANEL_CLASS_BY_TYPE = {
  string: "tool-call-panel-string",
  number: "tool-call-panel-number",
  boolean: "tool-call-panel-boolean",
};

export function renderMarkdown(element, markdown) {
  if (!element) {
    return;
  }
  element.innerHTML = markdownToHtml(String(markdown || ""));
}

function streamChunks(content) {
  const chunks = [];
  let index = 0;
  while (index < content.length) {
    const remaining = content.length - index;
    const size = remaining < 12 ? remaining : Math.min(24, Math.max(8, nextBreakDistance(content, index)));
    chunks.push(content.slice(index, index + size));
    index += size;
  }
  return chunks;
}

function nextBreakDistance(content, start) {
  const windowText = content.slice(start, start + 24);
  const breakIndex = windowText.search(/[\s，。；、,.!?！？\n]/);
  return breakIndex >= 7 ? breakIndex + 1 : 12;
}

function streamDelayFor(chunk) {
  if (chunk.includes("\n")) {
    return 90;
  }
  if (/[。.!?！？]$/.test(chunk.trim())) {
    return 110;
  }
  return 28;
}

function wait(milliseconds) {
  return new Promise((resolve) => window.setTimeout(resolve, milliseconds));
}

function normalizeProcessEvents(events) {
  if (!Array.isArray(events)) {
    return [];
  }
  return events
    .map((event) => ({
      title: String(event?.title || "").trim(),
      description: String(event?.description || "").trim(),
    }))
    .filter((event) => event.title || event.description);
}

function normalizeToolCallPanels(panels) {
  if (!Array.isArray(panels)) {
    return [];
  }
  return panels
    .map((panel, index) => ({
      id: String(panel?.id || `tool_call_${index + 1}`),
      functionName: String(panel?.function_name || `tool_call_${index + 1}`),
      title: String(panel?.title || panel?.function_name || "工具呼叫").trim(),
      description: String(panel?.description || "").trim(),
      api: normalizeToolCallApi(panel?.api),
      fields: normalizeToolCallFields(panel?.fields),
    }))
    .filter((panel) => panel.fields.length);
}

function normalizeToolCallApi(api) {
  if (!api || typeof api !== "object") {
    return null;
  }
  const url = String(api.url || "").trim();
  if (!url) {
    return null;
  }
  return {
    method: String(api.method || "POST").toUpperCase(),
    url,
  };
}

function normalizeToolCallFields(fields) {
  if (!Array.isArray(fields)) {
    return [];
  }
  return fields.map((field) => {
    const type = normalizeToolCallFieldType(field?.type || field?.panel_type);
    return {
      name: String(field?.name || "field"),
      label: String(field?.label || field?.name || "欄位"),
      type,
      description: String(field?.description || ""),
      required: Boolean(field?.required),
      value: field?.value,
      choices: normalizeToolCallChoices(field?.choices),
    };
  });
}

function normalizeToolCallChoices(choices) {
  if (!Array.isArray(choices)) {
    return [];
  }
  return choices
    .map((choice) => ({
      value: choice?.value,
      label: String(choice?.label || "").trim(),
      description: String(choice?.description || "").trim(),
    }))
    .filter((choice) => choice.label);
}

function normalizeToolCallFieldType(rawType) {
  const value = String(rawType || "").toLowerCase();
  if (value.includes("number") || value.includes("integer")) {
    return "number";
  }
  if (value.includes("boolean")) {
    return "boolean";
  }
  return "string";
}

function createToolCallPanel(panel) {
  const form = document.createElement("form");
  form.className = "tool-call-card";
  form.dataset.toolCallForm = panel.id;
  form.dataset.toolCallFunction = panel.functionName;

  const header = document.createElement("header");
  header.className = "tool-call-card-header";
  const label = document.createElement("span");
  label.className = "eyebrow";
  label.textContent = "需要你選擇";
  const title = document.createElement("h3");
  title.textContent = panel.title || "下一步方向";
  header.append(label, title);

  if (panel.description && panel.description !== panel.title) {
    const description = document.createElement("p");
    description.className = "tool-call-description";
    description.textContent = panel.description;
    header.append(description);
  }

  const fieldList = document.createElement("div");
  fieldList.className = "tool-call-fields";
  panel.fields.forEach((field) => fieldList.append(createToolCallFieldPanel(field)));

  const status = document.createElement("p");
  status.className = "tool-call-status";
  status.textContent = "請選擇後送出。";

  const actions = document.createElement("div");
  actions.className = "tool-call-actions";
  const confirmButton = document.createElement("button");
  confirmButton.className = "button button-secondary";
  confirmButton.type = "submit";
  confirmButton.textContent = "送出選擇";
  actions.append(confirmButton, status);

  form.append(header, fieldList, actions);
  form.addEventListener("input", () => {
    status.textContent = "選擇已更新，尚未送出。";
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const argumentsPayload = collectToolCallPayload(form);
    form.dataset.toolCallPayload = JSON.stringify(argumentsPayload);
    status.textContent = "正在送出選擇...";
    confirmButton.disabled = true;
    form.dispatchEvent(new CustomEvent("runner:tool-call-submit", {
      bubbles: true,
      detail: {
        id: panel.id,
        function_name: panel.functionName,
        arguments: argumentsPayload,
        api: panel.api,
      },
    }));
  });
  form.addEventListener("runner:tool-call-complete", () => {
    status.textContent = "已送出選擇。";
    confirmButton.disabled = false;
  });
  return form;
}

function createToolCallFieldPanel(field) {
  const panel = document.createElement("section");
  panel.className = `tool-call-panel ${TOOL_CALL_PANEL_CLASS_BY_TYPE[field.type] || TOOL_CALL_PANEL_CLASS_BY_TYPE.string}`;

  const label = document.createElement("label");
  label.className = "tool-call-field-label";
  const name = document.createElement("span");
  name.textContent = field.required ? `${field.label} *` : field.label;
  const hint = document.createElement("small");
  hint.textContent = field.description || dataTypeLabel(field.type);

  const control = createToolCallControl(field);
  label.append(name, hint, control);
  panel.append(label);
  return panel;
}

function createToolCallControl(field) {
  if (field.type === "boolean") {
    const wrapper = document.createElement("div");
    wrapper.className = "tool-call-choice-list";
    const booleanValue = field.value === true || String(field.value).toLowerCase() === "true";
    const choices = field.choices.length ? field.choices : [
      { value: true, label: "是", description: "" },
      { value: false, label: "否", description: "" },
    ];
    choices.forEach((choice) => {
      const value = choice.value === true || String(choice.value).toLowerCase() === "true";
      wrapper.append(createBooleanChoice(field, value, choice.label, value ? booleanValue : !booleanValue, choice.description));
    });
    return wrapper;
  }
  const input = document.createElement("input");
  input.name = field.name;
  input.dataset.toolCallType = field.type;
  input.type = field.type === "number" ? "number" : "text";
  input.value = field.value == null ? "" : String(field.value);
  return input;
}

function createBooleanChoice(field, value, labelText, checked, descriptionText = "") {
  const label = document.createElement("label");
  label.className = "tool-call-choice";
  const input = document.createElement("input");
  input.type = "radio";
  input.name = field.name;
  input.value = value ? "true" : "false";
  input.dataset.toolCallType = field.type;
  input.checked = checked;
  const text = document.createElement("span");
  text.textContent = labelText;
  label.append(input, text);
  if (descriptionText) {
    const description = document.createElement("small");
    description.textContent = descriptionText;
    label.append(description);
  }
  return label;
}

function dataTypeLabel(type) {
  if (type === "number") {
    return "數字資料";
  }
  if (type === "boolean") {
    return "是/否確認";
  }
  return "文字選項";
}

function collectToolCallPayload(form) {
  const payload = {};
  form.querySelectorAll("[data-tool-call-type]").forEach((control) => {
    const name = control.getAttribute("name");
    const type = control.dataset.toolCallType;
    if (!name) {
      return;
    }
    if (type === "boolean") {
      if (control.type === "radio" && !control.checked) {
        return;
      }
      payload[name] = control.value === "true" || (control.type !== "radio" && Boolean(control.checked));
    } else if (type === "number") {
      payload[name] = control.value === "" ? null : Number(control.value);
    } else {
      payload[name] = control.value;
    }
  });
  return payload;
}

function createProcessEvent(event, { active = false } = {}) {
  const item = document.createElement("section");
  item.className = "process-event";
  if (active) {
    item.classList.add("is-active");
  }

  const mark = document.createElement("span");
  mark.className = "process-event-mark";
  mark.setAttribute("aria-hidden", "true");

  const title = document.createElement("div");
  title.className = "process-event-title";
  const titleText = document.createElement("span");
  titleText.textContent = event.title || "處理中";
  const chevron = document.createElement("span");
  chevron.className = "process-chevron";
  chevron.setAttribute("aria-hidden", "true");
  chevron.textContent = ">";
  title.append(titleText, chevron);

  const description = document.createElement("p");
  description.className = "process-event-detail";
  description.textContent = event.description || "正在整理這一步的處理結果。";

  item.append(mark, title, description);
  return item;
}

function createProcessTraceDisclosure(events, { active = false, latestOnly = false, open = false } = {}) {
  const root = document.createElement("details");
  root.className = "process-trace-disclosure";
  root.open = Boolean(open);
  if (active) {
    root.classList.add("is-active");
  }

  const summary = document.createElement("summary");
  summary.className = "process-trace-toggle";

  const labelRow = document.createElement("span");
  labelRow.className = "process-trace-label-row";
  const summaryEvents = latestOnly ? events.slice(-1) : events;
  const latestEvent = summaryEvents[summaryEvents.length - 1];
  const label = document.createElement("span");
  label.className = "process-trace-label";
  label.textContent = latestEvent?.title || "處理步驟";
  const description = document.createElement("span");
  description.className = "process-trace-description";
  description.textContent = latestEvent?.description || "正在整理這一步的處理結果。";
  labelRow.append(label, description);

  const chevron = document.createElement("span");
  chevron.className = "process-trace-toggle-chevron";
  chevron.setAttribute("aria-hidden", "true");
  chevron.textContent = root.open ? "v" : ">";
  summary.append(labelRow, chevron);

  const list = document.createElement("div");
  list.className = "process-trace-list";
  events.forEach((event) => list.append(createProcessEvent(event)));

  root.addEventListener("toggle", () => {
    chevron.textContent = root.open ? "v" : ">";
  });
  root.append(summary, list);
  return root;
}

function createProcessSummaryItem(event) {
  const item = document.createElement("details");
  item.className = "process-summary-item";

  const summary = document.createElement("summary");
  summary.className = "process-summary-name";
  const name = document.createElement("span");
  name.textContent = event.title || "處理步驟";
  const chevron = document.createElement("span");
  chevron.className = "process-summary-chevron";
  chevron.setAttribute("aria-hidden", "true");
  chevron.textContent = ">";
  summary.append(name, chevron);

  const description = document.createElement("p");
  description.className = "process-summary-description";
  description.textContent = event.description || "這一步沒有額外敘述。";

  item.append(summary, description);
  return item;
}

function markdownToHtml(markdown) {
  const blocks = [];
  const fencePattern = /```([^\n`]*)\n([\s\S]*?)```/g;
  let cursor = 0;
  let match;
  while ((match = fencePattern.exec(markdown)) !== null) {
    blocks.push(renderBlocks(markdown.slice(cursor, match.index)));
    blocks.push(renderCodeBlock(match[2], match[1]));
    cursor = match.index + match[0].length;
  }
  blocks.push(renderBlocks(markdown.slice(cursor)));
  return blocks.join("");
}

function renderBlocks(markdown) {
  const lines = markdown.replace(/\r\n/g, "\n").split("\n");
  const html = [];
  let paragraph = [];
  let listItems = [];
  let ordered = false;
  let quoteLines = [];

  const flushParagraph = () => {
    if (paragraph.length) {
      html.push(`<p>${renderInline(paragraph.join(" "))}</p>`);
      paragraph = [];
    }
  };
  const flushList = () => {
    if (listItems.length) {
      const tag = ordered ? "ol" : "ul";
      html.push(`<${tag}>${listItems.map((item) => `<li>${renderInline(item)}</li>`).join("")}</${tag}>`);
      listItems = [];
    }
  };
  const flushQuote = () => {
    if (quoteLines.length) {
      html.push(`<blockquote>${quoteLines.map((line) => `<p>${renderInline(line)}</p>`).join("")}</blockquote>`);
      quoteLines = [];
    }
  };

  for (const line of lines) {
    const trimmed = line.trim();
    if (!trimmed) {
      flushParagraph();
      flushList();
      flushQuote();
      continue;
    }
    const heading = /^(#{1,3})\s+(.+)$/.exec(trimmed);
    if (heading) {
      flushParagraph();
      flushList();
      flushQuote();
      const level = heading[1].length + 2;
      html.push(`<h${level}>${renderInline(heading[2])}</h${level}>`);
      continue;
    }
    const bullet = /^[-*]\s+(.+)$/.exec(trimmed);
    const numbered = /^\d+[.)]\s+(.+)$/.exec(trimmed);
    if (bullet || numbered) {
      flushParagraph();
      flushQuote();
      const isOrdered = Boolean(numbered);
      if (listItems.length && ordered !== isOrdered) {
        flushList();
      }
      ordered = isOrdered;
      listItems.push((bullet || numbered)[1]);
      continue;
    }
    const quote = /^>\s?(.+)$/.exec(trimmed);
    if (quote) {
      flushParagraph();
      flushList();
      quoteLines.push(quote[1]);
      continue;
    }
    flushList();
    flushQuote();
    paragraph.push(trimmed);
  }
  flushParagraph();
  flushList();
  flushQuote();
  return html.join("");
}

function renderCodeBlock(code, language) {
  const languageClass = String(language || "").trim().replace(/[^a-z0-9_-]/gi, "");
  const className = languageClass ? ` class="language-${languageClass}"` : "";
  return `<pre><code${className}>${escapeHtml(code.replace(/\n$/, ""))}</code></pre>`;
}

function renderInline(text) {
  const inlineSnippets = [];
  let protectedText = String(text).replace(/`([^`]+)`/g, (_, code) => {
    const token = `@@INLINE_${inlineSnippets.length}@@`;
    inlineSnippets.push(`<code>${escapeHtml(code)}</code>`);
    return token;
  });
  protectedText = protectedText.replace(/\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)/g, (_, label, url) => {
    const token = `@@INLINE_${inlineSnippets.length}@@`;
    inlineSnippets.push(`<a href="${escapeAttribute(url)}" target="_blank" rel="noreferrer noopener">${applyInlineFormatting(escapeHtml(label))}</a>`);
    return token;
  });
  protectedText = applyInlineFormatting(escapeHtml(protectedText));
  inlineSnippets.forEach((snippet, index) => {
    protectedText = protectedText.replace(`@@INLINE_${index}@@`, snippet);
  });
  return protectedText;
}

function applyInlineFormatting(escapedText) {
  return String(escapedText)
    .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/__([^_]+)__/g, "<strong>$1</strong>")
    .replace(/(^|\s)\*([^*]+)\*(?=\s|$|[，。,.!?！？])/g, "$1<em>$2</em>")
    .replace(/(^|\s)_([^_]+)_(?=\s|$|[，。,.!?！？])/g, "$1<em>$2</em>");
}

function escapeHtml(value) {
  return String(value)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#39;");
}

function escapeAttribute(value) {
  return escapeHtml(value).replace(/`/g, "&#96;");
}

export function setResultTitle(element, title) {
  if (element && title) {
    element.textContent = title;
  }
}

export function showResultSurface(element) {
  if (element) {
    element.hidden = false;
  }
}

export function setTrustEvidence(list, evidence) {
  if (!list || !Array.isArray(evidence)) {
    return;
  }
  list.replaceChildren(
    ...evidence.map((entry) => {
      const item = document.createElement("li");
      item.textContent = entry;
      return item;
    }),
  );
}