# Playground — Phase 5 圖形編排 UI

> 對應 [docs/04-observability-dashboard/phase5-graph-editor-plan.md](../docs/04-observability-dashboard/phase5-graph-editor-plan.md)

本前端讓使用者能用瀏覽器拖曳設計五節點工作流、即時看到節點執行動畫,並用對話框驗證效果,**完全不必碰 Python 或 YAML**。

## 啟動(本機開發)

需求:Node 22+(本專案不要求全機 install,可用 fnm / nvm-windows 隔離)。

```powershell
# 1. 啟 Playground V1 dev gateway(另一個 terminal)
.\.venv\Scripts\python.exe -m playground_v1_gateway --host 127.0.0.1 --port 8080

# 2. 啟編輯器(此目錄)
cd playground
npm install
npm run dev
# 開 http://localhost:5173
```

Vite dev server 已設定 `/v1/*` 與 `/api/me/*` proxy 到 `http://localhost:8080`,跨域不必處理。

## 你能做什麼

1. **看到預設五節點工作流**:畫布顯示 Perceive → Plan → Retrieve / Action → Reflect → Plan / END
2. **拖曳節點、改連線**:畫布即時擋掉非法連線(白名單見 [`src/adapter.ts`](./src/adapter.ts))
3. **點選節點開屬性面板**:
   - Plan 可選 `react` / `cot` / `plan_and_solve` 三模板,或自訂多行 prompt
   - Reflect 可切 `retry_plan`(失敗回 Plan 重試)/ `end`(失敗直接結束)
    - Action 以 OpenAI-compatible `api_key` / `base_url` / `model` 設定模型連線
4. **YAML 下載 / 載入**:Ctrl+S / 拖檔載入。檔案完全在本機。
5. **跑一次 + 動畫**:輸入訊息按「跑一次」→ 五節點即時亮燈 → 對話框顯示最終回應

## 不做的範圍

- ❌ 工具調用(function calling / MCP)
- ❌ 多輪對話與 session 狀態(每次跑一次都是新 session)
- ❌ 自訂節點 Python import(RCE 風險,只允許內建五節點)
- ❌ 工作流版本控制、團隊共享、雲端儲存

## 結構

```
playground/
├── package.json
├── vite.config.ts                 # /v1/* + /api/me/* proxy → :8080
├── index.html
└── src/
    ├── main.tsx                   # entry
    ├── App.tsx                    # 主版型 + 跑一次 + SSE 訂閱
    ├── styles.css                 # 全域樣式 + 節點動畫 keyframe
    ├── types.ts                   # WorkflowConfig 對齊 Python schema
    ├── adapter.ts                 # YAML ⇄ React Flow nodes/edges
    ├── defaultWorkflow.ts         # 預設五節點 YAML
    ├── nodes/
    │   ├── NodeBase.tsx           # 共用外殼 + 狀態描邊
    │   ├── PerceiveNode.tsx
    │   ├── PlanNode.tsx
    │   ├── RetrieveNode.tsx
    │   ├── ReflectNode.tsx
    │   ├── ActionNode.tsx
    │   └── index.ts
    ├── panels/
    │   ├── NodePalette.tsx        # 左:5 種型別 + YAML 下載/載入
    │   ├── PropertyPanel.tsx      # 右:依選中節點顯示對應屬性
    │   └── ChatPanel.tsx          # 底:對話框 + 跑一次按鈕
    └── runtime/
        ├── types.ts               # NodeStatus / TelemetryEvent / ChatMessage
        ├── eventNames.ts          # 對齊 Python observability/events.py
        └── api.ts                 # POST /v1/workflow/run + EventSource SSE
```

## 對應後端

| 前端動作 | Gateway 端點 |
|----------|-------------|
| 點「跑一次」 | `POST /v1/workflow/run`(送 `workflow_yaml` + `user_message`) |
| 動畫驅動 | `GET /v1/workflow/{id}/stream`(SSE,推 `workflow.node.start`/`finish`) |
| 取最終回應 | `GET /v1/workflow/{id}/result`(SSE 結束後拉一次) |
