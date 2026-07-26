const PYTHON_KEYWORDS = new Set([
  "False", "None", "True", "and", "as", "assert", "async", "await", "break", "class", "continue",
  "def", "del", "elif", "else", "except", "finally", "for", "from", "global", "if", "import",
  "in", "is", "lambda", "nonlocal", "not", "or", "pass", "raise", "return", "try", "while", "with", "yield",
]);

const PYTHON_BUILTINS = new Set([
  "dict", "float", "int", "list", "print", "set", "str", "tuple", "Workflow", "Gates",
]);

export function highlightCodeBlocks(root = document) {
  root.querySelectorAll("code.language-python, code.language-bash").forEach((code) => {
    const language = code.classList.contains("language-python") ? "python" : "bash";
    setHighlightedCode(code, code.textContent || "", language);
  });
}

export function setHighlightedCode(code, source, language) {
  code.replaceChildren();
  code.classList.add("code-highlight", `code-highlight-${language}`);
  const tokens = language === "python" ? tokenizePython(source) : tokenizeShell(source);
  tokens.forEach((token) => appendToken(code, token));
}

function tokenizePython(source) {
  const tokens = [];
  let index = 0;
  while (index < source.length) {
    const character = source[index];
    if (character === "#") {
      const end = source.indexOf("\n", index);
      const nextIndex = end === -1 ? source.length : end;
      tokens.push({ type: "comment", value: source.slice(index, nextIndex) });
      index = nextIndex;
      continue;
    }
    if (character === '"' || character === "'") {
      const token = readString(source, index);
      tokens.push({ type: "string", value: token.value });
      index = token.nextIndex;
      continue;
    }
    if (/\d/.test(character)) {
      const match = source.slice(index).match(/^\d+(?:\.\d+)?/);
      if (match) {
        tokens.push({ type: "number", value: match[0] });
        index += match[0].length;
        continue;
      }
    }
    if (/[A-Za-z_]/.test(character)) {
      const match = source.slice(index).match(/^[A-Za-z_][A-Za-z0-9_]*/);
      if (match) {
        const value = match[0];
        tokens.push({ type: pythonIdentifierType(source, index, value), value });
        index += value.length;
        continue;
      }
    }
    if (/[=+\-*/%<>!|&:,.()[\]{}]/.test(character)) {
      tokens.push({ type: /[()[\]{},.:]/.test(character) ? "punctuation" : "operator", value: character });
      index += 1;
      continue;
    }
    tokens.push({ type: "plain", value: character });
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
      tokens.push({ type: "plain", value: character });
      index += 1;
      expectsCommand = true;
      continue;
    }
    if (/\s/.test(character)) {
      const match = source.slice(index).match(/^\s+/);
      tokens.push({ type: "plain", value: match[0] });
      index += match[0].length;
      continue;
    }
    if (character === "#") {
      const end = source.indexOf("\n", index);
      const nextIndex = end === -1 ? source.length : end;
      tokens.push({ type: "comment", value: source.slice(index, nextIndex) });
      index = nextIndex;
      continue;
    }
    if (character === '"' || character === "'") {
      const token = readShellString(source, index);
      tokens.push({ type: "string", value: token.value });
      index = token.nextIndex;
      expectsCommand = false;
      continue;
    }
    const match = source.slice(index).match(/^\S+/);
    const value = match[0];
    tokens.push({ type: shellTokenType(value, expectsCommand), value });
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

function appendToken(parent, token) {
  if (token.type === "plain") {
    parent.append(document.createTextNode(token.value));
    return;
  }
  const span = document.createElement("span");
  span.className = `code-token code-token-${token.type}`;
  span.textContent = token.value;
  parent.append(span);
}