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
  const previousEvents = Array.isArray(element._processEvents) ? element._processEvents : [];
  const processEvents = mergeProcessVisits([...previousEvents, processEvent]);
  const root = element.querySelector(".process-trace-disclosure");
  if (!root) {
    element.replaceChildren(createProcessTraceDisclosure(processEvents, { active: true, latestOnly: true }));
    element.hidden = false;
    element._processEvents = processEvents;
    onUpdate?.();
    return;
  }

  element._processEvents = processEvents;
  element.hidden = false;
  updateLiveProcessTrace(root, processEvent, processEvents);
  onUpdate?.();
}

function updateLiveProcessTrace(root, currentEvent, processEvents) {
  root.classList.add("is-active");
  const label = root.querySelector(".process-trace-label");
  const description = root.querySelector(".process-trace-description");
  if (label) {
    label.textContent = currentEvent.title || "處理步驟";
  }
  if (description) {
    description.textContent = currentEvent.description || "正在整理這一步的處理結果。";
  }

  const list = root.querySelector(".process-trace-list");
  if (!list) {
    return;
  }
  renderProcessTraceHistory(list, processEvents);
}

function renderProcessTraceHistory(list, events) {
  list.replaceChildren(...events.slice(0, -1).map(createProcessEvent));
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
  const streamedContent = content.slice(0, 960);
  const chunks = streamChunks(streamedContent);
  let rendered = "";
  for (const chunk of chunks) {
    rendered += chunk;
    renderMarkdown(element, rendered);
    onUpdate?.();
    await wait(streamDelayFor(chunk));
  }
  if (streamedContent.length < content.length) {
    renderMarkdown(element, content);
    onUpdate?.();
  }
}

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
  const normalized = events
    .map((event) => ({
      role: String(event?.role || "").trim(),
      module: String(event?.module || event?.role || "").trim(),
      visitId: String(event?.visit_id || "").trim(),
      visitCount: Number.isFinite(Number(event?.visit_count)) ? Number(event.visit_count) : null,
      phase: String(event?.phase || "").trim(),
      status: String(event?.status || "").trim(),
      title: String(event?.title || "").trim(),
      description: processDisplayDescription(event),
      trackedFields: Array.isArray(event?.tracked_fields) ? event.tracked_fields.map((field) => String(field || "").trim()).filter(Boolean) : [],
      details: [],
    }))
    .filter((event) => event.title || event.description);
  return mergeProcessVisits(normalized);
}

function processDisplayDescription(event) {
  const title = String(event?.title || "").trim();
  const descriptions = {
    "理解輸入": "已整理本次問題。",
    "判斷工具順序": "正在決定需要的處理步驟。",
    "整理相關來源": "正在查找相關知識庫內容。",
    "準備輸出回覆": "正在整理回覆內容。",
    "檢查回覆": "已檢查回覆內容，可交付。",
  };
  if (descriptions[title]) {
    return descriptions[title];
  }
  if (title === "流程中止") {
    return String(event?.description || "").trim() || "流程已被安全限制中止。";
  }
  return "正在處理這個步驟。";
}

function normalizeProcessDetails(details) {
  if (!Array.isArray(details)) {
    return [];
  }
  return details
    .map((detail) => ({
      field: String(detail?.field || "").trim(),
      description: String(detail?.description || "").trim(),
    }))
    .filter((detail) => detail.field && detail.description);
}

function mergeProcessVisits(events) {
  const merged = [];
  const indexesByVisitId = new Map();
  events.forEach((event) => {
    if (!event.visitId || !indexesByVisitId.has(event.visitId)) {
      if (event.visitId) {
        indexesByVisitId.set(event.visitId, merged.length);
      }
      merged.push({ ...event, details: [...event.details] });
      return;
    }
    const index = indexesByVisitId.get(event.visitId);
    const current = merged[index];
    const detailIndexes = new Map(current.details.map((detail, detailIndex) => [detail.field, detailIndex]));
    event.details.forEach((detail) => {
      const detailIndex = detailIndexes.get(detail.field);
      if (detailIndex == null) {
        detailIndexes.set(detail.field, current.details.length);
        current.details.push(detail);
      } else {
        current.details[detailIndex] = detail;
      }
    });
    current.title = event.title || current.title;
    current.description = event.description || current.description;
    current.phase = event.phase || current.phase;
    current.status = event.status || current.status;
    current.trackedFields = event.trackedFields.length ? event.trackedFields : current.trackedFields;
  });
  return merged;
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
      review: String(panel?.review || "").trim(),
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
      customLabel: String(field?.custom_label || "自行填寫").trim() || "自行填寫",
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
  form.className = "tool-call-card interactive-followup";
  form.dataset.toolCallForm = panel.id;
  form.dataset.toolCallFunction = panel.functionName;

  const header = document.createElement("header");
  header.className = "tool-call-card-header";
  const title = document.createElement("h3");
  const titleId = `${panel.id}-title`;
  title.id = titleId;
  title.textContent = panel.title || "下一步方向";
  header.append(title);

  if (panel.description && panel.description !== panel.title) {
    const description = document.createElement("p");
    description.className = "tool-call-description";
    description.textContent = panel.description;
    header.append(description);
  }

  const review = createToolCallReview(panel.review);

  const fieldList = document.createElement("div");
  fieldList.className = "tool-call-fields";
  panel.fields.forEach((field, index) => fieldList.append(createToolCallFieldPanel(field, `${panel.id}-${index + 1}`)));

  const status = document.createElement("p");
  status.className = "tool-call-status";
  status.id = `${panel.id}-status`;
  status.setAttribute("aria-live", "polite");
  status.textContent = "請選擇後送出。";

  const actions = document.createElement("div");
  actions.className = "tool-call-actions";
  const confirmButton = document.createElement("button");
  confirmButton.className = "tool-call-submit";
  confirmButton.type = "submit";
  confirmButton.setAttribute("aria-describedby", status.id);
  confirmButton.textContent = "送出選擇";
  actions.append(confirmButton, status);

  form.append(header);
  if (review) {
    form.append(review);
  }
  form.append(fieldList, actions);
  form.addEventListener("input", () => {
    clearToolCallValidation(form);
  });
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (form.dataset.toolCallSubmitting === "true") {
      return;
    }
    const argumentsPayload = collectToolCallPayload(form);
    const missingRequiredFields = panel.fields.filter((field) => field.required && !hasToolCallValue(argumentsPayload[field.name]));
    if (missingRequiredFields.length) {
      setToolCallValidation(form, missingRequiredFields);
      status.textContent = `請先填寫：${missingRequiredFields.map((field) => field.label).join("、")}。`;
      return;
    }
    clearToolCallValidation(form);
    form.dataset.toolCallPayload = JSON.stringify(argumentsPayload);
    form.dataset.toolCallSubmitting = "true";
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
    delete form.dataset.toolCallSubmitting;
    const completion = document.createElement("p");
    completion.className = "tool-call-status tool-call-complete";
    completion.textContent = "已送出選擇";
    confirmButton.replaceWith(completion);
    status.remove();
  });
  return form;
}

function createToolCallReview(reviewText) {
  const text = String(reviewText || "").trim();
  if (!text) {
    return null;
  }
  const review = document.createElement("p");
  review.className = "tool-call-review";
  review.textContent = text;
  return review;
}

function createToolCallFieldPanel(field, fieldId) {
  const panel = document.createElement("section");
  panel.className = "tool-call-panel interactive-field";
  panel.dataset.toolCallField = field.name;

  const label = document.createElement("label");
  label.className = "tool-call-field-label";
  label.htmlFor = `${fieldId}-control`;
  const name = document.createElement("span");
  name.textContent = field.required ? `${field.label} *` : field.label;
  const control = createToolCallControl(field, fieldId, name);
  label.append(name);
  const hintText = String(field.description || "").trim();
  if (hintText) {
    const hint = document.createElement("small");
    hint.id = `${fieldId}-hint`;
    hint.textContent = hintText;
    label.append(hint);
  }
  label.append(control);
  const error = document.createElement("p");
  error.className = "tool-call-field-error";
  error.id = `${fieldId}-error`;
  error.hidden = true;
  panel.append(label, error);
  return panel;
}

function createToolCallControl(field, fieldId, label) {
  if (field.type === "boolean") {
    const wrapper = document.createElement("div");
    wrapper.className = "tool-call-choice-list";
    wrapper.setAttribute("role", "radiogroup");
    wrapper.setAttribute("aria-labelledby", label.id || `${fieldId}-label`);
    label.id = `${fieldId}-label`;
    const rawBooleanValue = String(field.value).toLowerCase();
    const booleanValue = field.value === true || rawBooleanValue === "true";
    const hasBooleanValue = field.value === true || field.value === false || rawBooleanValue === "true" || rawBooleanValue === "false";
    const choices = field.choices.length ? field.choices : [
      { value: true, label: "是", description: "" },
      { value: false, label: "否", description: "" },
    ];
    choices.forEach((choice) => {
      const value = choice.value === true || String(choice.value).toLowerCase() === "true";
      wrapper.append(createBooleanChoice(field, fieldId, value, choice.label, hasBooleanValue && (value ? booleanValue : !booleanValue), choice.description));
    });
    return wrapper;
  }
  if (field.type === "string") {
    return createStringChoiceControl(field, fieldId, label);
  }
  if (field.type === "number") {
    return createNumberControl(field, fieldId);
  }
  const value = field.value == null ? "" : String(field.value);
  const control = field.type === "string" && value.length > 60 ? document.createElement("textarea") : document.createElement("input");
  control.id = `${fieldId}-control`;
  control.name = field.name;
  control.dataset.toolCallType = field.type;
  control.value = value;
  if (control instanceof HTMLTextAreaElement) {
    control.rows = 3;
  } else {
    control.type = "text";
  }
  return control;
}

function createStringChoiceControl(field, fieldId, label) {
  const wrapper = document.createElement("div");
  wrapper.className = "tool-call-string-options";
  wrapper.setAttribute("role", "radiogroup");
  label.id = `${fieldId}-label`;
  wrapper.setAttribute("aria-labelledby", label.id);
  const choices = field.choices.length
    ? field.choices
    : [{ value: String(field.value || "請填寫"), label: String(field.value || "請填寫") }];
  choices.forEach((choice, index) => {
    wrapper.append(createStringChoice(field, fieldId, String(choice.value), choice.label, index === 0));
  });
  wrapper.append(createStringChoice(field, fieldId, "__custom__", field.customLabel, false));
  const customInput = document.createElement("input");
  customInput.className = "tool-call-custom-input";
  customInput.type = "text";
  customInput.placeholder = "輸入自訂內容";
  customInput.dataset.toolCallCustomFor = field.name;
  customInput.disabled = true;
  wrapper.append(customInput);
  return wrapper;
}

function createStringChoice(field, fieldId, value, labelText, checked) {
  const choice = document.createElement("label");
  choice.className = "tool-call-string-choice";
  const input = document.createElement("input");
  input.id = `${fieldId}-choice-${value === "__custom__" ? "custom" : labelText}`;
  input.type = "radio";
  input.name = field.name;
  input.value = value;
  input.dataset.toolCallType = "string";
  input.checked = checked;
  input.addEventListener("change", () => {
    const customInput = choice.parentElement?.querySelector(`[data-tool-call-custom-for="${CSS.escape(field.name)}"]`);
    if (customInput instanceof HTMLInputElement) {
      customInput.disabled = value !== "__custom__";
      if (value === "__custom__") {
        customInput.focus();
      }
    }
  });
  const text = document.createElement("span");
  text.textContent = labelText;
  choice.append(input, text);
  return choice;
}

function createNumberControl(field, fieldId) {
  const wrapper = document.createElement("div");
  wrapper.className = "tool-call-number-stepper";
  const decrement = document.createElement("button");
  decrement.type = "button";
  decrement.className = "tool-call-number-adjust";
  decrement.textContent = "-";
  decrement.setAttribute("aria-label", "減少數值");
  const input = document.createElement("input");
  input.id = `${fieldId}-control`;
  input.name = field.name;
  input.type = "number";
  input.step = "1";
  input.value = field.value == null || field.value === "" ? "0" : String(field.value);
  input.dataset.toolCallType = "number";
  const increment = document.createElement("button");
  increment.type = "button";
  increment.className = "tool-call-number-adjust";
  increment.textContent = "+";
  increment.setAttribute("aria-label", "增加數值");
  decrement.addEventListener("click", () => input.stepDown());
  increment.addEventListener("click", () => input.stepUp());
  wrapper.append(decrement, input, increment);
  return wrapper;
}

function createBooleanChoice(field, fieldId, value, labelText, checked, descriptionText = "") {
  const label = document.createElement("label");
  label.className = "tool-call-choice";
  const input = document.createElement("input");
  input.id = `${fieldId}-${value ? "true" : "false"}`;
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

function setToolCallValidation(form, fields) {
  const missingFields = new Set(fields.map((field) => field.name));
  form.querySelectorAll("[data-tool-call-field]").forEach((fieldPanel) => {
    const isMissing = missingFields.has(fieldPanel.dataset.toolCallField);
    fieldPanel.classList.toggle("is-invalid", isMissing);
    const error = fieldPanel.querySelector(".tool-call-field-error");
    if (error) {
      error.hidden = !isMissing;
      error.textContent = isMissing ? "此欄位為必填。" : "";
    }
    fieldPanel.querySelectorAll("[data-tool-call-type]").forEach((control) => {
      control.setAttribute("aria-invalid", String(isMissing));
      if (isMissing && error) {
        control.setAttribute("aria-describedby", error.id);
      }
    });
  });
}

function clearToolCallValidation(form) {
  form.querySelectorAll(".tool-call-panel.is-invalid").forEach((fieldPanel) => {
    fieldPanel.classList.remove("is-invalid");
    const error = fieldPanel.querySelector(".tool-call-field-error");
    if (error) {
      error.hidden = true;
      error.textContent = "";
    }
    fieldPanel.querySelectorAll("[data-tool-call-type]").forEach((control) => {
      control.removeAttribute("aria-invalid");
      control.removeAttribute("aria-describedby");
    });
  });
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
      if (control.type === "radio" && !control.checked) {
        return;
      }
      if (control.value === "__custom__") {
        const customInput = form.querySelector(`[data-tool-call-custom-for="${CSS.escape(name)}"]`);
        payload[name] = customInput instanceof HTMLInputElement ? customInput.value : "";
        return;
      }
      payload[name] = control.value;
    }
  });
  return payload;
}

function hasToolCallValue(value) {
  if (typeof value === "boolean") {
    return true;
  }
  if (typeof value === "number") {
    return Number.isFinite(value);
  }
  return String(value ?? "").trim().length > 0;
}

function createProcessEvent(event, { active = false } = {}) {
  const item = document.createElement("section");
  item.className = "process-event";
  if (event.visitId) {
    item.dataset.processVisitId = event.visitId;
  }
  if (active) {
    item.classList.add("is-active");
  }

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

  item.append(title, description);
  if (event.details.length) {
    const detailList = document.createElement("ul");
    detailList.className = "process-event-details";
    event.details.forEach((detail) => {
      const detailItem = document.createElement("li");
      detailItem.dataset.processField = detail.field;
      detailItem.textContent = detail.description;
      detailList.append(detailItem);
    });
    item.append(detailList);
  }
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
  renderProcessTraceHistory(list, events);

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
  if (event.details.length) {
    const detailList = document.createElement("ul");
    detailList.className = "process-summary-details";
    event.details.forEach((detail) => {
      const detailItem = document.createElement("li");
      detailItem.textContent = detail.description;
      detailList.append(detailItem);
    });
    item.append(detailList);
  }
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