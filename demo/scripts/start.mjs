/**
 * demo/scripts/start.mjs
 *
 * 一鍵啟動 Gateway + Vite dev server。跨平台（Windows / macOS / Linux）。
 * 自動偵測 .venv 的 Python 路徑；找不到時退回系統 `python` / `python3`。
 */

import { spawn, spawnSync } from "child_process";
import { existsSync } from "fs";
import { resolve, join, dirname } from "path";
import { fileURLToPath } from "url";
import { platform } from "os";

const __dirname = dirname(fileURLToPath(import.meta.url));
const demoRoot = resolve(__dirname, "..");
const projectRoot = resolve(demoRoot, "..");
const isWin = platform() === "win32";

const cyan = "\x1b[36m";
const green = "\x1b[32m";
const reset = "\x1b[0m";

function printPrefixed(label, color, buf) {
  String(buf)
    .split(/\r?\n/)
    .filter(Boolean)
    .forEach((line) => process.stdout.write(`${color}[${label}]${reset} ${line}\n`));
}

// ── 偵測 Python 執行檔 ─────────────────────────────────────────────────
function resolvePython() {
  const candidates = isWin
    ? [
        join(projectRoot, ".venv", "Scripts", "python.exe"),
        "python.exe",
        "python",
      ]
    : [
        join(projectRoot, ".venv", "bin", "python"),
        "python3",
        "python",
      ];
  for (const c of candidates) {
    if (c.includes("/") || c.includes("\\")) {
      if (existsSync(c)) return c;
    } else {
      const which = spawnSync(isWin ? "where" : "which", [c], { stdio: "pipe" });
      if (which.status === 0) return c;
    }
  }
  process.stderr.write(
    `[gateway] 找不到 Python。請先建立 venv（uv sync）或安裝 Python。\n`
  );
  process.exit(1);
}

const pythonExe = resolvePython();

// ── Gateway（cwd = 專案根，確保 pydantic_settings 能讀到 .env）──────
const gw = spawn(pythonExe, ["-m", "agentic_sdk.gateway", "--host", "127.0.0.1", "--port", "8080"], {
  cwd: projectRoot,
  stdio: "pipe",
  env: { ...process.env, PYTHONUNBUFFERED: "1" },
});
gw.stdout.on("data", (d) => printPrefixed("gateway", cyan, d));
gw.stderr.on("data", (d) => printPrefixed("gateway", cyan, d));
gw.on("error", (e) => process.stderr.write(`[gateway] spawn error: ${e.message}\n`));

// ── Vite（以 npm 自帶的 node 執行，不依賴全域 PATH）────────────────
const viteEntry = join(demoRoot, "node_modules", "vite", "bin", "vite.js");
const vite = spawn(process.execPath, [viteEntry], {
  cwd: demoRoot,
  stdio: "inherit",
  env: { ...process.env, FORCE_COLOR: "1" },
});
vite.on("error", (e) => process.stderr.write(`[demo] spawn error: ${e.message}\n`));

process.stdout.write(
  `${green}[demo]${reset} Gateway: http://localhost:8080 / Demo UI: http://localhost:5173\n`
);

// ── 退出清理 ──────────────────────────────────────────────────────
const cleanup = () => {
  gw.kill("SIGTERM");
  vite.kill("SIGTERM");
};
process.on("SIGINT", cleanup);
process.on("SIGTERM", cleanup);
vite.on("exit", (code) => { gw.kill(); process.exit(code ?? 0); });
gw.on("exit", (code) => { if (code !== 0) process.stderr.write(`[gateway] exited with code ${code}\n`); });
