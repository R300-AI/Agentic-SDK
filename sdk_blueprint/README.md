# SDK Blueprint

這份文件補上根目錄 README 中的藍圖連結，描述目前 repo 以 README 與 `docs/` 為基準時，可對照的實作範圍。

## MVP 基準

目前 MVP 可分成四個面向理解：

1. SDK workflow 核心

- `Workflow` 可串接 perceive / plan / retrieve / reflect / action 節點。
- `WorkflowState` 會保留 context entries、payload 與 action 結果。
- README 相容層另外提供 `agentic_sdk.modules`、`InputPerceive`、`KeywordRetrieve`、`DirectAnswerAction` 與 `memory.lookup(...)` 用法。

2. Gateway API

- `GET /healthz`
- `GET /v1/models`
- `POST /v1/chat/completions`
- `POST /v1/workflow/run`
- `GET /v1/workflow/{workflow_id}/stream`
- `GET /v1/workflow/{workflow_id}/result`

3. Context / memory

- Active context 與 archived context 已有基礎實作。
- `WorkflowState.lookup("latest_retrieved_content")` 提供 README custom action 所需的最小記憶體契約。

4. Demo / deployment

- Gateway 以 `demo/dist` 作為靜態前端掛載目標。
- `demo_old/` 仍是目前前端原始碼來源。
- GitHub Actions 會先建置 `demo_old/`，再同步產物到 `demo/dist` 打包部署。

## 現階段判讀方式

若要驗證「是否符合基準文件」，建議依下列順序檢查：

1. README 三個 quickstart 能否執行。
2. Gateway 主要端點是否存在且可回應。
3. `demo/dist` 是否存在並能由 Gateway 提供首頁。
4. CI/CD 是否把前端產物打進 `demo/dist`。

## 延伸原則

- README、`docs/`、`docs-site/` 視為基準，不直接改寫來遷就程式碼。
- 新節點或新能力應以新增模組、相容層或附加文件的方式擴充。