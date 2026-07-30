export function bindInputComposer(form, onSubmit) {
  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(form);
    const files = Array.from(formData.getAll("attachments"))
      .filter((item) => item instanceof File && item.name);
    onSubmit?.({
      message: String(formData.get("message") || ""),
      attachment_names: files.map((file) => file.name),
      attachments: await Promise.all(files.map(fileToAttachment)),
    });
  });
}

function fileToAttachment(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.addEventListener("load", () => {
      const mediaType = file.type || "application/octet-stream";
      resolve({
        kind: mediaType.startsWith("image/") ? "image" : "file",
        name: file.name,
        media_type: mediaType,
        content: String(reader.result || ""),
        metadata: { size: file.size },
      });
    });
    reader.addEventListener("error", () => reject(reader.error || new Error("附件讀取失敗。")));
    reader.readAsDataURL(file);
  });
}
