export function getSavePanelState() {
  return "not_saved";
}

export function showSavePanel(panel, message) {
  if (!panel) {
    return;
  }
  panel.textContent = message;
  panel.hidden = false;
  panel.dataset.state = "visible";
}