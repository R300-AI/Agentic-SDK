import { setDrawerOpen } from "../shared/dialog.js";

export function bindCodePreview(toggles, drawer) {
  toggles.forEach((toggle) => {
    toggle.addEventListener("click", () => setDrawerOpen(drawer, drawer?.hidden));
  });
}