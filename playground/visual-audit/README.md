# Playground Visual Audit

This folder contains real browser screenshots captured with Playwright against the local Flask app.

## Capture Command

Start the app first:

```powershell
python.exe -m flask --app playground.app:app run --host 127.0.0.1 --port 5051
```

Capture the current comparison set:

```powershell
$playwrightPackage = Get-ChildItem "$env:LOCALAPPDATA\npm-cache\_npx" -Recurse -Filter package.json | Where-Object { Select-String -Path $_.FullName -Pattern '"name": "playwright"' -Quiet } | Select-Object -First 1
$env:NODE_PATH = Split-Path $playwrightPackage.FullName -Parent | Split-Path -Parent
node playground/visual-audit/capture-r7.cjs
```

Current review set:

- Entry: `entry-desktop-r7.png`, `entry-mobile-r7.png`
- Builder: `builder-desktop-r7.png`, `builder-mobile-r7.png`
- Runner: `runner-desktop-r7.png`, `runner-mobile-r7.png`

Earlier r5/r6 screenshots are retained as historical comparison sets only.

## Keyboard Audit

With the Flask app running, the trust disclosure keyboard audit can be run with:

```powershell
$playwrightPackage = Get-ChildItem "$env:LOCALAPPDATA\npm-cache\_npx" -Recurse -Filter package.json | Where-Object { Select-String -Path $_.FullName -Pattern '"name": "playwright"' -Quiet } | Select-Object -First 1
$env:NODE_PATH = Split-Path $playwrightPackage.FullName -Parent | Split-Path -Parent
node playground/visual-audit/keyboard-audit.cjs
```

Latest local result:

```text
keyboard-audit ok: trust basis toggle is keyboard reachable and expandable
```

## Findings

- r7 updates the visible language system to Taiwan Traditional Chinese across Entry, Builder, Runner, mode labels, run status, save status, result copy, and next-step actions.
- r7 moves the visual direction to an AMD-inspired black/white/red system: hard-edged panels, low-radius controls, angular cut corners, strong red top rules, black Runner side rail, and direct typography with `Noto Sans TC` / Microsoft JhengHei fallbacks.
- Entry now presents a centered AI Hub Agent 建立工具 card with login and local trial paths, avoiding generic English product-shell copy.
- Builder keeps the horizontal setup rail and centered current-step card, but the step labels, summary, readiness checklist, and advanced disclosure use task-oriented Taiwan Chinese.
- Runner uses a direct-use conversation surface with nearby reason, evidence toggle, and next-step actions. The custom attachment trigger is localized as `選擇參考檔案`, so the native English file-button text is no longer exposed in the page markup.
- The r7 desktop/mobile screenshots were reviewed after restarting Flask so the captured pages reflected the latest Python templates and CSS.

## Remaining Visual Gaps

- This is a local screenshot audit, not a formal design review with designer/PM sign-off.
- No automated pixel-diff baseline is committed yet.
- Screen-reader audit remains separate from visual art review; the trust disclosure keyboard path has a passing Playwright smoke audit.
- AI Hub/AMD final brand review remains pending because the integration is still stubbed.
- The layout is inspired by publicly visible AMD art direction and uses original implementation code; official AMD, Microsoft, or Google frontend source code was not copied into this repository.
