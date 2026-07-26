export function selectChoice(cards, selectedCard) {
  cards.forEach((card) => card.classList.remove("selected"));
  selectedCard.classList.add("selected");
}