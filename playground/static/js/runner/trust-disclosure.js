export function bindTrustDisclosure(toggle, panel) {
  toggle?.addEventListener("click", () => {
    const expanded = toggle.getAttribute("aria-expanded") === "true";
    toggle.setAttribute("aria-expanded", String(!expanded));
    if (panel) {
      panel.hidden = expanded;
    }
  });
}