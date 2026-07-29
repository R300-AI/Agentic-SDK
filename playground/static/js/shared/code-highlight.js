const PYTHON_KEYWORDS = new Set([
  "False", "None", "True", "and", "as", "assert", "async", "await", "break", "class", "continue",
  "def", "del", "elif", "else", "except", "finally", "for", "from", "global", "if", "import",
  "in", "is", "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "try", "while", "with", "yield",
]);

const PYTHON_BUILTINS = new Set([
  "dict", "float", "int", "list", "print", "set", "str", "tuple", "Workflow", "Gates",
]);

const FOLDABLE_PYTHON_KEYWORDS = new Set([
  "description",
  "fallback",
  "image_instruction",
  "prefix",
  "retrieve_description",
  "system_prompt",
  "welcome_message",
]);

const FOLDABLE_PYTHON_ASSIGNMENTS = new Set([
  "instruction",
  "summary",
]);

export function highlightCodeBlocks(root = document) {
  root.querySelectorAll("code.language-python, code.language-bash").forEach((code) => {
    const language = code.classList.contains("language-python") ? "python" : "bash";
    setHighlightedCode(code, code.textContent || "", language);
  });
}

export function setHighlightedCode(code, source, language, options = {}) {
  code.replaceChildren();
  code.classList.add("code-highlight", `code-highlight-${language}`);
  const tokens = language === "python" ? tokenizePython(source) : tokenizeShell(source);
  const foldState = { imageIndex: 0 };
  tokens.forEach((token) => appendToken(code, token, source, language, options, foldState));
}

function tokenizePython(source) {
  const tokens = [];
  let index = 0;
  while (index < source.length) {
    const character = source[index];
    if (character === "#") {
      const end = source.indexOf("\n", index);
      const nextIndex = end === -1 ? source.length : end;
      tokens.push({ type: "comment", value: source.slice(index, nextIndex), start: index, end: nextIndex });
      index = nextIndex;
      continue;
    }
    if (character === '"' || character === "'") {
      const token = readString(source, index);
      tokens.push({ type: "string", value: token.value, start: index, end: token.nextIndex });
      index = token.nextIndex;
      continue;
    }
    if (/\d/.test(character)) {
      const match = source.slice(index).match(/^\d+(?:\.\d+)?/);
      if (match) {
        tokens.push({ type: "number", value: match[0], start: index, end: index + match[0].length });
        index += match[0].length;
        continue;
      }
    }
    if (/[A-Za-z_]/.test(character)) {
      const match = source.slice(index).match(/^[A-Za-z_][A-Za-z0-9_]*/);
      if (match) {
        const value = match[0];
        tokens.push({ type: pythonIdentifierType(source, index, value), value, start: index, end: index + value.length });
        index += value.length;
        continue;
      }
    }
    if (/[=+\-*/%<>!|&:,.()[\]{}]/.test(character)) {
      tokens.push({ type: /[()[\]{},.:]/.test(character) ? "punctuation" : "operator", value: character, start: index, end: index + 1 });
      index += 1;
      continue;
    }
    tokens.push({ type: "plain", value: character, start: index, end: index + 1 });
    index += 1;
  }
  return tokens;
}

function tokenizeShell(source) {
  const tokens = [];
  let index = 0;
  let expectsCommand = true;
  while (index < source.length) {
    const character = source[index];
    if (character === "\n") {
      tokens.push({ type: "plain", value: character, start: index, end: index + 1 });
      index += 1;
      expectsCommand = true;
      continue;
    }
    if (/\s/.test(character)) {
      const match = source.slice(index).match(/^\s+/);
      tokens.push({ type: "plain", value: match[0], start: index, end: index + match[0].length });
      index += match[0].length;
      continue;
    }
    if (character === "#") {
      const end = source.indexOf("\n", index);
      const nextIndex = end === -1 ? source.length : end;
      tokens.push({ type: "comment", value: source.slice(index, nextIndex), start: index, end: nextIndex });
      index = nextIndex;
      continue;
    }
    if (character === '"' || character === "'") {
      const token = readShellString(source, index);
      tokens.push({ type: "string", value: token.value, start: index, end: token.nextIndex });
      index = token.nextIndex;
      expectsCommand = false;
      continue;
    }
    const match = source.slice(index).match(/^\S+/);
    const value = match[0];
    tokens.push({ type: shellTokenType(value, expectsCommand), value, start: index, end: index + value.length });
    index += value.length;
    expectsCommand = /^(?:&&|\|\||[;|])$/.test(value);
  }
  return tokens;
}

function readString(source, startIndex) {
  const quote = source[startIndex];
  const triple = source.slice(startIndex, startIndex + 3) === quote.repeat(3);
  let index = startIndex + (triple ? 3 : 1);
  while (index < source.length) {
    if (!triple && source[index] === "\\") {
      index += 2;
      continue;
    }
    if (triple && source.slice(index, index + 3) === quote.repeat(3)) {
      return { value: source.slice(startIndex, index + 3), nextIndex: index + 3 };
    }
    if (!triple && source[index] === quote) {
      return { value: source.slice(startIndex, index + 1), nextIndex: index + 1 };
    }
    index += 1;
  }
  return { value: source.slice(startIndex), nextIndex: source.length };
}

function readShellString(source, startIndex) {
  const quote = source[startIndex];
  let index = startIndex + 1;
  while (index < source.length) {
    if (source[index] === "\\") {
      index += 2;
      continue;
    }
    if (source[index] === quote) {
      return { value: source.slice(startIndex, index + 1), nextIndex: index + 1 };
    }
    index += 1;
  }
  return { value: source.slice(startIndex), nextIndex: source.length };
}

function shellTokenType(value, expectsCommand) {
  if (expectsCommand && /^(?:cd|git|ollama|pip|python|python3)$/.test(value)) {
    return "command";
  }
  if (/^--?[A-Za-z0-9][\w-]*$/.test(value)) {
    return "option";
  }
  if (/^\$[A-Za-z_][A-Za-z0-9_]*$/.test(value)) {
    return "variable";
  }
  if (/^(?:&&|\|\||[;|])$/.test(value)) {
    return "operator";
  }
  return "plain";
}

function pythonIdentifierType(source, startIndex, value) {
  if (PYTHON_KEYWORDS.has(value)) {
    return "keyword";
  }
  if (PYTHON_BUILTINS.has(value)) {
    return "builtin";
  }
  const next = source.slice(startIndex + value.length).match(/^\s*\(/);
  if (next) {
    return /^[A-Z]/.test(value) ? "class" : "function";
  }
  return "plain";
}

function appendToken(parent, token, source, language, options, foldState) {
  if (token.type === "plain") {
    parent.append(document.createTextNode(token.value));
    return;
  }
  if (language === "python" && token.type === "string" && options.foldLongStrings && shouldFoldPythonString(source, token)) {
    parent.append(createFoldedStringToken(token.value, foldState));
    return;
  }
  const span = document.createElement("span");
  span.className = `code-token code-token-${token.type}`;
  span.textContent = token.value;
  parent.append(span);
}

function shouldFoldPythonString(source, token) {
  const inner = pythonStringInnerValue(token.value);
  if (isPlaceholderString(inner) || isStringInListLikeContext(source, token.start)) {
    return false;
  }
  if (inner.includes("\n") || isImageDataString(inner)) {
    return true;
  }
  const displayLength = stringDisplayLength(inner);
  if (isFoldablePythonTextArgument(source, token.start)) {
    return displayLength > 28;
  }
  return displayLength > 72;
}

function stringDisplayLength(value) {
  return Array.from(String(value)).reduce((length, character) => {
    return length + (isWideCharacter(character) ? 2 : 1);
  }, 0);
}

function isWideCharacter(character) {
  return /[\u1100-\u115F\u2E80-\uA4CF\uAC00-\uD7A3\uF900-\uFAFF\uFE10-\uFE19\uFE30-\uFE6F\uFF00-\uFF60\uFFE0-\uFFE6]/u.test(character);
}

function pythonStringInnerValue(value) {
  const match = String(value).match(/^[rubfRUBF]*(["']{1,3})([\s\S]*)(\1)$/);
  return match ? match[2] : String(value);
}

function isPlaceholderString(value) {
  return /^<[^>\n]{1,120}>$/.test(String(value).trim());
}

function isImageDataString(value) {
  return /^data:image\/[a-z0-9.+-]+;base64,/i.test(String(value).trim());
}

function isFoldablePythonTextArgument(source, start) {
  const lineStart = source.lastIndexOf("\n", start - 1) + 1;
  const before = source.slice(lineStart, start);
  const keywordMatch = before.match(/([A-Za-z_][A-Za-z0-9_]*)\s*=\s*$/);
  if (keywordMatch && FOLDABLE_PYTHON_KEYWORDS.has(keywordMatch[1])) {
    return true;
  }
  const assignmentMatch = before.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=.*(?:\bor\s+)?$/);
  return Boolean(assignmentMatch && FOLDABLE_PYTHON_ASSIGNMENTS.has(assignmentMatch[1]));
}

function isStringInListLikeContext(source, start) {
  const stack = [];
  for (let index = 0; index < start; index += 1) {
    const character = source[index];
    if (character === '"' || character === "'") {
      index = readString(source, index).nextIndex - 1;
      continue;
    }
    if (character === "#") {
      const lineEnd = source.indexOf("\n", index);
      if (lineEnd === -1 || lineEnd >= start) {
        return stack.at(-1) === "[";
      }
      index = lineEnd;
      continue;
    }
    if ("[{".includes(character)) {
      stack.push({ bracket: character, listLike: true });
      continue;
    }
    if (character === "(") {
      stack.push({ bracket: character, listLike: isTupleLiteralOpen(source, index) });
      continue;
    }
    if ("])}".includes(character)) {
      stack.pop();
    }
  }
  return Boolean(stack.at(-1)?.listLike);
}

function isTupleLiteralOpen(source, openIndex) {
  let index = openIndex - 1;
  while (index >= 0 && /\s/.test(source[index])) {
    index -= 1;
  }
  return index < 0 || "=,([{:".includes(source[index]);
}

function createFoldedStringToken(value, foldState) {
  const inner = pythonStringInnerValue(value);
  const button = document.createElement("button");
  button.type = "button";
  button.className = "code-fold-string code-token code-token-string";
  button.dataset.fullText = value;
  button.dataset.collapsedLabel = isImageDataString(inner) ? `[圖片${++foldState.imageIndex}]` : "...";
  button.dataset.expanded = "false";
  button.textContent = button.dataset.collapsedLabel;
  button.setAttribute("aria-label", "展開長文字內容");
  button.title = "展開長文字內容";
  button.addEventListener("click", () => {
    const expanded = button.dataset.expanded === "true";
    button.dataset.expanded = expanded ? "false" : "true";
    button.textContent = expanded ? button.dataset.collapsedLabel : value;
    button.setAttribute("aria-label", expanded ? "展開長文字內容" : "收合長文字內容");
    button.title = expanded ? "展開長文字內容" : "收合長文字內容";
  });
  return button;
}