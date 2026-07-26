# Playground

This is the official FastAPI Playground for Agentic SDK. It mounts the existing server-rendered app and provides the Entry, Builder, Runner, AI Hub integration stubs, source preview/export, and ToolCallAction runner panels in one service.

## Run Locally

```powershell
python -m playground.main --host 127.0.0.1 --port 5050 --reload
```

Then open:

- `http://127.0.0.1:5050/playground`
- `http://127.0.0.1:5050/playground/builder`
- `http://127.0.0.1:5050/playground/run`

## Current Scope

- Entry route and template
- Windows OOBE-style Builder flow
- Task-page Runner flow
- ToolCallAction panels for string, number, and boolean user input
- Lightweight page-specific JavaScript modules
- Shared visual language across the three pages
- Python source preview/export as the canonical saved artifact
- Azure App Service deployment through `.github/workflows/deploy-playground.yml`

AI Hub save/load is currently a local stub. Model endpoint credentials should be provided through environment variables or Key Vault-backed runtime configuration.