/**
 * editor/scripts/start.mjs
 *
 * 取代 concurrently：直接以 npm 自己的 node（process.execPath）啟動 vite，
 * 避免全域 PATH 沒有 node.exe 造成的靜默失敗。
 * Gateway 走 ../.venv/Scripts/python.exe，與原始 npm start 一致。
 */

import { spawn } from "child_process";
import { resolve, join, dirname } from "path";
import { fileURLToPath } from "url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const editorRoot = resolve(__dirname, "..");
const projectRoot = resolve(editorRoot, "..");

const cyan  = "\x1b[36m";
const green = "\x1b[32m";
const reset = "\x1b[0m";

function printPrefixed(label, color, buf) {
  String(buf)
    .split(/\r?\n/)
    .filter(Boolean)
    .forEach((line) => process.stdout.write(`${color}[${label}]${reset} ${line}\n`));
}

// ── Gateway（cwd = 專案根，確保 pydantic_settings 能讀到 .env）──────
const pythonExe = resolve(editorRoot, "../.venv/Scripts/python.exe");
const gw = spawn(pythonExe, ["-m", "agentic_sdk.gateway", "--host", "127.0.0.1", "--port", "8080"], {
  cwd: projectRoot,
  stdio: "pipe",
  env: { ...process.env, PYTHONUNBUFFERED: "1" },
});
gw.stdout.on("data", (d) => printPrefixed("gateway", cyan, d));
gw.stderr.on("data", (d) => printPrefixed("gateway", cyan, d));
gw.on("error", (e) => process.stderr.write(`[gateway] spawn error: ${e.message}\n`));

// ── Vite（以 npm 自帶的 node 執行，不依賴全域 PATH）────────────────
const viteEntry = join(editorRoot, "node_modules/vite/bin/vite.js");
const vite = spawn(process.execPath, [viteEntry], {
  cwd: editorRoot,
  stdio: "inherit",
  env: { ...process.env, FORCE_COLOR: "1" },
});
vite.on("error", (e) => process.stderr.write(`[editor] spawn error: ${e.message}\n`));

// ── 退出清理 ──────────────────────────────────────────────────────
const cleanup = () => {
  gw.kill("SIGTERM");
  vite.kill("SIGTERM");
};
process.on("SIGINT",  cleanup);
process.on("SIGTERM", cleanup);
vite.on("exit", (code) => { gw.kill(); process.exit(code ?? 0); });
gw.on("exit",  (code) => { if (code !== 0) process.stderr.write(`[gateway] exited with code ${code}\n`); });
