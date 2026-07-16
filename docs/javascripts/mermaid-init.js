let mermaidInitialized = false;

function renderMermaidDiagrams() {
  if (!window.mermaid) {
    return;
  }
  if (!mermaidInitialized) {
    window.mermaid.initialize({
      startOnLoad: false,
      securityLevel: "loose",
    });
    mermaidInitialized = true;
  }
  window.mermaid.run({
    querySelector: ".mermaid",
  });
}

if (typeof window.document$ !== "undefined") {
  window.document$.subscribe(() => {
    renderMermaidDiagrams();
  });
} else {
  document.addEventListener("DOMContentLoaded", () => {
    renderMermaidDiagrams();
  });
}
