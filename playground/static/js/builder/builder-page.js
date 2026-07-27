import { postJson } from "../shared/api-client.js";
import { selectChoice } from "./starter-template.js";

const progressSteps = Array.from(document.querySelectorAll("[data-progress-step]"));
const panels = Array.from(document.querySelectorAll("[data-step-panel]"));
const cards = document.querySelectorAll("[data-choice-card]");
const progressCurrent = document.querySelector("[data-progress-current]");
const builderFormStateElement = document.querySelector("[data-builder-form-state]");
let stateQueue = Promise.resolve();

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
    hybrid_later: {},
  },
  output_format: {
    free_text: {},
    interactive: {},
  },
  failure_policy: {
    clarify: {},
    re_retrieve: { retrieve_policy: ["keyword", "semantic", "hybrid_later"] },
    safe_answer: {},
    escalate: {},
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

async function postBuilderState(payload) {
  const task = stateQueue.catch(() => {}).then(async () => {
    const response = await postJson("/playground/builder/state", payload);
    updateSummary(response.workflow_summary);
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

function setPairEditorValue(output, value) {
  const editor = output.closest("[data-pair-editor]");
  const list = editor?.querySelector("[data-pair-list]");
  const sourceRow = editor?.querySelector("[data-pair-row]");
  if (!editor || !list || !sourceRow) {
    output.value = String(value || "");
    return;
  }
  const pairs = parsePairText(value);
  const rows = pairs.length ? pairs : [{ key: "", value: "" }];
  list.replaceChildren(...rows.map((pair) => {
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
  }));
  syncPairEditor(editor);
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
  const normalized = String(value || "").trim();
  const legacyMap = {
    "文字輸入": "文字選項 / string",
    "選單": "文字選項 / string",
    "按鈕": "是/否確認 / boolean",
    "文字內容": "文字選項 / string",
    "文字選項": "文字",
    "文字選項 / string": "文字",
    "文字 / string": "文字",
    "數字資料": "數字",
    "數字資料 / number": "數字",
    "數字 / number": "數字",
    "是/否確認": "是/否",
    "是/否確認 / boolean": "是/否",
    "是/否 / boolean": "是/否",
    "清單 / array": "清單",
  };
  return legacyMap[normalized] || normalized;
}

function setFieldValue(field, value) {
  if (field.matches("[data-api-output]")) {
    setApiEditorValue(field, value);
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
  const legacyNames = new Map([
    ["[data-api-trigger]", "interaction_trigger"],
    ["[data-api-method]", "api_method"],
    ["[data-api-url]", "api_url"],
    ["[data-pair-output]", "component_fields"],
  ]);
  legacyNames.forEach((name, selector) => {
    const field = block.querySelector(selector);
    if (!field) {
      return;
    }
    if (index === 0) {
      field.name = name;
    } else {
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

function addPairRow(editor) {
  const list = editor.querySelector("[data-pair-list]");
  const sourceRow = editor.querySelector("[data-pair-row]");
  if (!list || !sourceRow) {
    return;
  }
  const row = sourceRow.cloneNode(true);
  clearPairRow(row);
  list.append(row);
  row.querySelector("[data-pair-key]")?.focus();
  syncPairEditor(editor);
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
applyChoiceDependencies();
panels.forEach(updateConditionalForms);

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
    const apiField = event.target.closest?.("[data-api-trigger], [data-api-url]");
    if (apiField) {
      syncApiEditor(apiField.closest("[data-api-editor]"));
    }
  });
  form.addEventListener("change", async (event) => {
    const field = event.target.closest?.("[data-pair-key], [data-pair-value], [data-pair-type]");
    if (field) {
      syncPairEditor(field.closest("[data-pair-editor]"));
      syncApiEditor(field.closest("[data-api-editor]"));
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
    const addApiButton = event.target.closest?.("[data-api-add]");
    const removeApiButton = event.target.closest?.("[data-api-remove]");
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
    if (removeApiButton) {
      removeApiBlock(removeApiButton.closest("[data-api-editor]"), removeApiButton.closest("[data-api-block]"));
      await syncParamForms(form.closest("[data-step-panel]"));
    }
  });
  form.querySelectorAll("input, textarea, select").forEach((field) => {
    if (field.matches("[data-pair-key], [data-pair-value], [data-pair-type], [data-pair-output], [data-api-trigger], [data-api-method], [data-api-url], [data-api-output]")) {
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
  form.querySelectorAll("[data-api-editor]").forEach(refreshApiBlocks);
  syncApiEditors(form);
});

document.querySelectorAll("[data-step-continue]").forEach((button) => {
  button.addEventListener("click", async () => {
    const activeIndex = panels.findIndex((panel) => !panel.hidden);
    await flushBuilderState();
    await syncSelectedChoice(panels[activeIndex]);
    await syncTextInput(panels[activeIndex]);
    await syncParamForms(panels[activeIndex]);
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

document.querySelectorAll("[data-runner-link]").forEach((link) => {
  link.addEventListener("click", async (event) => {
    event.preventDefault();
    const activePanel = panels.find((panel) => !panel.hidden);
    await flushBuilderState();
    await syncSelectedChoice(activePanel);
    await syncTextInput(activePanel);
    await syncParamForms(activePanel);
    window.location.href = link.href;
  });
});