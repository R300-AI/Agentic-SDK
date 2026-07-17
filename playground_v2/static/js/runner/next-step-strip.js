export function getDefaultNextSteps() {
  return ["複製回覆", "縮短語氣", "加入依據說明"];
}

export function bindNextStepStrip(strip, { resultMessage, runStatus, savePanel } = {}) {
  strip?.addEventListener("click", async (event) => {
    const button = event.target.closest("[data-next-step-action]");
    if (!button) {
      return;
    }

    const action = button.dataset.nextStepAction;
    let message = "已選擇下一步。";
    if (action === "copy") {
      const text = resultMessage?.textContent?.trim() || "";
      if (text && navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
      }
      message = text ? "已複製結果卡中的回覆。" : "目前沒有可複製的回覆。";
    } else if (action === "shorten") {
      message = "請調整提示內容後重新產生，讓回覆語氣更精簡。";
    } else if (action === "source-note") {
      message = "請開啟查看依據，確認來源說明後再送出。";
    }

    if (runStatus) {
      runStatus.textContent = message;
    }
    if (savePanel) {
      savePanel.textContent = message;
      savePanel.hidden = false;
      savePanel.dataset.state = "visible";
    }
  });
}