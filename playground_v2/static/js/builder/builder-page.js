import { postJson } from "../shared/api-client.js";
import { selectChoice } from "./starter-template.js";

const progressSteps = Array.from(document.querySelectorAll("[data-progress-step]"));
const panels = Array.from(document.querySelectorAll("[data-step-panel]"));
const cards = document.querySelectorAll("[data-choice-card]");
const progressCurrent = document.querySelector("[data-progress-current]");
const builderFormStateElement = document.querySelector("[data-builder-form-state]");
let stateQueue = Promise.resolve();

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
  await Promise.all(forms.map((form) => postBuilderState({
    step: form.dataset.stepKey,
    value: Object.fromEntries(new FormData(form).entries()),
  })));
}

function updateConditionalForms(panel) {
  const selectedChoice = panel?.querySelector("[data-choice-card].selected")?.dataset.choiceLabel;
  panel?.querySelectorAll("[data-visible-choices]").forEach((form) => {
    const visibleChoices = form.dataset.visibleChoices.includes("|")
      ? form.dataset.visibleChoices.split("|").map((choice) => choice.trim())
      : [form.dataset.visibleChoices.trim()];
    form.hidden = !visibleChoices.includes(selectedChoice);
  });
}

function updateRangeOutput(range) {
  const output = range.form?.querySelector(`output[for="${range.id}"]`);
  if (output) {
    output.value = range.value;
    output.textContent = range.value;
  }
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
    return row;
  }));
  syncPairEditor(editor);
}

function setFieldValue(field, value) {
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
      .find((card) => card.dataset.choiceLabel === String(choiceLabel));
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
    return { key, value };
  }).filter((pair) => pair.key && pair.value);
  output.value = pairs.map((pair) => `${pair.key} = ${pair.value}`).join("\n");
}

function syncPairEditors(root) {
  root.querySelectorAll("[data-pair-editor]").forEach(syncPairEditor);
}

function clearPairRow(row) {
  row.querySelectorAll("[data-pair-key], [data-pair-value]").forEach((field) => {
    field.value = "";
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
panels.forEach(updateConditionalForms);

cards.forEach((card) => {
  card.addEventListener("click", async () => {
    const panel = card.closest("[data-step-panel]");
    if (panel) {
      selectChoice(panel.querySelectorAll("[data-choice-card]"), card);
      updateConditionalForms(panel);
    }
    await postBuilderState({
      step: card.dataset.stepKey,
      choice: card.dataset.choiceLabel,
    });
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
    const field = event.target.closest?.("[data-pair-key], [data-pair-value]");
    if (field) {
      syncPairEditor(field.closest("[data-pair-editor]"));
    }
  });
  form.addEventListener("change", async (event) => {
    const field = event.target.closest?.("[data-pair-key], [data-pair-value]");
    if (field) {
      syncPairEditor(field.closest("[data-pair-editor]"));
      await syncParamForms(form.closest("[data-step-panel]"));
    }
  });
  form.addEventListener("click", async (event) => {
    const addButton = event.target.closest?.("[data-pair-add]");
    const removeButton = event.target.closest?.("[data-pair-remove]");
    if (addButton) {
      addPairRow(addButton.closest("[data-pair-editor]"));
    }
    if (removeButton) {
      removePairRow(removeButton.closest("[data-pair-editor]"), removeButton.closest("[data-pair-row]"));
      await syncParamForms(form.closest("[data-step-panel]"));
    }
  });
  form.querySelectorAll("input, textarea, select").forEach((field) => {
    if (field.matches("[data-pair-key], [data-pair-value], [data-pair-output]")) {
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
});

document.querySelectorAll("[data-step-continue]").forEach((button) => {
  button.addEventListener("click", async () => {
    const activeIndex = panels.findIndex((panel) => !panel.hidden);
    await flushBuilderState();
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
    await syncTextInput(activePanel);
    await syncParamForms(activePanel);
    window.location.href = link.href;
  });
});