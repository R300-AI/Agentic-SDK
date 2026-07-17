export async function fetchSourcePreview() {
  const response = await fetch("/playground/source/preview");
  return response.text();
}