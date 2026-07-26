export function setResultMessage(element, message) {
  if (element && message) {
    element.textContent = message;
  }
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

export function renderToolCallPanels(resultSurface, panels, options = {}) {
  const host = ensureToolCallHost(resultSurface);
  if (!host) {
    return;
  }
  host.replaceChildren();
  if (!Array.isArray(panels) || panels.length === 0) {
    host.hidden = true;
    return;
  }
  host.hidden = false;
  for (const panel of panels) {
    host.appendChild(createToolCallPanel(panel, options));
  }
}

function ensureToolCallHost(resultSurface) {
  if (!resultSurface) {
    return null;
  }
  const card = resultSurface.querySelector(".result-card") || resultSurface;
  let host = card.querySelector("[data-tool-call-panel-host]");
  if (!host) {
    host = document.createElement("div");
    host.className = "tool-call-panel-host";
    host.dataset.toolCallPanelHost = "";
    const content = card.querySelector(".result-content");
    if (content) {
      content.after(host);
    } else {
      card.appendChild(host);
    }
  }
  return host;
}

function createToolCallPanel(panel, options) {
  const form = document.createElement("form");
  form.className = "tool-call-panel";
  form.dataset.toolCallPanelId = panel.id || "";

  const header = document.createElement("div");
  header.className = "tool-call-panel-header";
  const title = document.createElement("strong");
  title.textContent = panel.title || "需要確認資料";
  const message = document.createElement("p");
  message.textContent = panel.message || "請確認欄位後送出。";
  header.append(title, message);
  form.appendChild(header);

  const fields = document.createElement("div");
  fields.className = "tool-call-fields";
  for (const field of panel.fields || []) {
    fields.appendChild(createToolCallField(field));
  }
  form.appendChild(fields);

  const actions = document.createElement("div");
  actions.className = "tool-call-actions";
  const submit = document.createElement("button");
  submit.type = "submit";
  submit.className = "button button-primary";
  submit.textContent = "送出選擇";
  actions.appendChild(submit);
  form.appendChild(actions);

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    form.dispatchEvent(
      new CustomEvent("runner:tool-call-submit", {
        bubbles: true,
        detail: {
          id: panel.id,
          function_name: panel.function_name,
          arguments: collectToolCallValues(form),
          requestMessage: options.requestMessage || "",
        },
      }),
    );
  });
  return form;
}

function createToolCallField(field) {
  const wrapper = document.createElement("label");
  wrapper.className = `tool-call-field tool-call-field-${field.type || "string"}`;
  const label = document.createElement("span");
  label.textContent = field.label || field.name || "欄位";
  wrapper.appendChild(label);

  if (field.type === "boolean") {
    const input = document.createElement("input");
    input.type = "checkbox";
    input.name = field.name || "value";
    input.checked = Boolean(field.value);
    input.dataset.valueType = "boolean";
    wrapper.appendChild(input);
    return wrapper;
  }

  if (field.type === "number") {
    const input = document.createElement("input");
    input.type = "number";
    input.name = field.name || "value";
    input.value = field.value ?? "";
    input.required = Boolean(field.required);
    input.dataset.valueType = "number";
    wrapper.appendChild(input);
    return wrapper;
  }

  const textarea = document.createElement("textarea");
  textarea.name = field.name || "value";
  textarea.rows = 2;
  textarea.value = field.value ?? "";
  textarea.required = Boolean(field.required);
  textarea.dataset.valueType = "string";
  wrapper.appendChild(textarea);
  return wrapper;
}

function collectToolCallValues(form) {
  const values = {};
  for (const input of form.querySelectorAll("input[name], textarea[name], select[name]")) {
    if (input.dataset.valueType === "boolean") {
      values[input.name] = input.checked;
    } else if (input.dataset.valueType === "number") {
      values[input.name] = input.value === "" ? null : Number(input.value);
    } else {
      values[input.name] = input.value;
    }
  }
  return values;
}