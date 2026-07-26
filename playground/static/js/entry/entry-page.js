import { getModeContext } from "../shared/mode-context.js";

getModeContext();

const loginForm = document.querySelector("[data-login-form]");
const loginButton = document.querySelector("[data-login-submit]");
const loginStatus = document.querySelector("[data-login-status]");

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
	if (loginStatus) {
		loginStatus.textContent = "正在驗證 AI Hub 帳戶。";
	}
});