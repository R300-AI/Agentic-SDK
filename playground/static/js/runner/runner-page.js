import { postJson, postJsonStream } from "../shared/api-client.js";
import { bindAttachmentPicker } from "./artifact-panel.js";
import { bindCodePreview } from "./code-preview.js";
import { bindInputComposer } from "./input-composer.js";
import { clearProcessEvents, setProcessSummary, setResultMessage, setToolCallPanels, showLiveProcessEvent, showResultSurface, streamProcessEvents, streamResultMarkdown } from "./result-surface.js";
import { showSavePanel } from "./save-panel.js";

const form = document.querySelector("[data-input-composer]");
const runStatus = document.querySelector("[data-run-status]");
const resultThread = document.querySelector("[data-result-thread]");
const resultSurface = document.querySelector("[data-result-surface]");
const userMessage = document.querySelector("[data-user-message]");
const emptyMessage = document.querySelector("[data-empty-message]");
const starterQuestions = document.querySelector("[data-starter-questions]");
const saveButton = document.querySelector("[data-save-action]");
const reloadButton = document.querySelector("[data-reload-action]");
const saveStatus = document.querySelector("[data-save-status]");
const attachmentInput = document.querySelector("[data-attachment-input]");
const artifactList = document.querySelector("[data-artifact-list]");
const attachmentStatus = document.querySelector("[data-attachment-status]");
const savePanel = document.querySelector("[data-save-panel]");
const codePreviewToggles = document.querySelectorAll("[data-code-preview-open]");
const codePreviewModal = document.querySelector("[data-code-preview-modal]");
const runnerPage = document.querySelector("[data-page='runner']");
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
const workflowDescriptionPlaceholder = workflowDescriptionDisplay?.dataset.placeholder || "";
let lastSaveTrigger = null;
let runnerInitialized = !initializationOverlay;
const initialSaveStatusText = saveStatus?.textContent?.trim() || "";
let savedWorkflowName = initialSaveStatusText === "尚未儲存" ? null : workflowName;
let savedWorkflowDescription = initialSaveStatusText === "尚未儲存" ? null : workflowDescription;
let lastStableSaveStatusText = initialSaveStatusText && initialSaveStatusText !== "儲存中..." ? initialSaveStatusText : "已儲存";

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
		initializationMessage.textContent = event?.message || "正在準備 Agent 初始化...";
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
		initializationMessage.textContent = message || "Agent 初始化失敗，請回到 Builder 檢查設定。";
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
		failInitialization(error.message || "Agent 初始化失敗，請稍後再試。")
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

function renderWorkflowName(nextName) {
	workflowName = String(nextName || "").trim() || workflowName;
	workflowNameTargets.forEach((element) => {
		element.textContent = workflowName;
	});
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
		async function commitWorkflowDescription() {
			if (!workflowDescriptionInput || workflowDescriptionRequest) {
				return workflowDescriptionRequest;
			}
			const nextDescription = workflowDescriptionInput.value.trim();
			if (!nextDescription || nextDescription === workflowDescription) {
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
				renderWorkflowDescription(result.description || nextDescription);
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

function hideStarterQuestions() {
	if (starterQuestions) {
		starterQuestions.hidden = true;
	}
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
	if (sideWorkflowTitleForm && !sideWorkflowTitleForm.hidden) {
		await commitWorkflowName();
	}
	if (workflowRenameRequest) {
		await workflowRenameRequest;
	}
	if (workflowDescriptionRequest) {
		await workflowDescriptionRequest;
	}
	if (workflowDescriptionForm && !workflowDescriptionForm.hidden) {
		await commitWorkflowDescription();
	}
	if (workflowDescriptionRequest) {
		await workflowDescriptionRequest;
	}
	return (!sideWorkflowTitleForm || sideWorkflowTitleForm.hidden) && (!workflowDescriptionForm || workflowDescriptionForm.hidden);
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
	return error === "Current mode cannot save to AI Hub." || error === "AI Hub login is required before saving.";
}

bindAttachmentPicker(attachmentInput, artifactList, attachmentStatus);
bindCodePreview(codePreviewToggles, codePreviewModal);
renderWorkflowDescription(workflowDescriptionInput?.value || workflowDescription);
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
	if (emptyMessage) {
		emptyMessage.hidden = true;
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
	}
	setProcessSummary(assistant.debugStatus, []);
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
		return;
	}
	const actionReply = actionReplyFrom(result);
	const debugMessages = debugMessagesFrom(result);
	const finalProcessEvents = processEventsFrom(result);
	const finalToolCallPanels = toolCallPanelsFrom(result);
	const replayProcessEvents = liveProcessShown ? [] : finalProcessEvents;
	if (actionReply || finalToolCallPanels.length || debugMessages.length || finalProcessEvents.length) {
		showResultSurface(resultThread);
		showResultSurface(assistant.surface);
		if (assistant.bubble) {
			assistant.bubble.hidden = !(actionReply || finalToolCallPanels.length || replayProcessEvents.length);
		}
		if (replayProcessEvents.length) {
			if (runStatus) {
				runStatus.textContent = "正在整理處理過程...";
			}
			await streamProcessEvents(assistant.processTrace, replayProcessEvents, {
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
		if (finalProcessEvents.length) {
			setProcessSummary(assistant.debugStatus, finalProcessEvents);
		} else {
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
		setProcessSummary(assistant.debugStatus, []);
	}
	if (runStatus) {
		runStatus.textContent = executionStatusFrom(result);
	}
	setSurfaceBusy(assistant.surface, false);
	if (submitButton && runId === activeRunId) {
		submitButton.disabled = false;
	}
}

bindInputComposer(form, async (payload) => {
	await runWorkflow(payload);
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
	await runWorkflow(
		{ message: "", tool_call_submission: submission },
		{ displayMessage: toolSubmissionDisplay(submission), showUserMessage: false },
	);
});

saveButton?.addEventListener("click", async () => {
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
		const statusText = result.saved ? "已儲存" : (result.config_saved ? "設定已儲存，知識庫未儲存" : "儲存失敗");
		if (result.saved || result.config_saved) {
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
	if (event.key === "Escape" && saveLoginModal && !saveLoginModal.hidden) {
		closeSaveLoginModal();
	}
});

reloadButton?.addEventListener("click", async () => {
	reloadButton.disabled = true;
	if (runStatus) {
		runStatus.textContent = "正在重新載入...";
	}
	let result;
	try {
		result = await postJson("/playground/aihub/config/reload");
	} catch (error) {
		result = { loaded: false, error: error.message || "重新載入失敗。" };
	}
	if (result.loaded) {
		window.location.href = "/playground/run";
		return;
	}
	const message = result.error || "重新載入失敗。";
	if (runStatus) {
		runStatus.textContent = message;
	}
	showSavePanel(savePanel, message);
	reloadButton.disabled = false;
});

if (autoSaveAfterLogin && saveButton && !saveRequiresLogin) {
	queueMicrotask(() => {
		saveButton.click();
	});
}

initializeRunner();