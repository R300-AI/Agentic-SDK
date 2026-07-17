export function setResultMessage(element, message) {
  if (element && message) {
    element.textContent = message;
  }
}

export function setResultTitle(element, title) {
  if (element && title) {
    element.textContent = title;
  }
}

export function showResultSurface(element) {
  if (element) {
    element.hidden = false;
  }
}

export function setTrustEvidence(list, evidence) {
  if (!list || !Array.isArray(evidence)) {
    return;
  }
  list.replaceChildren(
    ...evidence.map((entry) => {
      const item = document.createElement("li");
      item.textContent = entry;
      return item;
    }),
  );
}