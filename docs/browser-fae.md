# Playground Browser FAE

Run this checklist through the VS Code Browser before a Playground release. A case passes only when every stated result is visible in the browser; route calls, unit-test results, and source inspection are supporting evidence, not FAE evidence.

## Local Setup

```powershell
$env:PLAYGROUND_ENABLE_TEST_SUPPORT_ROUTES = "true"
uv run python -m flask --app playground.app run --debug --port 5050
```

Authenticate with Azure first. Browser FAE reads model configuration from the Azure `agentic-sdk-models` Key Vault; do not configure model endpoints in the local process environment.

Use a fresh anonymous browser session for each case. Capture a screenshot after the Builder configuration, the Runner result, and the returned Builder state. Do not save FAE agents.

For interactive cases, use `http://127.0.0.1:5050/playground/test-support/interactive-echo?case=<case-id>`. The route is disabled unless `PLAYGROUND_ENABLE_TEST_SUPPORT_ROUTES=true`, accepts only JSON, and does not persist data or call an external service.

## Required Cases

| ID | Builder setup | Runner assertion | Return-to-Builder assertion |
| --- | --- | --- | --- |
| FAE-01 | Q1 `in_context`; add two starter questions, remove one, then reorder by recreating it. | Both remaining chips render; clicking one fills and focuses the composer. | Questions and order are prefilled. `workflow_recall_preview` remains disabled. |
| FAE-02 | Q2 `pass_through`; add a distinctive welcome message and intent pair. | Trace/result uses the unmodified input contract. | Choice, message, and pair are prefilled. |
| FAE-03 | Q2 `text`; add a distinctive welcome message and intent pair. | Trace identifies text understanding and result follows the configured intent. | Text-only fields are prefilled without image-only stale values. |
| FAE-04 | Q2 `text_image`; add image instruction and a fixture image. | Attachment preview appears and trace/result includes image understanding. | Image instruction and shared fields are prefilled. |
| FAE-05 | Q3 `none`. | Trace skips retrieval. | `none` remains selected and no retrieval-only field is required. |
| FAE-06 | Q3 `keyword`; configure two key/value facts and a fallback. | Exact-key query returns its configured fact; unknown query returns fallback; trace identifies keyword retrieval. | Pairs and fallback are exact. |
| FAE-07 | Q3 `semantic`; upload a fixture document containing a unique fact, add a search goal, and bind an embedding endpoint. | A paraphrased query returns the fixture fact; trace identifies semantic retrieval. | File name and search goal are prefilled. |
| FAE-08 | Q4 `free_text`; configure a distinctive response instruction. | Answer visibly follows the instruction. | Instruction is prefilled. |
| FAE-09 | Q4 `interactive`; configure string, number, and boolean fields plus the local echo URL. | Information question has no panel. Actionable confirmation question has correctly typed controls; submit once; continuation visibly acknowledges the submitted values. | Contract URL, trigger, fields, types, and response instruction are prefilled. |
| FAE-10 | Q5 `retry` with an unsupported fixture; repeat with `handoff`. | Terminal behavior differs according to policy and is visible to the user. | Selected policy is prefilled. |
| FAE-11 | Omit each required advanced value, upload, or endpoint binding in turn. | Readiness stays disabled and names the missing configuration; it enables only when valid. | Review status and endpoint selections persist. |
| FAE-12 | Any complete workflow. | Initialization progresses to ready, overlay hides, composer and attachments enable, response streams, and submit re-enables after completion/error. | Builder retains the full workflow configuration. |

## Cloud Replay

After local cases pass, push and wait for CI and deployment. In a fresh VS Code Browser context, repeat the same matrix against the deployed Playground using synthetic fixtures and an approved no-side-effect test target. A cloud failure blocks release: reproduce locally, repair, rerun local FAE, deploy, and replay the complete cloud matrix.

### Test-support route window

`PLAYGROUND_ENABLE_TEST_SUPPORT_ROUTES` is disabled by default and must stay disabled outside an explicitly scheduled Cloud Replay window. Before enabling it, verify that `POST /playground/test-support/interactive-echo` returns `404` in the deployed environment. Record the owner, start time, expected end time, and synthetic case IDs for the window.

Enable the setting only for the replay, then verify the endpoint accepts the expected synthetic JSON payload. Immediately after the final case, remove the setting, restart the App Service if required by the platform, and verify the same endpoint again returns `404`. A replay is incomplete until this final `404` check is recorded.