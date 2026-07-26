export function getArtifacts(result) {
  return result?.artifacts || [];
}

export function bindAttachmentPicker(input, list, status) {
  input?.addEventListener("change", () => {
    const files = Array.from(input.files || []);
    if (status) {
      status.textContent = files.length
        ? `已為本次試跑選擇 ${files.length} 個參考檔案。`
        : "尚未選擇附件。";
    }
    if (list) {
      list.replaceChildren(
        ...files.map((file) => {
          const item = document.createElement("li");
          item.textContent = file.name;
          return item;
        }),
      );
    }
  });
}