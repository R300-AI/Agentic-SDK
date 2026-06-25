# 02 Data Contracts

## Scope

此文件只定義第一階段為了「個人 Agent 建立、保存、續用、執行」所需的最小資料契約。

## SQL Data Model

### Table: `agent_workspace_agent`

建議用途：每列代表一個使用者擁有的 Playground Agent。

建議欄位：

- `agent_id` NVARCHAR(64) PK
- `owner_username` NVARCHAR(100) NOT NULL REFERENCES `app_user(username)`
- `agent_name` NVARCHAR(200) NOT NULL
- `description` NVARCHAR(1000) NULL
- `workflow_yaml` NVARCHAR(MAX) NOT NULL
- `entry_node` NVARCHAR(60) NOT NULL DEFAULT `'perceive'`
- `execution_backend` NVARCHAR(40) NOT NULL DEFAULT `'upstream'`
- `last_run_at` DATETIME2 NULL
- `created_at` DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()
- `updated_at` DATETIME2 NOT NULL DEFAULT SYSUTCDATETIME()

必要索引：

- `(owner_username, updated_at DESC)`
- `(owner_username, agent_name)`

### Deferred Table: `agent_workspace_run`

此表延後到後續階段，第一階段不建立。

第一階段只在 `agent_workspace_agent` 維護 `last_run_at`，不保存每次執行摘要。

## Why Single Agent Table First

- 使用者當前痛點是「不能保存自己的 Playground」。
- 第一階段最小必要物件是 Agent 草稿本身，不是完整執行歷史。
- 先用單表保存 `workflow_yaml` 即可支撐重新登入續用。
- `workflow_yaml` 是正式權威來源；第一階段不保存 `workflow_json`。

## API Contract Draft

註：以下 API 可實作在 AI Hub Flask 端，也可在獨立 App Service 模式下由 Agentic-SDK 呼叫 AI Hub 受管 API；但 owner authority 不得下放到瀏覽器自由指定。

### `GET /api/me/agents`

用途：列出目前登入使用者的 Agent。

回應最小欄位：

```json
{
  "items": [
    {
      "agent_id": "agt_001",
      "agent_name": "我的客服 PoC",
      "description": "客服 FAQ playground",
      "execution_backend": "foundry",
      "updated_at": "2026-06-25T09:00:00Z",
      "last_run_at": "2026-06-25T09:10:00Z"
    }
  ]
}
```

### `POST /api/me/agents`

用途：建立新的 Agent。

請求最小欄位：

```json
{
  "agent_name": "新 Agent",
  "description": "可選描述",
  "workflow_yaml": "name: demo\nentry: perceive\n...",
  "execution_backend": "upstream"
}
```

### `GET /api/me/agents/{agent_id}`

用途：讀取單一 Agent 詳細配置。

### `PUT /api/me/agents/{agent_id}`

用途：更新 Agent 核心配置。

### `DELETE /api/me/agents/{agent_id}`

用途：物理刪除 Agent。

### `POST /api/me/agents/{agent_id}/run`

用途：以已保存的 Agent 配置發起執行。

伺服端流程不變式：

1. 由 session 解析 owner。
2. 由 owner + `agent_id` 載入 Agent。
3. 可接受前端覆蓋 `user_message` 與暫時附件，但不得覆蓋 owner。
4. 轉送到 Agentic-SDK Gateway 執行。

建議請求：

```json
{
  "user_message": "請幫我整理這份需求",
  "attachments": []
}
```

建議回應：

```json
{
  "agent_id": "agt_001",
  "workflow_id": "wf_123",
  "stream_url": "/api/me/agents/agt_001/runs/wf_123/stream",
  "status": "started"
}
```

## Execution Metadata Contract

Flask 對 Gateway 的 server-to-server 呼叫建議附帶：

```json
{
  "workflow_yaml": "...",
  "user_message": "...",
  "attachments": [],
  "metadata": {
    "owner_username": "alice",
    "agent_id": "agt_001",
    "requested_by": "ai-hub-webui"
  }
}
```

即使第一階段 Gateway 尚未完整消費 `metadata`，也應保留欄位，方便後續審計與配額控制。

## Identity Bridge Contract

若採 `Trusted Token Exchange`，需補一份最小 bridge 契約：

```json
{
  "sub": "alice",
  "display_name": "Alice",
  "role": "member",
  "aud": "agentic-sdk-playground",
  "iss": "ai-hub-webui",
  "exp": 1780000000,
  "jti": "tok_001"
}
```

最小要求：

1. token 必須短效。
2. `sub` 對應 `app_user.username`。
3. `aud` 僅限 Agentic-SDK Playground 使用。
4. Agentic-SDK 不得自行擴寫使用者角色權限，只能消費 AI Hub 提供的事實。

## Validation Rules

1. `agent_name` 不可為空。
2. `workflow_yaml` 不可為空，且需通過 Agentic-SDK 現有 config 驗證。
3. `execution_backend` 僅允許目前 runtime 支援的值，例如 `upstream`、`foundry`。
4. `owner_username` 不得由前端提交。
5. 同一位使用者的 `agent_name` 必須唯一。
6. 刪除後的 Agent 直接從正式資料庫移除，不保留軟刪除狀態。

## Phase 1 Locked Decisions

- 保留公開展示版，但不提供正式保存功能。
- 同一位使用者的 Agent 名稱必須唯一。
- 刪除採物理刪除。
- `workflow_yaml` 為權威來源，`workflow_json` 僅作前端快取。
- `workflow_yaml` 為唯一入庫的正式配置來源；第一階段不保存 `workflow_json`。
- 不建立 `agent_workspace_run`，只維護 `last_run_at`。
- 每位使用者第一階段先不限制 Agent 數量。

## Workspace Card Fields For Phase 1

AI Hub 工作區中的 Agent 卡片第一階段固定顯示：

- `agent_name`
- `description`
- `updated_at`
- `last_run_at`
- `execution_backend`

## Deferred Until Later

- 多版本 revision table。
- team / organization shared ownership。
- per-agent secret reference table。
- token quota ledger。
- cross-agent knowledge base permission matrix。