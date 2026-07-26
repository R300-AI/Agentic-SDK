export function appendHistoryItem(history, item) {
  return [...history, item];
}

export function prependHistoryItem(list, item) {
  if (!list || !item) {
    return;
  }
  list.querySelector(".empty-history")?.remove();
  const row = document.createElement("li");
  const status = document.createElement("strong");
  const message = document.createElement("span");
  status.textContent = item.status || "completed";
  message.textContent = item.message || "試跑已完成。";
  row.append(status, message);
  list.prepend(row);
  while (list.children.length > 3) {
    list.lastElementChild?.remove();
  }
}