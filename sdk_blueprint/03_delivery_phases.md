# 03 Delivery Phases

## Phase 0: Scope Freeze

目標：在動工前把第一階段的產品邊界釘住。

需要決議：

1. 是否完全關閉匿名 Playground 執行。
2. `core config` 的最小欄位集合。
3. 是否保存最近一次執行摘要。
4. 每位使用者的 Agent 數量上限。

完成定義後，RD 才進入實作藍圖。

## Phase 1: Identity Bridge

目標：讓 Playground 正式掛在 ai-hub-webui 的登入體系下。

交付：

- 決定採 `Entry Consolidation` 或 `Trusted Token Exchange`。
- `/api/me/agents*` 受保護 API 骨架。
- 前端改走受管身份路徑，而不是直接匿名打 Gateway。

驗收：

- 未登入不能執行。
- 已登入能進入線上 Playground。
- API 透過 session 或受信 bridge token 判定 owner。

## Phase 2: Personal Agent Persistence

目標：讓使用者可保存與載入自己的 Agent。

交付：

- SQL schema bootstrap。
- Agent CRUD service。
- Playground 初次載入時列出我的 Agent。
- 編輯後可保存，重新登入後可續用。

驗收：

- 使用者 A 看不到使用者 B 的 Agent。
- SQL 暫停時保存會失敗且回可辨識錯誤。
- 重新登入後能還原最近保存的配置。

## Phase 3: Managed Execution

目標：把執行路徑改成可追溯的受管入口。

交付：

- `POST /api/me/agents/{agent_id}/run`
- server-to-server 轉送至 Agentic-SDK Gateway
- stream/result 代理或對應轉發
- run metadata 內含 owner 與 agent context

驗收：

- 每次執行都能對應到 owner 與 agent。
- 既有 workflow engine 不需大改即可執行。
- Gateway 不需直接理解 Flask session。

## Phase 4: Operability Hardening

目標：補上第一階段上線前最低限度的維運防線。

交付：

- 錯誤分類：SQL / Gateway / upstream / validation
- 基本審計欄位與日誌關聯鍵
- 若需要，加入最近一次 run summary

驗收：

- 維護者能區分是保存失敗還是執行失敗。
- 使用者能收到可操作的錯誤訊息。

## Key Risks

1. 若仍讓前端直接呼叫 FastAPI Gateway，身份與資料所有權會分裂。
2. 若未先裁定獨立 App Service 的身份橋接方案，工程實作會卡在跨站 session 與入口拓撲。
3. 若第一階段就追求多版本、共享與配額，scope 會膨脹到無法快速驗證。
4. 若 SQL schema 一開始就綁死過多未驗證欄位，後續 UI 與 engine 會被反向限制。

## Recommended RD Handoff Questions

1. 若保留獨立 App Service，bridge token 的驗證位置、格式與輪替策略是什麼。
2. 若採入口收斂，前端資產是反向代理、iframe，還是搬到 ai-hub-webui 內部頁面。
3. Flask BFF 與 FastAPI Gateway 的 stream 代理要如何設計，才能兼顧簡單與可觀測性。
4. `workflow_yaml` 與 `workflow_json` 是否都要保存，還是以一者為權威來源。
5. Agentic-SDK 的 run request/result schema 是否需要正式抽成共享 contract。
6. 第一階段是否需要 run summary table，或先僅更新 `last_run_at` 即可。