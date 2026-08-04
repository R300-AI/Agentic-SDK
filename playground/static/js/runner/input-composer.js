export function bindInputComposer(form, onSubmit) {
  const messageInput = form?.querySelector("textarea[name='message']");

  messageInput?.addEventListener("keydown", (event) => {
    if (event.key !== "Enter" || event.shiftKey || event.isComposing) {
      return;
    }
    event.preventDefault();
    form.requestSubmit();
  });

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const formData = new FormData(form);
    const files = Array.from(formData.getAll("attachments"))
      .filter((item) => item instanceof File && item.name);
    const payload = {
      message: String(formData.get("message") || ""),
      attachment_names: files.map((file) => file.name),
      attachments: await Promise.all(files.map(fileToAttachment)),
    };
    if (messageInput) {
      messageInput.value = "";
    }
    onSubmit?.(payload);
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
