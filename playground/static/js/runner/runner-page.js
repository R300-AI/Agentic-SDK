import { postJson, postJsonStream } from "../shared/api-client.js";
import { bindAttachmentPicker } from "./artifact-panel.js";
import { bindCodePreview } from "./code-preview.js?v=preview-feedback-v1";
import { bindInputComposer } from "./input-composer.js";
import { clearProcessEvents, setProcessEvents, setResultMessage, setToolCallPanels, showLiveProcessEvent, showResultSurface, streamResultMarkdown } from "./result-surface.js";
import { showSavePanel } from "./save-panel.js";

const form = document.querySelector("[data-input-composer]");
const runStatus = document.querySelector("[data-run-status]");
const resultThread = document.querySelector("[data-result-thread]");
const resultSurface = document.querySelector("[data-result-surface]");
const userMessage = document.querySelector("[data-user-message]");
const emptyMessage = document.querySelector("[data-empty-message]");
const starterQuestions = document.querySelector("[data-starter-questions]");
const saveButton = document.querySelector("[data-save-action]");
const saveStatus = document.querySelector("[data-save-status]");
const attachmentInput = document.querySelector("[data-attachment-input]");
const artifactList = document.querySelector("[data-artifact-list]");
const attachmentStatus = document.querySelector("[data-attachment-status]");
const savePanel = document.querySelector("[data-save-panel]");
const codePreviewToggles = document.querySelectorAll("[data-code-preview-open]");
const codePreviewModal = document.querySelector("[data-code-preview-modal]");
const workflowInfoOpen = document.querySelector("[data-workflow-info-open]");
const workflowInfoModal = document.querySelector("[data-workflow-info-modal]");
const workflowInfoCloseButtons = workflowInfoModal?.querySelectorAll("[data-workflow-info-close]") || [];
const workflowInfoForm = document.querySelector("[data-workflow-info-form]");
const workflowInfoNameInput = document.querySelector("[data-workflow-info-name-input]");
const workflowInfoDescriptionInput = document.querySelector("[data-workflow-info-description-input]");
const workflowInfoSubmit = document.querySelector("[data-workflow-info-submit]");
const runnerPage = document.querySelector("[data-page='runner']");
const usesSemanticRetrieve = runnerPage?.dataset.semanticRetrieve === "true";
const runnerSidebar = document.querySelector("[data-runner-sidebar]");
const sidebarToggle = document.querySelector("[data-sidebar-toggle]");
const saveRequiresLogin = runnerPage?.dataset.saveRequiresLogin === "true";
const autoSaveAfterLogin = runnerPage?.dataset.autoSaveAfterLogin === "true";
const saveLoginModal = document.querySelector("[data-save-login-modal]");
const saveLoginCloseButtons = saveLoginModal?.querySelectorAll("[data-save-login-close]") || [];
const saveLoginForm = document.querySelector("[data-save-login-form]");
const saveLoginUsername = document.querySelector("[data-save-login-username]");
const saveLoginPassword = document.querySelector("[data-save-login-password]");
const saveLoginError = document.querySelector("[data-save-login-error]");
const saveLoginSubmit = document.querySelector("[data-save-login-submit]");
const submitButton = form?.querySelector("button[type='submit']");
const messageInput = form?.querySelector("textarea[name='message']");
const workflowNameTargets = document.querySelectorAll("[data-workflow-name]");
const sideWorkflowTitleDisplay = document.querySelector("[data-side-workflow-title-display]");
const sideWorkflowTitleForm = document.querySelector("[data-side-workflow-title-form]");
const sideWorkflowTitleInput = document.querySelector("[data-side-workflow-title-input]");
const workflowDescriptionTargets = document.querySelectorAll("[data-workflow-description]");
const workflowDescriptionDisplay = document.querySelector("[data-workflow-description-display]");
const workflowDescriptionForm = document.querySelector("[data-workflow-description-form]");
const workflowDescriptionInput = document.querySelector("[data-workflow-description-input]");
const initializationOverlay = document.querySelector("[data-initialization-overlay]");
const initializationMessage = document.querySelector("[data-initialization-message]");
const initializationBar = document.querySelector("[data-initialization-bar]");
const initializationCount = document.querySelector("[data-initialization-count]");
let activeRunId = 0;
let workflowName = sideWorkflowTitleInput?.value.trim() || sideWorkflowTitleDisplay?.textContent?.trim() || "";
let workflowDescription = workflowDescriptionInput?.value.trim() || workflowDescriptionDisplay?.textContent?.trim() || "";
let workflowRenameRequest = null;
let workflowDescriptionRequest = null;
const workflowDescriptionPlaceholder = workflowDescriptionInput?.getAttribute("placeholder") || workflowDescriptionDisplay?.dataset.placeholder || "";
let lastSaveTrigger = null;
let runnerInitialized = !initializationOverlay;
let knowledgeUploadInFlight = false;
const initialSaveStatusText = saveStatus?.textContent?.trim() || "";
let savedWorkflowName = initialSaveStatusText === "尚未儲存" ? null : workflowName;
let savedWorkflowDescription = initialSaveStatusText === "尚未儲存" ? null : workflowDescription;
let lastStableSaveStatusText = initialSaveStatusText && initialSaveStatusText !== "儲存中..." ? initialSaveStatusText : "已儲存";

function setSidebarCollapsed(collapsed) {
	if (!runnerPage || !runnerSidebar || !sidebarToggle) {
		return;
	}
	runnerPage.classList.toggle("sidebar-collapsed", collapsed);
	runnerSidebar.classList.toggle("is-collapsed", collapsed);
	sidebarToggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
	sidebarToggle.setAttribute("aria-label", collapsed ? "展開側欄" : "收合側欄");
	try {
		window.localStorage.setItem("runnerSidebarCollapsed", collapsed ? "true" : "false");
	} catch {
		// Ignore storage failures in private or locked-down browsing contexts.
	}
}

function initializeSidebar() {
	if (!runnerPage || !runnerSidebar || !sidebarToggle) {
		return;
	}
	let collapsed = false;
	try {
		collapsed = window.localStorage.getItem("runnerSidebarCollapsed") === "true";
	} catch {
		collapsed = false;
	}
	setSidebarCollapsed(collapsed);
	sidebarToggle.addEventListener("click", () => {
		setSidebarCollapsed(!runnerPage.classList.contains("sidebar-collapsed"));
	});
}

function hasWorkflowMetadataChanges() {
	return savedWorkflowName === null
		|| savedWorkflowDescription === null
		|| workflowName !== savedWorkflowName
		|| workflowDescription !== savedWorkflowDescription;
}

function refreshSaveStatus() {
	if (!saveStatus) {
		return;
	}
	saveStatus.textContent = hasWorkflowMetadataChanges() ? "尚未儲存" : lastStableSaveStatusText;
}

function recordSavedWorkflowMetadata(statusText = "已儲存") {
	savedWorkflowName = workflowName;
	savedWorkflowDescription = workflowDescription;
	lastStableSaveStatusText = statusText;
}

function setRunnerChatEnabled(enabled) {
	if (submitButton) {
		submitButton.disabled = !enabled;
	}
	if (messageInput) {
		messageInput.disabled = !enabled;
	}
	if (attachmentInput) {
		attachmentInput.disabled = !enabled;
	}
	document.querySelectorAll("[data-starter-question-button]").forEach((button) => {
		button.disabled = !enabled;
	});
}

function updateInitializationProgress(event) {
	const completed = Number(event?.completed || 0);
	const total = Number(event?.total || 0);
	const percent = total > 0 ? Math.round((completed / total) * 100) : 0;
	if (initializationMessage) {
		initializationMessage.textContent = event?.message || "正在載入所需內容...";
	}
	if (initializationBar) {
		initializationBar.style.width = `${Math.max(0, Math.min(100, percent))}%`;
	}
	if (initializationCount) {
		initializationCount.textContent = `${completed} / ${total}`;
	}
}

function finishInitialization() {
	runnerInitialized = true;
	setRunnerChatEnabled(true);
	if (initializationOverlay) {
		initializationOverlay.classList.add("is-complete");
		window.setTimeout(() => {
			initializationOverlay.hidden = true;
		}, 180);
	}
}

function failInitialization(message) {
	runnerInitialized = false;
	setRunnerChatEnabled(false);
	if (initializationOverlay) {
		initializationOverlay.classList.add("has-error");
	}
	if (initializationMessage) {
		initializationMessage.textContent = message || "準備對話時發生問題，請回到設定頁檢查。";
	}
}

async function initializeRunner() {
	if (!initializationOverlay) {
		return;
	}
	setRunnerChatEnabled(false);
	try {
		await postJsonStream("/playground/run/initialize/stream", {}, async (event) => {
			updateInitializationProgress(event);
			if (event.type === "final") {
				if (event.ready) {
					finishInitialization();
				} else {
					failInitialization(event.error || event.message);
				}
			}
		});
	} catch (error) {
		failInitialization(error.message || "準備對話時發生問題，請稍後再試。")
	}
}

function actionReplyFrom(result) {
	if (result.status === "input_error" || result.status === "configuration_error") {
		return "";
	}
	const message = String(result.final_message || "").trim();
	return message.startsWith("[workflow ended with error]") ? "" : message;
}

function executionStatusFrom(result) {
	if (result.status === "completed") {
		return "已產生回覆。";
	}
	if (result.status === "aborted") {
		return "流程已中止。";
	}
	return result.final_message || result.error || "已完成。";
}

function setDebugMessages(element, messages) {
	if (!element) {
		return;
	}
	const entries = Array.isArray(messages) ? messages.filter(Boolean) : [];
	element.textContent = entries.join(" · ");
	element.hidden = entries.length === 0;
}

function debugMessagesFrom(result) {
	if (Array.isArray(result.debug_messages)) {
		return result.debug_messages;
	}
	const notes = [];
	if (result.status === "completed") {
		notes.push("Action 已完成");
	} else if (result.status === "aborted") {
		notes.push("流程已中止");
	} else if (result.status === "configuration_error") {
		notes.push(result.final_message || "模型端點尚未部署");
	} else if (result.status === "fallback") {
		notes.push(result.error || "執行失敗");
	} else if (result.status === "input_error") {
		notes.push(result.final_message || "請先輸入內容");
	}

	if (result.result?.adoption_level) {
		notes.push(result.result.adoption_level);
	}
	if (Array.isArray(result.result?.evidence)) {
		notes.push(...result.result.evidence);
	}
	return notes.filter(Boolean);
}

function processEventsFrom(result) {
	if (!Array.isArray(result.process_events)) {
		return [];
	}
	return result.process_events.filter((event) => event?.title || event?.description);
}

function toolCallPanelsFrom(result) {
	if (Array.isArray(result.tool_call_panels)) {
		return result.tool_call_panels;
	}
	if (Array.isArray(result.result?.tool_call_panels)) {
		return result.result.tool_call_panels;
	}
	return [];
}

function scrollResultThread() {
	if (resultThread) {
		resultThread.scrollTop = resultThread.scrollHeight;
	}
}

function avatarTextFromWorkflowName(name) {
	const value = String(name || "").trim();
	if (!value) {
		return "A";
	}
	const first = Array.from(value)[0] || "A";
	if (/^[A-Za-z]$/.test(first)) {
		const letters = Array.from(value.match(/[A-Za-z]/g) || []).slice(0, 2).join("");
		return (letters || first).toUpperCase();
	}
	return first;
}

function renderAgentAvatars() {
	const avatarText = avatarTextFromWorkflowName(workflowName);
	document.querySelectorAll("[data-agent-avatar]").forEach((element) => {
		element.textContent = avatarText;
	});
}

function renderWorkflowName(nextName) {
	workflowName = String(nextName || "").trim() || workflowName;
	workflowNameTargets.forEach((element) => {
		element.textContent = workflowName;
	});
	renderAgentAvatars();
	if (sideWorkflowTitleInput) {
		sideWorkflowTitleInput.value = workflowName;
	}
}

function renderWorkflowDescription(nextDescription) {
	workflowDescription = String(nextDescription || "").trim();
	workflowDescriptionTargets.forEach((element) => {
		element.textContent = workflowDescription;
		element.classList.toggle("is-placeholder", !workflowDescription);
	});
	if (workflowDescriptionInput) {
		workflowDescriptionInput.value = workflowDescription;
	}
}

function openSideWorkflowTitleEditor() {
	if (!sideWorkflowTitleDisplay || !sideWorkflowTitleForm || !sideWorkflowTitleInput) {
		return;
	}
	sideWorkflowTitleDisplay.hidden = true;
	sideWorkflowTitleForm.hidden = false;
	sideWorkflowTitleInput.value = workflowName;
	queueMicrotask(() => {
		sideWorkflowTitleInput.focus();
		sideWorkflowTitleInput.select();
	});
}

function closeSideWorkflowTitleEditor() {
	if (!sideWorkflowTitleDisplay || !sideWorkflowTitleForm || !sideWorkflowTitleInput) {
		return;
	}
	sideWorkflowTitleForm.hidden = true;
	sideWorkflowTitleDisplay.hidden = false;
	sideWorkflowTitleInput.value = workflowName;
}

function openWorkflowDescriptionEditor() {
	if (!workflowDescriptionDisplay || !workflowDescriptionForm || !workflowDescriptionInput) {
		return;
	}
	workflowDescriptionDisplay.hidden = true;
	workflowDescriptionForm.hidden = false;
	workflowDescriptionInput.value = workflowDescription;
	queueMicrotask(() => {
		workflowDescriptionInput.focus();
		workflowDescriptionInput.select();
	});
}

function closeWorkflowDescriptionEditor() {
	if (!workflowDescriptionDisplay || !workflowDescriptionForm || !workflowDescriptionInput) {
		return;
	}
	workflowDescriptionForm.hidden = true;
	workflowDescriptionDisplay.hidden = false;
	workflowDescriptionInput.value = workflowDescription;
}

async function commitWorkflowName() {
	const activeInput = sideWorkflowTitleInput;
	if (!activeInput || workflowRenameRequest) {
		return workflowRenameRequest;
	}
	const nextName = activeInput.value.trim();
	if (!nextName || nextName === workflowName) {
		closeSideWorkflowTitleEditor();
		return null;
	}
	workflowRenameRequest = (async () => {
		if (sideWorkflowTitleInput) {
			sideWorkflowTitleInput.disabled = true;
		}
		if (runStatus) {
			runStatus.textContent = "正在更新 Agent 名稱...";
		}
		let result;
		try {
			result = await postJson("/playground/run/name", { name: nextName });
		} catch (error) {
			result = { updated: false, error: error.message || "更新 Agent 名稱失敗。" };
		}
		if (sideWorkflowTitleInput) {
			sideWorkflowTitleInput.disabled = false;
		}
		if (!result.updated) {
			activeInput.focus();
			activeInput.select();
			if (runStatus) {
				runStatus.textContent = result.error || "更新 Agent 名稱失敗。";
			}
			showSavePanel(savePanel, result.error || "更新 Agent 名稱失敗。");
			return;
		}
		renderWorkflowName(result.workflow_summary?.name || nextName);
		closeSideWorkflowTitleEditor();
		refreshSaveStatus();
		if (runStatus) {
			runStatus.textContent = "Agent 名稱已更新。";
		}
	})().finally(() => {
		workflowRenameRequest = null;
	});
	return workflowRenameRequest;
}

async function commitWorkflowDescription() {
	if (!workflowDescriptionInput || workflowDescriptionRequest) {
		return workflowDescriptionRequest;
	}
	const nextDescription = workflowDescriptionInput.value.trim();
	if (nextDescription === workflowDescription) {
		closeWorkflowDescriptionEditor();
		return null;
	}
	workflowDescriptionRequest = (async () => {
		workflowDescriptionInput.disabled = true;
		if (runStatus) {
			runStatus.textContent = "正在更新 workflow description...";
		}
		let result;
		try {
			result = await postJson("/playground/run/description", { description: nextDescription });
		} catch (error) {
			result = { updated: false, error: error.message || "更新 workflow description 失敗。" };
		}
		workflowDescriptionInput.disabled = false;
		if (!result.updated) {
			workflowDescriptionInput.focus();
			workflowDescriptionInput.select();
			if (runStatus) {
				runStatus.textContent = result.error || "更新 workflow description 失敗。";
			}
			showSavePanel(savePanel, result.error || "更新 workflow description 失敗。");
			return;
		}
		renderWorkflowDescription(result.description ?? nextDescription);
		closeWorkflowDescriptionEditor();
		refreshSaveStatus();
		if (runStatus) {
			runStatus.textContent = "workflow description 已更新。";
		}
	})().finally(() => {
		workflowDescriptionRequest = null;
	});
	return workflowDescriptionRequest;
}

function setStarterContentHidden(hidden) {
	if (emptyMessage) {
		emptyMessage.hidden = hidden;
	}
	if (starterQuestions) {
		starterQuestions.hidden = hidden;
	}
}

function animateComposerToChatPosition() {
	if (!form || !runnerPage || window.matchMedia?.("(prefers-reduced-motion: reduce)").matches) {
		setStarterContentHidden(true);
		runnerPage?.classList.add("has-chat-started");
		return;
	}
	const start = form.getBoundingClientRect();
	setStarterContentHidden(true);
	runnerPage.classList.add("has-chat-started");
	const end = form.getBoundingClientRect();
	const deltaX = start.left - end.left;
	const deltaY = start.top - end.top;
	if (Math.abs(deltaX) < 1 && Math.abs(deltaY) < 1) {
		return;
	}
	form.style.transition = "none";
	form.style.transform = `translate(${deltaX}px, ${deltaY}px)`;
	form.style.willChange = "transform";
	form.getBoundingClientRect();
	window.requestAnimationFrame(() => {
		form.style.transition = "transform 420ms cubic-bezier(0.2, 0, 0, 1)";
		form.style.transform = "translate(0, 0)";
		window.setTimeout(() => {
			form.style.transition = "";
			form.style.transform = "";
			form.style.willChange = "";
		}, 460);
	});
}

function hideStarterQuestions() {
	if (!runnerPage?.classList.contains("has-chat-started")) {
		animateComposerToChatPosition();
		return;
	}
	setStarterContentHidden(true);
}

async function executeRunnerStream(requestPayload, runId, onLiveProcess) {
	if (!window.ReadableStream || !window.TextDecoder) {
		throw new Error("Streaming is not supported.");
	}
	let finalResult = null;
	await postJsonStream("/playground/run/execute/stream", requestPayload, async (event) => {
		if (runId !== activeRunId) {
			return;
		}
		if (event.type === "process" && event.event) {
			onLiveProcess?.(event.event);
		}
		if (event.type === "final") {
			finalResult = event.result;
		}
	});
	if (!finalResult) {
		throw new Error("Streaming response ended before the final result.");
	}
	return finalResult;
}

function toolSubmissionDisplay(submission) {
	const values = submission?.arguments && typeof submission.arguments === "object" ? submission.arguments : {};
	const text = Object.entries(values).map(([key, value]) => `${key}: ${value}`).join("，");
	return text ? `送出選擇：${text}` : "送出選擇";
}

function appendUserMessage(text) {
	if (!resultThread || !userMessage) {
		return null;
	}
	const message = userMessage.cloneNode(true);
	const textElement = message.querySelector("[data-user-message-text]");
	if (textElement) {
		textElement.textContent = text || "（空白訊息）";
	}
	message.hidden = false;
	resultThread.append(message);
	return message;
}

function appendAssistantSurface() {
	if (!resultThread || !resultSurface) {
		return null;
	}
	const surface = resultSurface.cloneNode(true);
	surface.hidden = false;
	resultThread.append(surface);
	return {
		surface,
		bubble: surface.querySelector("[data-result-bubble]"),
		processTrace: surface.querySelector("[data-process-trace]"),
		message: surface.querySelector("[data-result-message]"),
		toolCallPanels: surface.querySelector("[data-tool-call-panels]"),
		debugStatus: surface.querySelector("[data-debug-status]"),
	};
}

function setSurfaceBusy(surface, isBusy) {
	if (surface) {
		surface.setAttribute("aria-busy", isBusy ? "true" : "false");
	}
}

function openSaveLoginModal() {
	if (!saveLoginModal) {
		return;
	}
	lastSaveTrigger = saveButton;
	if (saveLoginError) {
		saveLoginError.hidden = true;
		saveLoginError.textContent = "";
	}
	saveLoginModal.hidden = false;
	saveLoginModal.classList.add("open");
	saveLoginModal.dataset.open = "true";
	queueMicrotask(() => saveLoginUsername?.focus());
}

function closeSaveLoginModal() {
	if (!saveLoginModal) {
		return;
	}
	saveLoginModal.hidden = true;
	saveLoginModal.classList.remove("open");
	saveLoginModal.dataset.open = "false";
	lastSaveTrigger?.focus?.();
}

function openWorkflowInfoModal() {
	if (!workflowInfoModal) {
		return;
	}
	lastSaveTrigger = workflowInfoOpen;
	if (workflowInfoNameInput) {
		workflowInfoNameInput.value = workflowName;
	}
	if (workflowInfoDescriptionInput) {
		workflowInfoDescriptionInput.value = workflowDescription;
	}
	workflowInfoModal.hidden = false;
	workflowInfoModal.classList.add("open");
	workflowInfoModal.dataset.open = "true";
	queueMicrotask(() => workflowInfoNameInput?.focus());
}

function closeWorkflowInfoModal() {
	if (!workflowInfoModal) {
		return;
	}
	workflowInfoModal.hidden = true;
	workflowInfoModal.classList.remove("open");
	workflowInfoModal.dataset.open = "false";
	lastSaveTrigger?.focus?.();
}

async function applyWorkflowInfo() {
	const nextName = workflowInfoNameInput?.value.trim() || workflowName;
	const nextDescription = workflowInfoDescriptionInput?.value.trim() || "";
	[workflowInfoNameInput, workflowInfoDescriptionInput, workflowInfoSubmit].forEach((element) => {
		if (element) {
			element.disabled = true;
		}
	});
	let result;
	try {
		result = await postJson("/playground/run/metadata", { name: nextName, description: nextDescription });
	} catch (error) {
		result = { updated: false, error: error.message || "更新 Agent 基本資料失敗。" };
	} finally {
		[workflowInfoNameInput, workflowInfoDescriptionInput, workflowInfoSubmit].forEach((element) => {
			if (element) {
				element.disabled = false;
			}
		});
	}
	if (!result.updated) {
		showSavePanel(savePanel, result.error || "更新 Agent 基本資料失敗。");
		return false;
	}
	renderWorkflowName(result.workflow_summary?.name || nextName);
	renderWorkflowDescription(result.description ?? nextDescription);
	refreshSaveStatus();
	return true;
}

async function saveCurrentWorkflow() {
	let result;
	try {
		result = await postJson("/playground/aihub/config/save");
	} catch (error) {
		result = { saved: false, error: error.message || "儲存失敗。" };
	}
	return result;
}

async function flushWorkflowMetadataEdits() {
	if (workflowRenameRequest) {
		await workflowRenameRequest;
	}
	await commitWorkflowName();
	if (workflowRenameRequest) {
		await workflowRenameRequest;
	}
	if (workflowDescriptionRequest) {
		await workflowDescriptionRequest;
	}
	await commitWorkflowDescription();
	if (workflowDescriptionRequest) {
		await workflowDescriptionRequest;
	}
	return true;
}

async function loginAiHubSession(username, password) {
	let result;
	try {
		result = await postJson("/playground/aihub/auth/login", { username, password });
	} catch (error) {
		result = { authenticated: false, error: error.message || "登入失敗。" };
	}
	return result;
}

function saveNeedsLogin(result) {
	const error = String(result?.error || "");
	return result?.reauthentication_required === true || error === "Current mode cannot save to AI Hub." || error === "AI Hub login is required before saving.";
}

async function refreshAiHubSession() {
	if (!saveLoginModal || saveRequiresLogin) {
		return;
	}
	let result;
	try {
		result = await postJson("/playground/aihub/session/refresh");
	} catch (error) {
		return;
	}
	if (result?.reauthentication_required) {
		openSaveLoginModal();
	}
}

bindAttachmentPicker(attachmentInput, artifactList, attachmentStatus);
bindCodePreview(codePreviewToggles, codePreviewModal);
initializeSidebar();
renderWorkflowDescription(workflowDescriptionInput?.value || workflowDescription);
workflowInfoOpen?.addEventListener("click", openWorkflowInfoModal);
workflowInfoCloseButtons.forEach((button) => button.addEventListener("click", closeWorkflowInfoModal));
workflowInfoForm?.addEventListener("submit", async (event) => {
	event.preventDefault();
	if (await applyWorkflowInfo()) {
		closeWorkflowInfoModal();
	}
});
sideWorkflowTitleDisplay?.addEventListener("click", () => {
	openSideWorkflowTitleEditor();
});
sideWorkflowTitleForm?.addEventListener("submit", async (event) => {
	event.preventDefault();
	await commitWorkflowName();
});
sideWorkflowTitleInput?.addEventListener("keydown", async (event) => {
	if (event.key === "Escape") {
		event.preventDefault();
		closeSideWorkflowTitleEditor();
		sideWorkflowTitleDisplay?.focus();
		return;
	}
	if (event.key === "Enter") {
		event.preventDefault();
		await commitWorkflowName();
		sideWorkflowTitleDisplay?.focus();
	}
});
sideWorkflowTitleInput?.addEventListener("blur", async () => {
	await commitWorkflowName();
});
workflowDescriptionDisplay?.addEventListener("click", () => {
	openWorkflowDescriptionEditor();
});
workflowDescriptionForm?.addEventListener("submit", async (event) => {
	event.preventDefault();
	await commitWorkflowDescription();
});
workflowDescriptionInput?.addEventListener("keydown", async (event) => {
	if (event.key === "Escape") {
		event.preventDefault();
		closeWorkflowDescriptionEditor();
		workflowDescriptionDisplay?.focus();
		return;
	}
	if (event.key === "Enter" && !event.shiftKey) {
		event.preventDefault();
		await commitWorkflowDescription();
		workflowDescriptionDisplay?.focus();
	}
});
workflowDescriptionInput?.addEventListener("blur", async () => {
	await commitWorkflowDescription();
});

async function runWorkflow(payload, { displayMessage, showUserMessage = true } = {}) {
	if (!runnerInitialized) {
		showSavePanel(savePanel, "Agent 還在初始化，完成後才能開始對話。");
		return;
	}
	const runId = ++activeRunId;
	const prompt = String(payload?.message || "").trim();
	const submittedToolCall = payload?.tool_call_submission || null;
	const requestMessage = prompt || (submittedToolCall ? toolSubmissionDisplay(submittedToolCall) : "");
	const requestPayload = { message: requestMessage };
	if (Array.isArray(payload?.attachments) && payload.attachments.length) {
		requestPayload.attachments = payload.attachments;
	}
	if (submittedToolCall) {
		requestPayload.tool_call_submission = submittedToolCall;
	}
	hideStarterQuestions();
	if (showUserMessage) {
		appendUserMessage(displayMessage || prompt || "（空白訊息）");
	}
	const assistant = appendAssistantSurface();
	if (!assistant) {
		return;
	}
	if (runStatus) {
		runStatus.textContent = "正在產生回覆...";
	}
	showResultSurface(resultThread);
	setSurfaceBusy(assistant.surface, true);
	if (assistant.bubble) {
		assistant.bubble.hidden = false;
		assistant.bubble.classList.add("is-running");
	}
	setDebugMessages(assistant.debugStatus, []);
	setResultMessage(assistant.message, "");
	setToolCallPanels(assistant.toolCallPanels, []);
	let liveProcessShown = false;
	clearProcessEvents(assistant.processTrace);
	if (submitButton) {
		submitButton.disabled = true;
	}
	let result;
	try {
		result = await executeRunnerStream(requestPayload, runId, (event) => {
			liveProcessShown = true;
			if (runStatus && event?.title) {
				runStatus.textContent = event.title;
			}
			showLiveProcessEvent(assistant.processTrace, event, { onUpdate: scrollResultThread });
		});
	} catch (error) {
		try {
			result = await postJson("/playground/run/execute", requestPayload);
		} catch (fallbackError) {
			result = {
				status: "fallback",
				final_message: "暫時無法產生回覆。",
				error: fallbackError.message || error.message,
				debug_messages: ["執行：前端送出或接收回應失敗。"],
				process_events: [{ title: "連線檢查", description: "送出或接收回應時發生問題，尚未取得可輸出的內容。" }],
			};
		}
	}
	if (runId !== activeRunId) {
		assistant.bubble?.classList.remove("is-running");
		return;
	}
	const actionReply = actionReplyFrom(result);
	const debugMessages = debugMessagesFrom(result);
	const finalProcessEvents = processEventsFrom(result);
	const finalToolCallPanels = toolCallPanelsFrom(result);
	if (actionReply || finalToolCallPanels.length || debugMessages.length || finalProcessEvents.length) {
		showResultSurface(resultThread);
		showResultSurface(assistant.surface);
		if (assistant.bubble) {
			assistant.bubble.hidden = !(actionReply || finalToolCallPanels.length || finalProcessEvents.length);
		}
		if (finalProcessEvents.length) {
			if (runStatus) {
				runStatus.textContent = "處理過程已完成";
			}
			setProcessEvents(assistant.processTrace, finalProcessEvents, {
				collapsible: true,
				latestOnly: true,
				preserveOpen: true,
				onUpdate: scrollResultThread,
			});
		} else {
			clearProcessEvents(assistant.processTrace);
		}
		if (actionReply) {
			if (runStatus) {
				runStatus.textContent = "正在輸出回覆...";
			}
			await streamResultMarkdown(assistant.message, actionReply, {
				onUpdate: scrollResultThread,
			});
		} else {
			setResultMessage(assistant.message, "");
		}
		setToolCallPanels(assistant.toolCallPanels, finalToolCallPanels);
		if (!finalProcessEvents.length) {
			setDebugMessages(assistant.debugStatus, debugMessages);
		}
		scrollResultThread();
	} else {
		if (assistant.bubble) {
			assistant.bubble.hidden = true;
		}
		clearProcessEvents(assistant.processTrace);
		setResultMessage(assistant.message, "");
		setToolCallPanels(assistant.toolCallPanels, []);
		setDebugMessages(assistant.debugStatus, []);
	}
	if (runStatus) {
		runStatus.textContent = executionStatusFrom(result);
	}
	assistant.bubble?.classList.remove("is-running");
	setSurfaceBusy(assistant.surface, false);
	if (submitButton && runId === activeRunId) {
		submitButton.disabled = false;
	}
}

bindInputComposer(form, async (payload) => {
	await runWorkflow(payload);
});

attachmentInput?.addEventListener("change", async () => {
	if (!usesSemanticRetrieve || !attachmentInput.files?.length) {
		return;
	}
	const body = new FormData();
	Array.from(attachmentInput.files).forEach((file) => body.append("files", file));
	knowledgeUploadInFlight = true;
	attachmentInput.disabled = true;
	if (attachmentStatus) {
		attachmentStatus.textContent = "正在加入知識庫...";
	}
	try {
		const response = await fetch("/playground/run/knowledge/uploads", { method: "POST", body });
		const result = await response.json();
		if (!response.ok || !result.updated) {
			throw new Error(result.error || "知識庫檔案上傳失敗。");
		}
		if (attachmentStatus) {
			attachmentStatus.textContent = `已加入知識庫 ${result.uploaded_files.length} 個檔案；儲存 Agent 後會一併保存。`;
		}
	} catch (error) {
		if (attachmentStatus) {
			attachmentStatus.textContent = error.message || "知識庫檔案上傳失敗。";
		}
	} finally {
		knowledgeUploadInFlight = false;
		attachmentInput.disabled = false;
	}
});

starterQuestions?.addEventListener("click", (event) => {
	const button = event.target.closest?.("[data-starter-question-button]");
	if (!button || !messageInput) {
		return;
	}
	messageInput.value = button.textContent?.trim() || "";
	messageInput.focus();
	messageInput.setSelectionRange(messageInput.value.length, messageInput.value.length);
});

resultThread?.addEventListener("runner:tool-call-submit", async (event) => {
	const submission = event.detail || {};
	try {
		await runWorkflow(
			{ message: "", tool_call_submission: submission },
			{ displayMessage: toolSubmissionDisplay(submission), showUserMessage: false },
		);
	} finally {
		event.target?.dispatchEvent(new CustomEvent("runner:tool-call-complete"));
	}
});

saveButton?.addEventListener("click", async () => {
	if (knowledgeUploadInFlight) {
		showSavePanel(savePanel, "知識庫檔案仍在上傳，請完成後再儲存 Agent。")
		return;
	}
	const readyToSave = await flushWorkflowMetadataEdits();
	if (!readyToSave) {
		showSavePanel(savePanel, "請先完成名稱或 description 的更新。");
		return;
	}
	if (saveRequiresLogin) {
		openSaveLoginModal();
		return;
	}
	if (saveButton) {
		saveButton.disabled = true;
	}
	if (runStatus) {
		runStatus.textContent = "正在儲存...";
	}
	if (saveStatus) {
		saveStatus.textContent = "儲存中...";
	}
	const result = await saveCurrentWorkflow();
	if (saveNeedsLogin(result)) {
		if (saveButton) {
			saveButton.disabled = false;
		}
		if (saveStatus) {
			saveStatus.textContent = "尚未儲存";
		}
		openSaveLoginModal();
		return;
	}
	const message = saveResultMessage(result);
	if (runStatus) {
		runStatus.textContent = message;
	}
	if (saveStatus) {
		const statusText = result.saved ? "已儲存" : "儲存失敗";
		if (result.saved) {
			recordSavedWorkflowMetadata(statusText);
		}
		saveStatus.textContent = statusText;
	}
	showSavePanel(savePanel, message);
	if (saveButton) {
		saveButton.disabled = false;
	}
});

function saveResultMessage(result) {
	if (result?.saved) {
		return "已儲存。";
	}
	if (result?.config_saved && result?.bundle_saved === false) {
		return `Agent 名稱與摘要已儲存；但 SemanticRetrieve 知識庫未儲存：${result.bundle_error || result.error || "請確認 AI Hub bundle storage API。"}`;
	}
	return result?.error || "儲存失敗。";
}

saveLoginCloseButtons.forEach((button) => button.addEventListener("click", closeSaveLoginModal));
saveLoginForm?.addEventListener("submit", async (event) => {
	event.preventDefault();
	const username = saveLoginUsername?.value.trim() || "";
	const password = saveLoginPassword?.value || "";
	if (!username || !password) {
		if (saveLoginError) {
			saveLoginError.hidden = false;
			saveLoginError.textContent = "請輸入 AI Hub 帳號與密碼。";
		}
		return;
	}
	if (saveLoginSubmit) {
		saveLoginSubmit.disabled = true;
	}
	if (runStatus) {
		runStatus.textContent = "正在登入...";
	}
	const result = await loginAiHubSession(username, password);
	if (saveLoginSubmit) {
		saveLoginSubmit.disabled = false;
	}
	if (!result.authenticated) {
		if (saveLoginError) {
			saveLoginError.hidden = false;
			saveLoginError.textContent = result.error || "登入失敗。";
		}
		if (runStatus) {
			runStatus.textContent = result.error || "登入失敗。";
		}
		return;
	}
	closeSaveLoginModal();
	showSavePanel(savePanel, "已登入 AI Hub，正在儲存...");
	window.location.href = result.redirect_url || "/playground/run";
});

document.addEventListener("keydown", (event) => {
	if (event.key === "Escape" && workflowInfoModal && !workflowInfoModal.hidden) {
		closeWorkflowInfoModal();
		return;
	}
	if (event.key === "Escape" && saveLoginModal && !saveLoginModal.hidden) {
		closeSaveLoginModal();
	}
});

if (autoSaveAfterLogin && saveButton && !saveRequiresLogin) {
	queueMicrotask(() => {
		saveButton.click();
	});
}

if (saveLoginModal && !saveRequiresLogin) {
	window.setInterval(refreshAiHubSession, 5 * 60 * 1000);
}

initializeRunner();