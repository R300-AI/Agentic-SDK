export async function postJson(url, payload = {}) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return response.json();
}

export async function postJsonStream(url, payload = {}, onMessage) {
  const response = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  if (!response.ok) {
    throw new Error(`Stream request failed with ${response.status}`);
  }
  if (!response.body) {
    throw new Error("Streaming response is not available in this browser.");
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const { value, done } = await reader.read();
    if (done) {
      break;
    }
    buffer += decoder.decode(value, { stream: true });
    buffer = await drainJsonLines(buffer, onMessage);
  }
  buffer += decoder.decode();
  await drainJsonLines(`${buffer}\n`, onMessage);
}

async function drainJsonLines(buffer, onMessage) {
  let nextBreak = buffer.indexOf("\n");
  while (nextBreak >= 0) {
    const line = buffer.slice(0, nextBreak).trim();
    buffer = buffer.slice(nextBreak + 1);
    if (line) {
      await onMessage?.(JSON.parse(line));
    }
    nextBreak = buffer.indexOf("\n");
  }
  return buffer;
}


export async function getJson(url) {
  const response = await fetch(url);
  return response.json();
}