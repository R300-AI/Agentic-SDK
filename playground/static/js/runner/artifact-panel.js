export function getArtifacts(result) {
  return result?.artifacts || [];
}

export function bindAttachmentPicker(input, list, status) {
  let previewUrls = [];
  const maxVisibleArtifacts = 3;

  input?.addEventListener("change", () => {
    previewUrls.forEach((url) => URL.revokeObjectURL(url));
    previewUrls = [];
    const files = Array.from(input.files || []);
    if (status) {
      status.textContent = files.length
        ? `已為本次試跑選擇 ${files.length} 個參考檔案。`
        : "尚未選擇附件。";
    }
    if (list) {
      const visibleFiles = files.slice(0, maxVisibleArtifacts);
      const hiddenCount = Math.max(0, files.length - visibleFiles.length);
      list.replaceChildren(
        ...visibleFiles.map((file) => {
          const item = document.createElement("div");
          item.className = file.type.startsWith("image/") ? "artifact-preview artifact-preview-image" : "artifact-preview artifact-preview-file";

          if (file.type.startsWith("image/")) {
            const image = document.createElement("img");
            const url = URL.createObjectURL(file);
            previewUrls.push(url);
            image.src = url;
            image.alt = file.name;
            item.append(image);
          }

          const name = document.createElement("span");
          name.textContent = file.name;
          item.append(name);
          return item;
        }),
        ...(hiddenCount ? [artifactOverflowItem(hiddenCount)] : []),
      );
    }
  });
}

function artifactOverflowItem(count) {
  const item = document.createElement("div");
  item.className = "artifact-preview artifact-preview-overflow";
  item.textContent = `+${count}`;
  item.setAttribute("aria-label", `還有 ${count} 個附件未顯示`);
  return item;
}