import { getModeContext } from "../shared/mode-context.js";

getModeContext();

const loginForm = document.querySelector("[data-login-form]");
const loginButton = document.querySelector("[data-login-submit]");
const entryTabs = document.querySelectorAll("[data-entry-tab]");
const entryPanels = document.querySelectorAll("[data-entry-panel]");

entryTabs.forEach((tab) => {
	tab.addEventListener("click", () => {
		const target = tab.dataset.entryTab;
		entryTabs.forEach((candidate) => {
			const isActive = candidate === tab;
			candidate.classList.toggle("is-active", isActive);
			candidate.setAttribute("aria-selected", String(isActive));
		});
		entryPanels.forEach((panel) => {
			panel.hidden = panel.dataset.entryPanel !== target;
		});
	});
});

loginForm?.addEventListener("submit", () => {
	loginForm.querySelectorAll("input").forEach((control) => {
		control.readOnly = true;
	});
	loginForm.querySelectorAll("button").forEach((control) => {
		control.disabled = true;
	});
	if (loginButton) {
		loginButton.textContent = "正在登入...";
	}
});