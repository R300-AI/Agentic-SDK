import { postJson } from "../shared/api-client.js";
import { setAdoptionState } from "./adoption-state.js";
import { bindAttachmentPicker } from "./artifact-panel.js";
import { bindInputComposer } from "./input-composer.js";
import { bindNextStepStrip } from "./next-step-strip.js";
import { setResultMessage, setResultTitle, setTrustEvidence, showResultSurface } from "./result-surface.js";
import { showSavePanel } from "./save-panel.js";
import { bindTrustDisclosure } from "./trust-disclosure.js";

const form = document.querySelector("[data-input-composer]");
const runStatus = document.querySelector("[data-run-status]");
const resultThread = document.querySelector("[data-result-thread]");
const resultSurface = document.querySelector("[data-result-surface]");
const resultTitle = document.querySelector("[data-result-title]");
const resultMessage = document.querySelector("[data-result-message]");
const adoptionState = document.querySelector("[data-adoption-state]");
const trustToggle = document.querySelector("[data-trust-toggle]");
const trustPanel = document.querySelector("[data-trust-panel]");
const evidenceList = document.querySelector("[data-evidence-list]");
const saveButton = document.querySelector("[data-save-action]");
const saveStatus = document.querySelector("[data-save-status]");
const attachmentInput = document.querySelector("[data-attachment-input]");
const artifactList = document.querySelector("[data-artifact-list]");
const attachmentStatus = document.querySelector("[data-attachment-status]");
const savePanel = document.querySelector("[data-save-panel]");
const nextStepStrip = document.querySelector("[data-next-step-strip]");

bindAttachmentPicker(attachmentInput, artifactList, attachmentStatus);
bindInputComposer(form, async (payload) => {
	if (runStatus) {
		runStatus.textContent = "正在產生回覆...";
	}
	const result = await postJson("/playground/run/execute", { message: payload?.message || "" });
	if (result.status !== "input_error") {
		showResultSurface(resultThread);
		showResultSurface(resultSurface);
		setResultTitle(resultTitle, result.result?.title || "回覆結果");
		setResultMessage(resultMessage, result.final_message);
		setAdoptionState(adoptionState, result.result?.adoption_level);
		setTrustEvidence(evidenceList, result.result?.evidence);
	}
	if (runStatus) {
		runStatus.textContent = result.status === "completed" ? "已產生回覆。" : result.final_message || "已產生回覆。";
	}
});
bindTrustDisclosure(trustToggle, trustPanel);
bindNextStepStrip(nextStepStrip, { resultMessage, runStatus, savePanel });

saveButton?.addEventListener("click", async () => {
	if (runStatus) {
		runStatus.textContent = "正在儲存...";
	}
	if (saveStatus) {
		saveStatus.textContent = "儲存中...";
	}
	const result = await postJson("/playground/aihub/config/save");
	if (runStatus) {
		runStatus.textContent = result.saved ? "已儲存。" : "儲存失敗。";
	}
	if (saveStatus) {
		saveStatus.textContent = result.saved ? "已儲存" : "儲存失敗";
	}
	showSavePanel(savePanel, result.saved ? "已儲存。" : "儲存失敗。");
});