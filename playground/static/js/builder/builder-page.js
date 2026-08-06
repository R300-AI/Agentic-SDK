import { postJson } from "../shared/api-client.js";
import { selectChoice } from "./starter-template.js";

const progressSteps = Array.from(document.querySelectorAll("[data-progress-step]"));
const panels = Array.from(document.querySelectorAll("[data-step-panel]"));
const cards = document.querySelectorAll("[data-choice-card]");
const progressCurrent = document.querySelector("[data-progress-current]");
const builderFormStateElement = document.querySelector("[data-builder-form-state]");
const builderEndpointStateElement = document.querySelector("[data-builder-endpoint-state]");
const completeLinks = Array.from(document.querySelectorAll("[data-complete-link]"));
let stateQueue = Promise.resolve();
const reviewEndpointStepByRole = {
  perceive: "input_type",
  retrieve: "retrieve_policy",
  action: "output_format",
  reflect: "failure_policy",
};

const dependencyRules = {
  input_type: {
    pass_through: {},
    text: {},
    text_image: {},
  },
  retrieve_policy: {
    none: {},
    keyword: {},
    semantic: {},
  },
  output_format: {
    free_text: {},
    interactive: {},
  },
  failure_policy: {
    retry: {},
    handoff: {},
  },
};

const dependentStepOrder = ["input_type", "retrieve_policy", "output_format", "failure_policy"];

function updateSummary(workflowSummary = {}) {
  Object.entries(workflowSummary).forEach(([key, value]) => {
    document.querySelectorAll(`[data-summary-field="${key}"]`).forEach((field) => {
      field.textContent = value;
    });
  });
}

function endpointStatusText(state) {
  const requirements = Array.isArray(state?.requirements) ? state.requirements : [];
  const hasOptions = requirements.some((requirement) => Array.isArray(requirement.options) && requirement.options.length);
  if (!hasOptions) {
    return "Key Vault 中沒有可用的模型端點。請確認至少一組模型的 MODEL、BASE-URL 與 API-KEY secret。";
  }
  return state.configured ? "模型設定由 Key Vault 自動提供。" : "Key Vault 的模型設定不完整，請確認所需 secret。";
}

function reviewAnswerForStep(stepKey) {
  const panel = panels.find((candidate) => candidate.dataset.stepPanel === stepKey);
  const selectedCard = panel?.querySelector("[data-choice-card].selected:not([hidden])")
    || panel?.querySelector("[data-choice-card].selected");
  if (!selectedCard) {
    return { selected: false, answer: "尚未選擇" };
  }
  const answer = selectedCard.querySelector("strong")?.textContent?.trim() || selectedCard.dataset.choiceLabel || "已選擇";
  return { selected: true, answer };
}

function setCompleteLinkState(ready) {
  completeLinks.forEach((link) => {
    link.classList.toggle("is-disabled", !ready);
    link.setAttribute("aria-disabled", ready ? "false" : "true");
    if (ready) {
      link.removeAttribute("tabindex");
    } else {
      link.setAttribute("tabindex", "-1");
    }
  });
}

function renderBuilderReviewState(items, ready) {
  const reviewItems = Array.isArray(items) ? items : [];
  const itemsByStep = new Map(reviewItems.map((item) => [String(item.step_key || ""), item]));
  document.querySelectorAll("[data-review-item]").forEach((item) => {
    const fallbackState = reviewAnswerForStep(item.dataset.reviewStep || "");
    const state = itemsByStep.get(item.dataset.reviewStep || "") || fallbackState;
    const completed = Boolean(state.completed ?? state.selected);
    item.classList.toggle("is-complete", completed);
    item.classList.toggle("is-incomplete", !completed);
    const status = item.querySelector("[data-review-status]");
    const answer = item.querySelector("[data-review-answer]");
    const detail = item.querySelector("[data-review-detail]");
    if (status) {
      status.checked = completed;
    }
    if (answer) {
      answer.textContent = state.answer || fallbackState.answer;
    }
    if (detail) {
      const text = String(state.detail || "").trim();
      detail.textContent = text;
      detail.hidden = !text;
      detail.classList.toggle("hidden", !text);
    }
  });
  setCompleteLinkState(Boolean(ready));
}

function renderBuilderEndpointState(state) {
  const requirements = Array.isArray(state?.requirements) ? state.requirements : [];
  const selections = state?.selections && typeof state.selections === "object" ? state.selections : {};
  const groupedRequirements = new Map();
  requirements.forEach((requirement) => {
    const stepKey = reviewEndpointStepByRole[requirement.role];
    if (!stepKey) {
      return;
    }
    const items = groupedRequirements.get(stepKey) || [];
    items.push(requirement);
    groupedRequirements.set(stepKey, items);
  });

  document.querySelectorAll("[data-review-item]").forEach((item) => {
    const body = item.querySelector("[data-review-endpoint-body]");
    if (!body) {
      return;
    }
    body.replaceChildren();
    const stepKey = item.dataset.reviewStep || "";
    const stepRequirements = groupedRequirements.get(stepKey) || [];
    if (!stepRequirements.length) {
      return;
    }

    const hasOptions = stepRequirements.every((requirement) => Array.isArray(requirement.options) && requirement.options.length);
    if (hasOptions) {
      const form = document.createElement("form");
      form.className = "module-param-form endpoint-form";
      form.dataset.builderEndpointForm = "true";
      stepRequirements.forEach((requirement) => {
        const label = document.createElement("label");
        label.className = "endpoint-row";

        const select = document.createElement("select");
        select.name = requirement.role;
        select.dataset.builderEndpointSelect = "true";
        select.required = true;
        const placeholder = document.createElement("option");
        placeholder.value = "";
        placeholder.textContent = "(請選擇部署選項)";
        placeholder.disabled = true;
        placeholder.selected = !selections[requirement.role];
        select.append(placeholder);
        requirement.options.forEach((endpoint) => {
          const option = document.createElement("option");
          option.value = endpoint.id;
          option.textContent = endpoint.label;
          option.selected = selections[requirement.role] === endpoint.id;
          select.append(option);
        });

        label.append(select);
        form.append(label);
      });
      body.append(form);
      return;
    }

    const statusText = endpointStatusText(state);
    if (statusText) {
      const status = document.createElement("p");
      status.className = "inline-status error";
      status.dataset.builderEndpointStatus = "true";
      status.textContent = statusText;
      body.append(status);
    }
  });
}

async function syncBuilderEndpointSelections() {
  const forms = Array.from(document.querySelectorAll("[data-builder-endpoint-form]"));
  if (!forms.length) {
    return;
  }
  const selections = {};
  forms.forEach((form) => Object.assign(selections, Object.fromEntries(new FormData(form).entries())));
  const result = await postJson("/playground/builder/endpoints", { selections });
  renderBuilderEndpointState(result);
  renderBuilderReviewState(result.builder_review_state, result.builder_review_ready);
}

async function postBuilderState(payload) {
  const task = stateQueue.catch(() => {}).then(async () => {
    const response = await postJson("/playground/builder/state", payload);
    updateSummary(response.workflow_summary);
    renderBuilderEndpointState(response.builder_endpoint_state);
    renderBuilderReviewState(response.builder_review_state, response.builder_review_ready);
    return response;
  });
  stateQueue = task.then(() => undefined, () => undefined);
  return task;
}

async function flushBuilderState() {
  await stateQueue;
}

async function syncTextInput(panel) {
  const input = panel?.querySelector("[data-name-input]");
  if (!input) {
    return;
  }
  await postBuilderState({
    step: input.dataset.stepKey,
    value: input.value,
  });
}

async function syncParamForms(panel) {
  const forms = Array.from(panel?.querySelectorAll("[data-param-form]") || []).filter((form) => !form.closest("[hidden]"));
  forms.forEach(syncPairEditors);
  forms.forEach(syncApiEditors);
  await Promise.all(forms.map((form) => postBuilderState({
    step: form.dataset.stepKey,
    value: Object.fromEntries(new FormData(form).entries()),
  })));
}

async function syncSelectedChoice(panel) {
  const selectedCard = panel?.querySelector("[data-choice-card].selected:not([hidden])")
    || panel?.querySelector("[data-choice-card].selected");
  if (!selectedCard) {
    return;
  }
  const dependencyChanges = applyChoiceDependencies();
  await postBuilderState({
    step: selectedCard.dataset.stepKey,
    choice: selectedCard.dataset.choiceLabel,
  });
  await Promise.all(dependencyChanges.map((change) => postBuilderState(change)));
}

function updateConditionalForms(panel) {
  const selectedChoice = panel?.querySelector("[data-choice-card].selected")?.dataset.choiceLabel;
  const selections = selectedChoices();
  panel?.querySelectorAll("[data-visible-choices]").forEach((form) => {
    const visibleChoices = form.dataset.visibleChoices.includes("|")
      ? form.dataset.visibleChoices.split("|").map((choice) => choice.trim())
      : [form.dataset.visibleChoices.trim()];
    const choiceVisible = visibleChoices.includes(selectedChoice);
    const dependenciesVisible = visibleDependenciesSatisfied(form.dataset.visibleDependencies, selections);
    form.hidden = !(choiceVisible && dependenciesVisible);
  });
  updateInputTypeFieldCopy(panel, selectedChoice);
}

function updateInputTypeFieldCopy(panel, selectedChoice) {
  if (!panel || panel.dataset.stepPanel !== "input_type") {
    return;
  }
  const mode = selectedChoice === "text_image" ? "text-image" : "text";
  panel.querySelectorAll("[data-input-mode-copy]").forEach((element) => {
    const nextText = mode === "text-image" ? element.dataset.textImageCopy : element.dataset.textCopy;
    if (nextText) {
      element.textContent = nextText;
    }
  });
  panel.querySelectorAll("[data-input-mode-placeholder]").forEach((field) => {
    const nextPlaceholder = mode === "text-image" ? field.dataset.textImagePlaceholder : field.dataset.textPlaceholder;
    if (nextPlaceholder) {
      field.placeholder = nextPlaceholder;
    }
  });
  panel.querySelectorAll("[data-input-mode-pair-fields]").forEach((wrapper) => {
    const keyPlaceholder = mode === "text-image" ? wrapper.dataset.textImageKeyPlaceholder : wrapper.dataset.textKeyPlaceholder;
    const valuePlaceholder = mode === "text-image" ? wrapper.dataset.textImageValuePlaceholder : wrapper.dataset.textValuePlaceholder;
    wrapper.querySelectorAll("[data-pair-key]").forEach((field) => {
      if (keyPlaceholder) {
        field.placeholder = keyPlaceholder;
      }
    });
    wrapper.querySelectorAll("[data-pair-value]").forEach((field) => {
      if (valuePlaceholder) {
        field.placeholder = valuePlaceholder;
      }
    });
  });
}

function visibleDependenciesSatisfied(rawDependencies, selections) {
  if (!rawDependencies) {
    return true;
  }
  return rawDependencies.split(";").map((dependency) => dependency.trim()).filter(Boolean).every((dependency) => {
    const [stepKey, rawAllowedChoices = ""] = dependency.split("=").map((part) => part.trim());
    const allowedChoices = rawAllowedChoices.split("|").map((choice) => choice.trim()).filter(Boolean);
    return stepKey && allowedChoices.includes(selections[stepKey]);
  });
}

function updateRangeOutput(range) {
  const output = range.form?.querySelector(`output[for="${range.id}"]`);
  if (output) {
    output.value = range.value;
    output.textContent = range.value;
  }
}

function selectedChoices() {
  const selections = {};
  panels.forEach((panel) => {
    const selectedCard = panel.querySelector("[data-choice-card].selected:not([hidden])")
      || panel.querySelector("[data-choice-card].selected");
    if (selectedCard) {
      selections[panel.dataset.stepPanel] = selectedCard.dataset.choiceLabel;
    }
  });
  return selections;
}

function isChoiceAllowed(stepKey, choiceLabel, selections) {
  const rule = dependencyRules[stepKey]?.[choiceLabel];
  if (!rule) {
    return true;
  }
  return Object.entries(rule).every(([dependencyStep, allowedChoices]) => {
    const selectedChoice = selections[dependencyStep];
    return !selectedChoice || allowedChoices.includes(selectedChoice);
  });
}

function applyChoiceDependencies() {
  const changes = [];
  const selections = selectedChoices();

  dependentStepOrder.forEach((stepKey) => {
    const panel = panels.find((candidate) => candidate.dataset.stepPanel === stepKey);
    const stepCards = Array.from(panel?.querySelectorAll("[data-choice-card]") || []);
    if (!panel || !stepCards.length) {
      return;
    }

    stepCards.forEach((card) => {
      const allowed = isChoiceAllowed(stepKey, card.dataset.choiceLabel, selections);
      card.hidden = !allowed;
      card.setAttribute("aria-disabled", allowed ? "false" : "true");
    });

    const selectedCard = stepCards.find((card) => card.classList.contains("selected") && !card.hidden);
    const fallbackCard = stepCards.find((card) => !card.hidden);
    if (!selectedCard && fallbackCard) {
      selectChoice(stepCards, fallbackCard);
      selections[stepKey] = fallbackCard.dataset.choiceLabel;
      changes.push({ step: stepKey, choice: fallbackCard.dataset.choiceLabel });
    } else if (selectedCard) {
      selections[stepKey] = selectedCard.dataset.choiceLabel;
    }

    updateConditionalForms(panel);
  });

  return changes;
}

function parseInitialBuilderFormState() {
  const rawState = builderFormStateElement?.textContent?.trim();
  if (!rawState) {
    return { choices: {}, values: {} };
  }
  try {
    return JSON.parse(rawState);
  } catch {
    return { choices: {}, values: {} };
  }
}

function parseInitialBuilderEndpointState() {
  const rawState = builderEndpointStateElement?.textContent?.trim();
  if (!rawState) {
    return { requirements: [], endpoints: [], selections: {}, configured: true };
  }
  try {
    return JSON.parse(rawState);
  } catch {
    return { requirements: [], endpoints: [], selections: {}, configured: true };
  }
}

function parsePairText(value) {
  return String(value || "")
    .split(/\r?\n/)
    .map((line) => {
      const separatorIndex = ["=", "：", ":"]
        .map((separator) => line.indexOf(separator))
        .filter((index) => index >= 0)
        .sort((left, right) => left - right)[0];
      if (separatorIndex === undefined) {
        return null;
      }
      const key = line.slice(0, separatorIndex).trim();
      const pairValue = line.slice(separatorIndex + 1).trim();
      return key && pairValue ? { key, value: pairValue } : null;
    })
    .filter(Boolean);
}

function parseListText(value) {
  return String(value || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

function setPairEditorValue(output, value) {
  const editor = output.closest("[data-pair-editor]");
  const list = editor?.querySelector("[data-pair-list]");
  const sourceRow = editor?.querySelector("[data-pair-row]");
  const addButton = list?.querySelector("[data-pair-add]");
  if (!editor || !list || !sourceRow) {
    output.value = String(value || "");
    return;
  }
  const pairs = parsePairText(value);
  const rows = pairs.length ? pairs : [{ key: "", value: "" }];
  const nextChildren = rows.map((pair) => {
    const row = sourceRow.cloneNode(true);
    row.querySelector("[data-pair-key]").value = pair.key;
    row.querySelector("[data-pair-value]").value = pair.value;
    const typeField = row.querySelector("[data-pair-type]");
    if (typeField) {
      const typeMatch = pair.value.match(/（(?:資料類型|呈現方式)：(.+?)）$/);
      if (typeMatch) {
        const cleanedValue = pair.value.replace(/\s*（(?:資料類型|呈現方式)：.+?）$/, "").trim();
        row.querySelector("[data-pair-value]").value = cleanedValue;
        typeField.value = normalizePairType(typeMatch[1]);
      }
    }
    return row;
  });
  if (addButton) {
    nextChildren.push(addButton);
  }
  list.replaceChildren(...nextChildren);
  syncPairEditor(editor);
}

function setListEditorValue(output, value) {
  const editor = output.closest("[data-list-editor]");
  const list = editor?.querySelector("[data-list-list]");
  const sourceRow = editor?.querySelector("[data-list-row]");
  const addButton = list?.querySelector("[data-list-add]");
  if (!editor || !list || !sourceRow) {
    output.value = String(value || "");
    return;
  }
  const items = parseListText(value);
  const rows = items.length ? items : [""];
  const nextChildren = rows.map((item) => {
    const row = sourceRow.cloneNode(true);
    row.querySelector("[data-list-item]").value = item;
    return row;
  });
  if (addButton) {
    nextChildren.push(addButton);
  }
  list.replaceChildren(...nextChildren);
  syncListEditor(editor);
}

function parseApiContracts(value) {
  if (!value) {
    return [];
  }
  try {
    const parsed = JSON.parse(String(value));
    if (!Array.isArray(parsed)) {
      return [];
    }
    return parsed.map((contract) => ({
      interaction_trigger: String(contract?.interaction_trigger || ""),
      api_method: String(contract?.api_method || "POST"),
      api_url: String(contract?.api_url || ""),
      component_fields: String(contract?.component_fields || ""),
    }));
  } catch {
    return [];
  }
}

function setApiEditorValue(output, value) {
  const editor = output.closest("[data-api-editor]");
  const list = editor?.querySelector("[data-api-list]");
  const sourceBlock = editor?.querySelector("[data-api-block]");
  if (!editor || !list || !sourceBlock) {
    output.value = String(value || "");
    return;
  }
  const contracts = parseApiContracts(value);
  const blocks = contracts.length ? contracts : [{ interaction_trigger: "", api_method: "POST", api_url: "", component_fields: "" }];
  list.replaceChildren(...blocks.map((contract, index) => {
    const block = sourceBlock.cloneNode(true);
    clearApiBlock(block);
    block.querySelector("[data-api-trigger]").value = contract.interaction_trigger;
    block.querySelector("[data-api-method]").value = normalizeApiMethod(contract.api_method);
    block.querySelector("[data-api-url]").value = contract.api_url;
    const fieldsOutput = block.querySelector("[data-pair-output]");
    if (fieldsOutput) {
      setPairEditorValue(fieldsOutput, contract.component_fields);
    }
    updateApiBlock(block, index);
    return block;
  }));
  syncApiEditor(editor);
}

function normalizePairType(value) {
  return String(value || "").trim();
}

function setFieldValue(field, value) {
  if (field.matches("[data-semantic-upload-output]")) {
    field.value = String(value ?? "");
    syncSemanticUploadPanel(field.closest("[data-semantic-upload-panel]"));
    return;
  }
  if (field.matches("[data-api-output]")) {
    setApiEditorValue(field, value);
    return;
  }
  if (field.matches("[data-list-output]")) {
    setListEditorValue(field, value);
    return;
  }
  if (field.matches("[data-pair-output]")) {
    setPairEditorValue(field, value);
    return;
  }
  field.value = String(value ?? "");
  if (field.matches("[data-range-control]")) {
    updateRangeOutput(field);
  }
}

function fieldsForStepValue(stepKey, fieldName) {
  const fields = [];
  document.querySelectorAll("[data-name-input]").forEach((field) => {
    if (field.dataset.stepKey === stepKey && field.name === fieldName) {
      fields.push(field);
    }
  });
  document.querySelectorAll("[data-param-form]").forEach((form) => {
    if (form.dataset.stepKey !== stepKey) {
      return;
    }
    Array.from(form.elements).forEach((field) => {
      if (field.name === fieldName) {
        fields.push(field);
      }
    });
  });
  return fields;
}

function hydrateBuilderFormState(state) {
  const choices = state?.choices && typeof state.choices === "object" ? state.choices : {};
  Object.entries(choices).forEach(([stepKey, choiceLabel]) => {
    const panel = panels.find((candidate) => candidate.dataset.stepPanel === stepKey);
    const selectedCard = Array.from(panel?.querySelectorAll("[data-choice-card]") || [])
      .find((card) => card.dataset.choiceLabel === String(choiceLabel) && !card.disabled);
    if (panel && selectedCard) {
      selectChoice(panel.querySelectorAll("[data-choice-card]"), selectedCard);
      updateConditionalForms(panel);
    }
  });

  const values = state?.values && typeof state.values === "object" ? state.values : {};
  Object.entries(values).forEach(([stepKey, stepValues]) => {
    if (!stepValues || typeof stepValues !== "object") {
      return;
    }
    Object.entries(stepValues).forEach(([fieldName, value]) => {
      fieldsForStepValue(stepKey, fieldName).forEach((field) => setFieldValue(field, value));
    });
  });
}

function syncPairEditor(editor) {
  const output = editor.querySelector("[data-pair-output]");
  if (!output) {
    return;
  }
  const pairs = Array.from(editor.querySelectorAll("[data-pair-row]")).map((row) => {
    const key = row.querySelector("[data-pair-key]")?.value.trim() || "";
    const value = row.querySelector("[data-pair-value]")?.value.trim().replace(/\s+/g, " ") || "";
    const type = row.querySelector("[data-pair-type]")?.value.trim() || "";
    return { key, value, type };
  }).filter((pair) => pair.key && pair.value);
  output.value = pairs.map((pair) => {
    const typeSuffix = pair.type ? `（資料類型：${pair.type}）` : "";
    return `${pair.key} = ${pair.value}${typeSuffix}`;
  }).join("\n");
}

function syncPairEditors(root) {
  root.querySelectorAll("[data-pair-editor]").forEach(syncPairEditor);
}

function syncListEditor(editor) {
  const output = editor.querySelector("[data-list-output]");
  if (!output) {
    return;
  }
  const items = Array.from(editor.querySelectorAll("[data-list-row]"))
    .map((row) => row.querySelector("[data-list-item]")?.value.trim() || "")
    .filter(Boolean);
  output.value = items.join("\n");
}

function syncListEditors(root) {
  root.querySelectorAll("[data-list-editor]").forEach(syncListEditor);
}

function syncSemanticUploadPanel(panel) {
  const output = panel?.querySelector("[data-semantic-upload-output]");
  const list = panel?.querySelector("[data-semantic-upload-list]");
  const status = panel?.querySelector("[data-semantic-upload-status]");
  if (!output || !list || !status) {
    return;
  }
  const items = parseListText(output.value);
  list.replaceChildren(
    ...items.map((item) => {
      const row = document.createElement("li");
      const name = document.createElement("span");
      const state = document.createElement("strong");
      name.textContent = item;
      state.textContent = "已上傳";
      row.append(name, state);
      return row;
    }),
  );
  status.classList.remove("error");
  status.textContent = items.length
    ? `已上傳 ${items.length} 份參考文件。`
    : "尚未上傳參考文件。";
}

function uploadSemanticFiles(panel) {
  const input = panel?.querySelector("[data-semantic-upload-input]");
  const output = panel?.querySelector("[data-semantic-upload-output]");
  const status = panel?.querySelector("[data-semantic-upload-status]");
  const progress = panel?.querySelector("[data-semantic-upload-progress]");
  const files = Array.from(input?.files || []);
  if (!input || !output || !status || !progress || !files.length) {
    return Promise.resolve();
  }

  const allowedExtensions = new Set(
    String(input.accept || "")
      .split(",")
      .map((extension) => extension.trim().toLowerCase())
      .filter((extension) => extension.startsWith(".")),
  );
  const rejectedNames = files
    .filter((file) => !allowedExtensions.has(`.${file.name.split(".").pop()?.toLowerCase() || ""}`))
    .map((file) => file.name);
  const acceptedFiles = files.filter((file) => !rejectedNames.includes(file.name));
  if (!acceptedFiles.length) {
    status.classList.add("error");
    status.textContent = `不支援上傳：${rejectedNames.join("、")}。`;
    input.value = "";
    return Promise.resolve();
  }

  status.classList.remove("error");
  status.textContent = `準備上傳 ${acceptedFiles.length} 份參考文件...`;
  progress.hidden = false;
  progress.value = 0;

  const formData = new FormData();
  acceptedFiles.forEach((file) => formData.append("files", file));

  return new Promise((resolve) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", "/playground/builder/uploads");
    xhr.upload.addEventListener("progress", (event) => {
      if (!event.lengthComputable) {
        return;
      }
      progress.value = Math.round((event.loaded / event.total) * 100);
    });
    xhr.addEventListener("load", () => {
      progress.value = 100;
      try {
        const response = JSON.parse(xhr.responseText || "{}");
        const rejectedFiles = Array.isArray(response.rejected_files) ? response.rejected_files : [];
        if (xhr.status >= 400 || response.updated === false) {
          const rejectedMessage = rejectedFiles.map((file) => `${file.name}：${file.reason}`).join("；");
          throw new Error(rejectedMessage || response.error || "上傳失敗。");
        }
        output.value = Array.isArray(response.semantic_support_files)
          ? response.semantic_support_files.join("\n")
          : "";
        syncSemanticUploadPanel(panel);
        const rejectedMessage = [
          ...rejectedNames.map((name) => `${name}：不支援的檔案格式。`),
          ...rejectedFiles.map((file) => `${file.name}：${file.reason}`),
        ].join("；");
        if (rejectedMessage) {
          status.classList.add("error");
          status.textContent = rejectedMessage;
        }
        updateSummary(response.workflow_summary);
        renderBuilderEndpointState(response.builder_endpoint_state);
        renderBuilderReviewState(response.builder_review_state, response.builder_review_ready);
      } catch (error) {
        status.classList.add("error");
        status.textContent = error.message || "上傳失敗。";
      }
      input.value = "";
      window.setTimeout(() => {
        progress.hidden = true;
        progress.value = 0;
      }, 400);
      resolve();
    });
    xhr.addEventListener("error", () => {
      status.classList.add("error");
      status.textContent = "上傳失敗。";
      progress.hidden = true;
      progress.value = 0;
      input.value = "";
      resolve();
    });
    xhr.send(formData);
  });
}

function normalizeApiMethod(value) {
  const method = String(value || "POST").trim().toUpperCase();
  return ["POST", "PUT", "PATCH", "DELETE"].includes(method) ? method : "POST";
}

function apiContracts(editor) {
  return Array.from(editor.querySelectorAll("[data-api-block]")).map((block) => {
    syncPairEditors(block);
    return {
      interaction_trigger: block.querySelector("[data-api-trigger]")?.value.trim() || "",
      api_method: normalizeApiMethod(block.querySelector("[data-api-method]")?.value),
      api_url: block.querySelector("[data-api-url]")?.value.trim() || "",
      component_fields: block.querySelector("[data-pair-output]")?.value.trim() || "",
    };
  }).filter((contract) => contract.interaction_trigger || contract.api_url || contract.component_fields);
}

function syncApiEditor(editor) {
  const output = editor?.querySelector("[data-api-output]");
  if (!output) {
    return;
  }
  const contracts = apiContracts(editor);
  output.value = contracts.length ? JSON.stringify(contracts) : "";
}

function syncApiEditors(root) {
  root.querySelectorAll("[data-api-editor]").forEach(syncApiEditor);
}

function requiredStepError(panel) {
  const selectedChoice = panel?.querySelector("[data-choice-card].selected:not([hidden])")
    || panel?.querySelector("[data-choice-card].selected");
  if (!panel || !selectedChoice) {
    return "請先選擇這一題的設定。";
  }
  if (panel.dataset.stepPanel === "retrieve_policy" && selectedChoice.dataset.choiceLabel === "semantic") {
    const sources = panel.querySelector("[data-semantic-upload-output]")?.value.trim();
    return sources ? "" : "請完成必填欄位。";
  }
  if (panel.dataset.stepPanel === "output_format" && selectedChoice.dataset.choiceLabel === "interactive") {
    const contracts = apiContracts(panel.querySelector("[data-api-editor]"));
    const hasCompleteContract = contracts.some((contract) => contract.api_url && contract.component_fields);
    return hasCompleteContract ? "" : "請完成必填欄位。";
  }
  return "";
}

function showStepValidationError(panel, message) {
  let status = panel?.querySelector("[data-step-validation-error]");
  if (!status && panel) {
    status = document.createElement("p");
    status.className = "inline-status error";
    status.dataset.stepValidationError = "true";
    panel.append(status);
  }
  if (status) {
    status.textContent = message;
    status.hidden = !message;
  }
}

function clearApiBlock(block) {
  block.querySelectorAll("[data-api-trigger], [data-api-url]").forEach((field) => {
    field.value = "";
  });
  block.querySelectorAll("[data-api-method]").forEach((field) => {
    field.value = "POST";
  });
  block.querySelectorAll("[data-pair-row]").forEach((row, index) => {
    if (index === 0) {
      clearPairRow(row);
    } else {
      row.remove();
    }
  });
  block.querySelectorAll("[data-pair-output]").forEach((field) => {
    field.value = "";
  });
}

function updateApiBlock(block, index) {
  const suffix = index === 0 ? "" : `-${index + 1}`;
  const fieldIds = new Map([
    ["[data-api-trigger]", `v3-action-interaction-trigger${suffix}`],
    ["[data-api-method]", `v3-action-api-method${suffix}`],
    ["[data-api-url]", `v3-action-api-url${suffix}`],
    ["[data-pair-output]", `v3-action-component-fields${suffix}`],
  ]);
  fieldIds.forEach((id, selector) => {
    const field = block.querySelector(selector);
    if (!field) {
      return;
    }
    const previousId = field.id;
    field.id = id;
    if (previousId) {
      block.querySelectorAll(`label[for="${previousId}"]`).forEach((label) => {
        label.setAttribute("for", id);
      });
    }
  });
  ["[data-api-trigger]", "[data-api-method]", "[data-api-url]", "[data-pair-output]"].forEach((selector) => {
    const field = block.querySelector(selector);
    if (field) {
      field.removeAttribute("name");
    }
  });
  const title = block.querySelector("[data-api-title]");
  if (title) {
    title.textContent = index === 0 ? "API 設定" : `API 設定 ${index + 1}`;
  }
  const removeButton = block.querySelector("[data-api-remove]");
  if (removeButton) {
    removeButton.hidden = index === 0;
  }
}

function refreshApiBlocks(editor) {
  editor.querySelectorAll("[data-api-block]").forEach(updateApiBlock);
}

function clearPairRow(row) {
  row.querySelectorAll("[data-pair-key], [data-pair-value]").forEach((field) => {
    field.value = "";
  });
  row.querySelectorAll("[data-pair-type]").forEach((field) => {
    field.selectedIndex = 0;
  });
}

function clearListRow(row) {
  row.querySelectorAll("[data-list-item]").forEach((field) => {
    field.value = "";
  });
}

function addPairRow(editor) {
  const list = editor.querySelector("[data-pair-list]");
  const sourceRow = editor.querySelector("[data-pair-row]");
  const addButton = editor.querySelector("[data-pair-add]");
  if (!list || !sourceRow) {
    return;
  }
  const row = sourceRow.cloneNode(true);
  clearPairRow(row);
  if (addButton?.parentElement === list) {
    list.insertBefore(row, addButton);
  } else {
    list.append(row);
  }
  row.querySelector("[data-pair-key]")?.focus();
  syncPairEditor(editor);
}

function addListRow(editor) {
  const list = editor.querySelector("[data-list-list]");
  const sourceRow = editor.querySelector("[data-list-row]");
  const addButton = editor.querySelector("[data-list-add]");
  if (!list || !sourceRow) {
    return;
  }
  const row = sourceRow.cloneNode(true);
  clearListRow(row);
  if (addButton?.parentElement === list) {
    list.insertBefore(row, addButton);
  } else {
    list.append(row);
  }
  row.querySelector("[data-list-item]")?.focus();
  syncListEditor(editor);
}

function addApiBlock(editor) {
  const list = editor.querySelector("[data-api-list]");
  const sourceBlock = editor.querySelector("[data-api-block]");
  if (!list || !sourceBlock) {
    return;
  }
  const block = sourceBlock.cloneNode(true);
  clearApiBlock(block);
  list.append(block);
  refreshApiBlocks(editor);
  block.querySelector("[data-api-trigger]")?.focus();
  syncApiEditor(editor);
}

function removeApiBlock(editor, block) {
  const blocks = Array.from(editor.querySelectorAll("[data-api-block]"));
  if (blocks.length <= 1) {
    clearApiBlock(block);
  } else {
    block.remove();
  }
  refreshApiBlocks(editor);
  syncApiEditor(editor);
}

function removePairRow(editor, row) {
  const rows = Array.from(editor.querySelectorAll("[data-pair-row]"));
  if (rows.length <= 1) {
    clearPairRow(row);
  } else {
    row.remove();
  }
  syncPairEditor(editor);
}

function removeListRow(editor, row) {
  const rows = Array.from(editor.querySelectorAll("[data-list-row]"));
  if (rows.length <= 1) {
    clearListRow(row);
  } else {
    row.remove();
  }
  syncListEditor(editor);
}

function showStep(key) {
  const activeIndex = progressSteps.findIndex((step) => step.dataset.progressStep === key);

  progressSteps.forEach((step, index) => {
    const isActive = index === activeIndex;
    const isCompleted = index < activeIndex;
    step.classList.toggle("active", isActive);
    step.classList.toggle("completed", isCompleted);
    if (isActive) {
      step.setAttribute("aria-current", "step");
    } else {
      step.removeAttribute("aria-current");
    }
    const status = isActive ? "目前階段" : isCompleted ? "已完成" : "尚未進行";
    step.setAttribute("aria-label", `${status}：步驟 ${index + 1} / ${progressSteps.length}：${step.dataset.stepLabel}`);
  });

  if (progressCurrent && activeIndex >= 0) {
    progressCurrent.textContent = `目前階段：步驟 ${activeIndex + 1} / ${progressSteps.length}`;
  }

  panels.forEach((panel) => {
    const isActive = panel.dataset.stepPanel === key;
    panel.hidden = !isActive;
    panel.classList.toggle("active", isActive);
    if (isActive) {
      updateConditionalForms(panel);
    }
  });
}

hydrateBuilderFormState(parseInitialBuilderFormState());
renderBuilderEndpointState(parseInitialBuilderEndpointState());
applyChoiceDependencies();
panels.forEach(updateConditionalForms);
renderBuilderReviewState(
  Array.from(document.querySelectorAll("[data-review-item]")).map((item) => ({
    step_key: item.dataset.reviewStep || "",
    completed: item.classList.contains("is-complete"),
    answer: item.querySelector("[data-review-answer]")?.textContent || "尚未選擇",
    detail: item.querySelector("[data-review-detail]")?.textContent || "",
  })),
  completeLinks.every((link) => link.getAttribute("aria-disabled") !== "true"),
);

cards.forEach((card) => {
  card.addEventListener("click", async () => {
    if (card.disabled || card.getAttribute("aria-disabled") === "true") {
      return;
    }
    const panel = card.closest("[data-step-panel]");
    if (panel) {
      selectChoice(panel.querySelectorAll("[data-choice-card]"), card);
      updateConditionalForms(panel);
    }
    const dependencyChanges = applyChoiceDependencies();
    await postBuilderState({
      step: card.dataset.stepKey,
      choice: card.dataset.choiceLabel,
    });
    await Promise.all(dependencyChanges.map((change) => postBuilderState(change)));
  });
});

document.addEventListener("change", async (event) => {
  if (event.target.matches("[data-builder-endpoint-select]")) {
    await syncBuilderEndpointSelections();
  }
});

document.querySelectorAll("[data-name-form]").forEach((form) => {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    await syncTextInput(form.closest("[data-step-panel]"));
  });
});

document.querySelectorAll("[data-name-input]").forEach((input) => {
  input.addEventListener("change", async () => {
    await postBuilderState({
      step: input.dataset.stepKey,
      value: input.value,
    });
  });
});

document.querySelectorAll("[data-param-form]").forEach((form) => {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    await syncParamForms(form.closest("[data-step-panel]"));
  });
  form.addEventListener("input", (event) => {
    const field = event.target.closest?.("[data-pair-key], [data-pair-value], [data-pair-type]");
    if (field) {
      syncPairEditor(field.closest("[data-pair-editor]"));
      syncApiEditor(field.closest("[data-api-editor]"));
      return;
    }
    const listField = event.target.closest?.("[data-list-item]");
    if (listField) {
      syncListEditor(listField.closest("[data-list-editor]"));
      return;
    }
    const apiField = event.target.closest?.("[data-api-trigger], [data-api-url]");
    if (apiField) {
      syncApiEditor(apiField.closest("[data-api-editor]"));
    }
  });
  form.addEventListener("change", async (event) => {
    const uploadInput = event.target.closest?.("[data-semantic-upload-input]");
    if (uploadInput) {
      await uploadSemanticFiles(uploadInput.closest("[data-semantic-upload-panel]"));
      return;
    }
    const field = event.target.closest?.("[data-pair-key], [data-pair-value], [data-pair-type]");
    if (field) {
      syncPairEditor(field.closest("[data-pair-editor]"));
      syncApiEditor(field.closest("[data-api-editor]"));
      await syncParamForms(form.closest("[data-step-panel]"));
      return;
    }
    const listField = event.target.closest?.("[data-list-item]");
    if (listField) {
      syncListEditor(listField.closest("[data-list-editor]"));
      await syncParamForms(form.closest("[data-step-panel]"));
      return;
    }
    const apiField = event.target.closest?.("[data-api-trigger], [data-api-method], [data-api-url]");
    if (apiField) {
      syncApiEditor(apiField.closest("[data-api-editor]"));
      await syncParamForms(form.closest("[data-step-panel]"));
    }
  });
  form.addEventListener("click", async (event) => {
    const addButton = event.target.closest?.("[data-pair-add]");
    const removeButton = event.target.closest?.("[data-pair-remove]");
    const addListButton = event.target.closest?.("[data-list-add]");
    const removeListButton = event.target.closest?.("[data-list-remove]");
    const addApiButton = event.target.closest?.("[data-api-add]");
    const removeApiButton = event.target.closest?.("[data-api-remove]");
    if (addListButton) {
      addListRow(addListButton.closest("[data-list-editor]"));
      return;
    }
    if (addButton) {
      addPairRow(addButton.closest("[data-pair-editor]"));
      syncApiEditor(addButton.closest("[data-api-editor]"));
      return;
    }
    if (addApiButton) {
      addApiBlock(addApiButton.closest("[data-api-editor]"));
      return;
    }
    if (removeButton) {
      removePairRow(removeButton.closest("[data-pair-editor]"), removeButton.closest("[data-pair-row]"));
      syncApiEditor(removeButton.closest("[data-api-editor]"));
      await syncParamForms(form.closest("[data-step-panel]"));
      return;
    }
    if (removeListButton) {
      removeListRow(removeListButton.closest("[data-list-editor]"), removeListButton.closest("[data-list-row]"));
      await syncParamForms(form.closest("[data-step-panel]"));
      return;
    }
    if (removeApiButton) {
      removeApiBlock(removeApiButton.closest("[data-api-editor]"), removeApiButton.closest("[data-api-block]"));
      await syncParamForms(form.closest("[data-step-panel]"));
    }
  });
  form.querySelectorAll("input, textarea, select").forEach((field) => {
    if (field.matches("[data-pair-key], [data-pair-value], [data-pair-type], [data-pair-output], [data-list-item], [data-list-output], [data-api-trigger], [data-api-method], [data-api-url], [data-api-output]")) {
      return;
    }
    if (field.matches("[data-range-control]")) {
      updateRangeOutput(field);
      field.addEventListener("input", () => updateRangeOutput(field));
    }
    field.addEventListener("change", async () => {
      await syncParamForms(form.closest("[data-step-panel]"));
    });
  });
  syncPairEditors(form);
  syncListEditors(form);
  form.querySelectorAll("[data-semantic-upload-panel]").forEach(syncSemanticUploadPanel);
  form.querySelectorAll("[data-api-editor]").forEach(refreshApiBlocks);
  syncApiEditors(form);
});

document.querySelectorAll("[data-step-continue]").forEach((button) => {
  button.addEventListener("click", async () => {
    const activeIndex = panels.findIndex((panel) => !panel.hidden);
    const activePanel = panels[activeIndex];
    await flushBuilderState();
    await syncSelectedChoice(activePanel);
    await syncTextInput(activePanel);
    await syncParamForms(activePanel);
    const validationError = requiredStepError(activePanel);
    showStepValidationError(activePanel, validationError);
    if (validationError) {
      return;
    }
    const nextStep = progressSteps[activeIndex + 1];
    if (nextStep) {
      showStep(nextStep.dataset.progressStep);
    }
  });
});

document.querySelectorAll("[data-step-back]").forEach((button) => {
  button.addEventListener("click", () => {
    const activeIndex = panels.findIndex((panel) => !panel.hidden);
    const previousStep = progressSteps[activeIndex - 1];
    if (previousStep) {
      showStep(previousStep.dataset.progressStep);
    }
  });
});

document.querySelectorAll("[data-runner-link], [data-complete-link]").forEach((link) => {
  link.addEventListener("click", async (event) => {
    if (link.matches("[data-complete-link]") && link.getAttribute("aria-disabled") === "true") {
      event.preventDefault();
      return;
    }
    event.preventDefault();
    const activePanel = panels.find((panel) => !panel.hidden);
    await flushBuilderState();
    await syncSelectedChoice(activePanel);
    await syncTextInput(activePanel);
    await syncParamForms(activePanel);
    window.location.href = link.href;
  });
});

