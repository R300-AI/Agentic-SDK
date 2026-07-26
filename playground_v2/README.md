# Playground V2 Frontend Package

This package is the first implementation slice for the Playground V2 blueprint. It is intentionally separate from the existing Vite/React Flow `playground/` app so the new Entry / Builder / Runner experience can evolve without breaking the current playground.

## Run Locally

```powershell
python -m flask --app playground_v2.app run --debug --port 5050
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
- Python source preview as the only canonical saved artifact placeholder

Gateway execution, structured result payloads, AI Hub integration, and SDK multimodal/structured modules are intentionally left for later implementation slices.