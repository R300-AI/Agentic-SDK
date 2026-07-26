export function setDrawerOpen(drawer, open) {
  if (drawer) {
    drawer.hidden = !open;
    drawer.classList.toggle("open", open);
    drawer.dataset.open = String(open);
  }
}