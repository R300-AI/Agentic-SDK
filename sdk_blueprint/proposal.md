# Agentic-SDK 升級 Proposal

## Problem Statement

Agentic-SDK 目前的核心產品形態是部署在 Azure App Service 的公開可用 Playground Demo。使用者不需登入即可直接透過線上 Gateway 執行 workflow，導致兩個問題同時存在：

1. 執行成本直接消耗公司持有的 AI Cloud 與推論資源，沒有使用者邊界。
2. 使用者無法建立自己的 Agent 與保存核心配置，下一次回來時也無法延續先前 Playground 狀態。

現況顯示這個子專案仍以單機或單行程 runtime 為中心：

- SDK 設定主要來自 `.env` 與 Gateway process state。
- Demo 前端直接呼叫 `/v1/workflow/run`、`/v1/workflow/{id}/stream` 與 `/v1/workflow/{id}/result`。
- `ActiveStore` 是 in-memory；`MemoryStore` 雖為 SQLite，但僅以 `workflow_name` 隔離，沒有使用者所有權概念。

因此，下個階段的真正目標不是單純把 Demo 加上登入畫面，而是把 Agentic-SDK 重新定位成「由 AI Hub 管理身份與資料所有權的受控線上多使用者 Playground」。

## Target User / Stakeholder

- 主要使用者：已在 AI Hub 擁有帳號的開發者、研究者、PoC 建置者。
- 驗收者：AI Hub 產品 owner 與平台維護者。
- 成本承擔者：AI Hub 平台方，需能控制誰可使用 Playground 與哪些執行資源可被消耗。

## Proposed Delivery Form

第一階段交付形式建議定義為：

「AI Hub 受管 Agent Playground」

- 使用者從 ai-hub-webui 登入後進入 Playground。
- Playground 的正式使用路徑必須對齊目前 Azure App Service 線上部署形態，而不是只優化本機測試流程。
- 每位使用者可建立、命名、編輯、刪除自己的 Agent。
- Agent 的核心編排配置儲存在 AI Hub 的 Azure SQL，重新登入後可繼續編輯與執行。
- Agent 執行仍可沿用 Agentic-SDK Gateway 與現有 workflow engine，不要求第一階段重寫節點系統。

## Acceptance Criteria

### A. 身份與入口

1. 未登入使用者不得直接使用正式 Playground 執行 workflow。
2. Playground 使用者身份以 ai-hub-webui 既有登入 session 與 Azure SQL `app_user` 為唯一權威來源。
3. Agentic-SDK 升級後不得再要求維護第二套獨立帳密。
4. 若 Agentic-SDK 維持獨立 App Service 網域，身份橋接方案必須明確定義，不得把跨站 cookie 共用視為既成事實。

### B. 個人 Agent 管理

1. 已登入使用者可建立至少一個個人 Agent 草稿。
2. 使用者只能讀寫自己的 Agent，不得存取其他使用者資料。
3. 使用者可在下次登入後看到自己上次保存的 Agent 與最近一次保存時間。
4. 使用者可更新至少以下核心欄位：Agent 名稱、描述、workflow 配置、執行後端選項、必要的 playground 參數。

### C. 執行與續用

1. 使用者可從已保存的 Agent 直接發起 workflow 執行。
2. 執行請求在伺服端必須帶有可追溯的 owner identity。
3. 重新整理頁面或重新登入後，使用者仍可載入同一個 Agent 並再次執行。

### D. 平台成本與管控

1. 平台方可關閉匿名 Playground 執行路徑。
2. 所有正式保存的 Agent 都有 owner、created_at、updated_at 等基本審計欄位。
3. 第一階段不要求完整計費系統，但資料模型不得阻礙後續加入配額或用量統計。

## Out Of Scope

- 團隊共享 Agent、多人協作編輯。
- 完整版本控制、branch、diff、回滾歷史。
- 使用者自帶模型憑證、各自綁定獨立 Foundry / upstream secret。
- 細粒度 RBAC 到節點級或工具級權限。
- 計費、配額扣點、組織帳單結算。
- 將五節點 workflow engine 全面改寫為新框架。
- 對外開放公開 Agent marketplace。

## Overengineering Guardrail

第一階段只證明三件事：

1. ai-hub 身份能接到 Playground。
2. 個人 Agent 能保存並續用。
3. 執行請求能帶著 owner identity 被平台追溯。

因此第一階段不應提前做：

- 通用 plugin marketplace。
- 跨租戶共享權限模型。
- 複雜的 workflow version graph。
- 額外引入新的 IAM 產品或外部身份提供者。
- 為尚未驗證的多人協作需求先拆出大量事件溯源或 CRDT 架構。

## Dependencies Requiring Curator Review

目前建議第一階段優先重用現有技術棧：

- ai-hub-webui 的 Flask session 與 SQL 帳號資料。
- Agentic-SDK 既有 FastAPI Gateway 與 workflow engine。
- 既有 `pymssql` / Azure SQL 路徑。

若後續要新增下列依賴，需另交 `tech-stack-curator` 審查：

- 新的前端狀態管理庫。
- 新的 ORM / migration framework。
- 新的身份提供者 SDK。
- 新的背景工作佇列或事件總線。

## Next-Stage Proposal

下一階段 proposal 建議以「Managed Agent Workspace v1」命名，拆成三個可驗收工作包：

1. `Identity Bridge`：由 ai-hub-webui 接手 Playground 的登入、Session、CSRF 與 owner resolution。
2. `Personal Agent Persistence`：新增 Agent SQL schema 與 CRUD API，保存每位使用者的核心 Playground 配置。
3. `Execution Mediation`：由受管 API 代理或轉送到 Agentic-SDK Gateway，使每次執行都帶有 owner context 與 agent_id。

若維持雙 App Service 拓撲，`Identity Bridge` 需進一步拆成二選一：

1. `Entry Consolidation`：由 ai-hub-webui 反向代理或掛載 Playground，讓使用者始終從同一個站點入口使用。
2. `Trusted Token Exchange`：由 ai-hub-webui 在使用者登入後簽發短效 token 給 Agentic-SDK，Agentic-SDK 再以該 token 向 AI Hub 或共享 SQL 驗證 owner。

## Open Questions Needing Product Decision

1. 未登入使用者是否完全禁止進入 Playground，還是保留 read-only 展示模式。
2. 第一階段的「核心配置」最小集合要包含哪些欄位，是否包含知識庫、附件、prompt 模板與匯出 bundle。
3. 每位使用者可建立的 Agent 數量是否需要先設上限。
4. Playground 是否只服務登入後的個人工作區，還是要同時保留一個公開展示網址。
5. 若保留獨立 App Service 網址，第一階段採入口收斂還是短效 token bridge。
6. 執行紀錄是否需要在第一階段保存最近一次結果摘要，供使用者回看。