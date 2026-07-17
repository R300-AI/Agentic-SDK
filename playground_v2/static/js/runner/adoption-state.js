export function getDefaultAdoptionState() {
  return "可供採用";
}

export function setAdoptionState(element, adoptionLevel) {
  if (element) {
    element.textContent = adoptionLevel || getDefaultAdoptionState();
  }
}