# Playground Frontend Package

This package contains the Flask-based Playground Entry, Builder, and Runner experience.

## Run Locally

```powershell
uv run python -m flask --app playground.app run --debug --port 5050
```

Then open:

- `http://127.0.0.1:5050/playground`
- `http://127.0.0.1:5050/playground/builder`
- `http://127.0.0.1:5050/playground/run`

## Current Scope

- Entry route and template
- Windows OOBE-style Builder shell
- Task-page Runner shell
- Lightweight page-specific JavaScript modules
- Shared visual language across the three pages
- Python source preview/export as the canonical artifact
- AI Hub login verification, Agent listing, config load/reload, and Runner save-back through the AI Hub API

Gateway execution, arbitrary Python execution, and SDK multimodal/structured modules are intentionally left for later implementation slices.