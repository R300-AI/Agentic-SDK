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
const saveButton = document.querySelector("[data-save-action]");
const reloadButton = document.querySelector("[data-reload-action]");
const saveStatus = document.querySelector("[data-save-status]");
const attachmentInput = document.querySelector("[data-attachment-input]");
const artifactList = document.querySelector("[data-artifact-list]");
const attachmentStatus = document.querySelector("[data-attachment-status]");
const savePanel = document.querySelector("[data-save-panel]");
const endpointForm = document.querySelector("[data-endpoint-form]");
const endpointDeployButton = document.querySelector("[data-endpoint-deploy]");
const endpointStatus = document.querySelector("[data-endpoint-status]");
const codePreviewToggles = document.querySelectorAll("[data-code-preview-open]");
const codePreviewModal = document.querySelector("[data-code-preview-modal]");
const submitButton = form?.querySelector("button[type='submit']");
let activeRunId = 0;

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

async function syncEndpointSelections() {
	if (!endpointForm) {
		return;
	}
	if (endpointDeployButton) {
		endpointDeployButton.disabled = true;
	}
	const selections = Object.fromEntries(new FormData(endpointForm).entries());
	const result = await postJson("/playground/run/endpoints", { selections });
	if (endpointDeployButton) {
		endpointDeployButton.disabled = false;
	}
	if (endpointStatus) {
		endpointStatus.textContent = result.error ? "端點設定失敗。" : "端點設定已更新。";
	}
}

bindAttachmentPicker(attachmentInput, artifactList, attachmentStatus);
bindCodePreview(codePreviewToggles, codePreviewModal);
endpointDeployButton?.addEventListener("click", () => {
	syncEndpointSelections();
});

async function runWorkflow(payload, { displayMessage, showUserMessage = true } = {}) {
	const runId = ++activeRunId;
	const prompt = String(payload?.message || "").trim();
	const submittedToolCall = payload?.tool_call_submission || null;
	const requestMessage = prompt || (submittedToolCall ? toolSubmissionDisplay(submittedToolCall) : "");
	const requestPayload = { message: requestMessage };
	if (submittedToolCall) {
		requestPayload.tool_call_submission = submittedToolCall;
	}
	if (emptyMessage) {
		emptyMessage.hidden = true;
	}
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

resultThread?.addEventListener("runner:tool-call-submit", async (event) => {
	const submission = event.detail || {};
	await runWorkflow(
		{ message: "", tool_call_submission: submission },
		{ displayMessage: toolSubmissionDisplay(submission), showUserMessage: false },
	);
});

saveButton?.addEventListener("click", async () => {
	if (saveButton) {
		saveButton.disabled = true;
	}
	if (runStatus) {
		runStatus.textContent = "正在儲存...";
	}
	if (saveStatus) {
		saveStatus.textContent = "儲存中...";
	}
	let result;
	try {
		result = await postJson("/playground/aihub/config/save");
	} catch (error) {
		result = { saved: false, error: error.message || "儲存失敗。" };
	}
	const message = result.saved ? "已儲存。" : (result.error || "儲存失敗。");
	if (runStatus) {
		runStatus.textContent = message;
	}
	if (saveStatus) {
		saveStatus.textContent = result.saved ? "已儲存" : "儲存失敗";
	}
	showSavePanel(savePanel, message);
	if (saveButton) {
		saveButton.disabled = false;
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