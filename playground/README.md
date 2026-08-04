# Playground Frontend Package

This package contains the Flask-based Playground Entry, Builder, and Runner experience.

## Run Locally

```powershell
$env:PLAYGROUND_SKIP_KEY_VAULT_LOAD = "true"
uv run python -m flask --app playground.app run --debug --port 5050
```

`PLAYGROUND_SKIP_KEY_VAULT_LOAD=true` is for local Browser FAE only. It avoids Azure Key Vault startup access; configure the required model and embedding endpoints in the local process environment before validating Runner execution.

Then open:

- `http://127.0.0.1:5050/playground`
- `http://127.0.0.1:5050/playground/builder`
- `http://127.0.0.1:5050/playground/run`

Before release, run the [Browser FAE checklist](../docs/browser-fae.md) through the VS Code Browser.

AI Hub navigation also enters the same pages through these handoff routes:

- `POST /playground/aihub/navigation/builder`
- `POST /playground/aihub/navigation/runner`
- `GET` / `POST /playground/aihub/navigation/shared-runner`

## Current Scope

- Entry route and template
- Windows OOBE-style Builder shell
- Task-page Runner shell
- Lightweight page-specific JavaScript modules
- Shared visual language across the three pages
- Python source preview/export as the canonical artifact
- AI Hub login or handoff-token verification, including account `display_name` for Runner identity labels
- Agent listing, config load/reload, public readonly config load, and Runner save-back through the AI Hub API
- Public readonly Runner mode for shared AI Hub Agents, with save/reload owner-only controls hidden outside editable sessions

Gateway execution, arbitrary Python execution, and SDK multimodal/structured modules are intentionally left for later implementation slices.