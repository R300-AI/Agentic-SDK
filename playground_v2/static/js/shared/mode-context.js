export function getModeContext() {
  return {
    mode: document.body.dataset.mode || "anonymous",
  };
}