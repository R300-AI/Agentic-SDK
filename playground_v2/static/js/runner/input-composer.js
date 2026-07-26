export function bindInputComposer(form, onSubmit) {
  form?.addEventListener("submit", (event) => {
    event.preventDefault();
    const formData = new FormData(form);
    onSubmit?.({
      message: String(formData.get("message") || ""),
      attachment_names: Array.from(formData.getAll("attachments"))
        .filter((item) => item instanceof File && item.name)
        .map((file) => file.name),
    });
  });
}