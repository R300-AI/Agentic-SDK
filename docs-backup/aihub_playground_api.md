# AI Hub

這一頁說明 AI Hub 如何把使用者帶進 Agentic SDK Playground。使用者可以從首頁進入，也可以由 AI Hub 直接進入 Builder 或 Runner。

AI Hub 驗證、Agent 清單、設定載入與設定保存以 AI Hub connection model 文件為準：<https://r300-ai.github.io/ai-hub-webui/playground/connection-model/>。

原始參考文件、SemanticRetriever vectorstore 與執行資訊會保存成單一 zip bundle；串接方式見 [Storage](aihub_playground_storage_api.md)。

AI Hub 維運文件對應：

| AI Hub 文件 | 這一頁對應內容 | Playground 實作位置 |
| --- | --- | --- |
| [整合自訂遊樂場](https://r300-ai.github.io/ai-hub-webui/platform-maintenance/custom-playground-integration/) | 整合總覽與責任分工 | `Integrations` 章節的 `AI Hub` 與 `Storage` 兩頁 |
| [連線方式與責任邊界](https://r300-ai.github.io/ai-hub-webui/platform-maintenance/custom-playground-integration/connection-and-responsibility/) | 登入、Agent 清單、設定載入與設定保存 | 本頁的入口模式、Playground 入口 API、AI Hub 既有 API |
| [工作流保存與讀回](https://r300-ai.github.io/ai-hub-webui/platform-maintenance/custom-playground-integration/workflow-save-load/) | bundle 保存、讀回與短效 URL | [Storage](aihub_playground_storage_api.md) |

FAE 或 AI Hub 網站開發團隊可以先看 AI Hub 維運文件確認平台責任，再回到本頁查 Playground 實際入口 URL 與表單欄位。

## AI Hub 團隊先看這裡

先用這張表決定要把使用者送到哪裡：

| 使用情境 | AI Hub 要做的事 | Playground 入口 | 需要準備的資料 | 使用者會看到 |
| --- | --- | --- | --- | --- |
| 使用者來源或登入狀態還不明確 | 導向 Playground 首頁 | `GET /playground/` | 無 | 使用者自行選擇 AI Hub 登入或匿名試用 |
| 匿名使用已分享 Agent | 帶 `agent_id` 進入公開 Runner | `GET` / `POST /playground/aihub/navigation/shared-runner` | 可公開載入的 `agent_id` | 唯讀 Runner |
| 已登入使用者要建立新 Agent | 送出 AI Hub handoff token | `POST /playground/aihub/navigation/builder` | `token`、`api_base_url` | Builder |
| 已登入使用者要打開既有 Agent | 送出 AI Hub handoff token 與 `agent_id` | `POST /playground/aihub/navigation/runner` | `token`、`api_base_url`、`agent_id` | 可編輯 Runner |
| 相容 bridge GET 建立新 Agent | 直接導到 Builder | `GET /playground/builder?runtimeMode=managed&apiBase=...&token=...` | AI Hub API base URL 與 bridge token | Builder |
| 相容 bridge GET 編輯既有 Agent | 直接導到 Runner | `GET /playground/run?mode=edit&runtimeMode=managed&apiBase=...&token=...&agentId=...` | AI Hub API base URL、bridge token、`agentId` | 可編輯 Runner |
| AI Hub 公開讀取既有 Agent | 直接導到 Runner | `GET /playground/run?mode=read&owner=...&agentId=...` | `agentId`，可選 `owner` | 唯讀 Runner |

## Playground 頁面階段與入口方式

AI Hub 設計導覽時，請先分清楚「頁面階段」與「handoff API」。`/playground` 是服務首頁；builder / runner handoff 才會建立 AI Hub 帳號與 Agent 狀態。

| 入口方式 | URL / Handoff | 使用情境 | 目標頁面 | 權限狀態 |
| --- | --- | --- | --- | --- |
| Playground 首頁入口 | `GET /playground/` | 未登入使用者、公開入口、單純進入 Playground 服務首頁 | `/playground/` | 尚未建立 AI Hub handoff session；使用者自行選擇登入或匿名試用 |
| Create Agent Handoff | `POST /playground/aihub/navigation/builder` | AI Hub 已登入使用者建立新的 Agent / workflow | `/playground/builder` | 可編輯；使用 `token` 驗證，後續可保存到 AI Hub |
| Existing Agent Handoff | `POST /playground/aihub/navigation/runner` | AI Hub 已登入使用者載入自己擁有或有權編輯的既有 Agent | `/playground/run` | 可編輯；使用 `token` 驗證，`mode=aihub_editable`，可 reload/save |
| Public / Anonymous Runner | `GET` / `POST /playground/aihub/navigation/shared-runner` | 匿名、未登入、或沒有編輯權限但允許公開使用的既有 Agent | `/playground/run` | 可使用、不可編輯；`mode=aihub_readonly` |
| Bridge Builder GET | `GET /playground/builder?runtimeMode=managed&apiBase=...&token=...` | 相容舊版 bridge token direct GET 入口 | `/playground/builder` | 可編輯；後續 save/reload 使用 bridge token 呼叫 AI Hub API |
| Bridge Runner Edit GET | `GET /playground/run?mode=edit&runtimeMode=managed&apiBase=...&token=...&agentId=...` | 相容舊版 bridge token direct GET 入口 | `/playground/run` | 可編輯；`mode=aihub_editable` |
| Bridge Runner Read GET | `GET /playground/run?mode=read&owner=...&agentId=...` | AI Hub WebUI 以公開連結直接送使用者讀取既有 Agent | `/playground/run` | 可使用、不可編輯；`mode=aihub_readonly`，不顯示擁有者限定操作 |
| Runner 頁面 | `GET /playground/run` | 已由首頁、builder、runner handoff 或 shared-runner 建立 Playground session 後進入 | `/playground/run` | 依 session 決定可編輯或唯讀；它本身不是載入既有 Agent 的 handoff API |

導覽規則：

1. 未登入或公開入口導到 `GET /playground/`。
2. 已登入且要新建 Agent，使用 `POST /playground/aihub/navigation/builder`，表單帶 `token` 與 `api_base_url`。
3. 已登入且要開啟自己擁有或有權編輯的既有 Agent，使用 `POST /playground/aihub/navigation/runner`，表單帶 `token`、`api_base_url` 與 `agent_id`。
4. 匿名、未登入、或沒有編輯權限但允許公開使用的既有 Agent，使用 `GET` / `POST /playground/aihub/navigation/shared-runner`，進入可使用但不可編輯的 Runner。
5. 早期或相容工具若使用 bridge token direct GET，Playground 也支援 `/playground/builder` 與 `/playground/run` query string 入口。

`/playground` 不建立 AI Hub handoff session；AI Hub 已登入使用者若要帶入帳號、Agent id 與編輯權限，請使用 handoff API 或 bridge GET。Runner 頁面需要明確標示權限狀態：擁有者或有權限者是可編輯，匿名或公開使用者是可使用但不可編輯。

目前 Playground 支援兩種 AI Hub 入口：API-based handoff 與相容 bridge GET。API-based handoff 由 AI Hub 對 `/playground/aihub/navigation/*` 送出短效 `token`、`api_base_url` 與必要的 `agent_id`；手動帳密欄位仍保留給 Playground 站內登入與相容流程。bridge GET 則可將瀏覽器直接導到 `/playground/builder` 或 `/playground/run`，用 query string 帶 `runtimeMode`、`apiBase`、`token`、`agentId`、`owner` 與 `mode=edit/read`。

舊版 helper 曾使用不含 `/playground` 前綴的 `{PLAYGROUND_ORIGIN}/builder/` 與 `{PLAYGROUND_ORIGIN}/runner/`，Playground 仍保留 alias 並 redirect 到正式頁面；AI Hub 新連結請優先使用 `/playground/builder` 與 `/playground/run`。

對 AI Hub 目前盤點問題的正式回覆：

1. `GET /playground/` 是公開入口頁，支援未登入使用者先進 Playground 自行選擇下一步。
2. AI Hub 已登入使用者要建立 Agent 時，正式路徑是 `POST /playground/aihub/navigation/builder` 搭配短效 token；相容路徑可用 `GET /playground/builder?runtimeMode=managed&apiBase=...&token=...`。
3. AI Hub 已登入使用者要以可編輯狀態開啟既有 Agent 時，正式路徑是 `POST /playground/aihub/navigation/runner` 搭配短效 token 與 `agent_id`；相容路徑可用 `GET /playground/run?mode=edit&runtimeMode=managed&apiBase=...&token=...&agentId=...`。成功後 Playground 設定 `mode=aihub_editable`。
4. 匿名、未登入、或公開使用既有 Agent 的 read-only Runner 可用 `GET` / `POST /playground/aihub/navigation/shared-runner`，也可用 `GET /playground/run?mode=read&owner=...&agentId=...`。成功後 Playground 設定 `mode=aihub_readonly`，並隱藏保存、重新載入為擁有者等 owner-only controls。

AI Hub 端需要提供三類能力：

1. 驗證帳密或 handoff token，讓 Playground 建立已登入操作狀態；驗證成功時可回傳帳戶層級 `display_name`，Runner 問候會優先使用 `display_name`，空值時回到帳號。
2. 依 `agent_id` 載入既有 Playground 設定，回傳 `python_source`。
3. 對已分享 Agent 提供公開載入能力，讓匿名使用者進入唯讀 Runner。

如果 Agent 使用 `SemanticRetrieve` 並上傳過參考文件，只保存 `python_source` 不算完整保存。AI Hub 還需要依 [Storage](aihub_playground_storage_api.md) 提供 bundle save/load URL，否則重新打開 Agent 時只能恢復流程設定，無法恢復原本的參考文件與 vectorstore。

## 這份文件會幫你完成什麼

完成這一頁後，你應該能清楚分辨四種進入 Playground 的方式：

1. 來源未知或未登入的使用者進入 Playground 首頁，自行選擇 AI Hub 登入或匿名試用。
2. 匿名使用者直接使用別人已建好的 Agent，進入唯讀 Runner 對話。
3. AI Hub 已登入使用者要建立新的 Playground 設定。
4. AI Hub 已登入使用者要恢復既有的 Playground 設定。

同時，你也能知道 AI Hub 在什麼情境下把使用者送到 Builder，什麼情境下直接送到 Runner。

## 開始之前

開始前，先確認三件事：

1. Playground 的來源網域已被 AI Hub 的 Playground Origin 設定允許。
2. 你現在是否已經知道使用者來源、存取模式，以及要新建設定、匿名使用分享 Agent，還是恢復既有設定。
3. 如果要恢復既有設定，AI Hub 已經知道要載入的 `agent_id`。

## 入口模式細節

| 模式 | 是否帶帳密 | 是否帶 `agent_id` | 進入位置 | 主要結果 |
| --- | --- | --- | --- | --- |
| 來源未知 / 未登入 | No | No | `/playground/` 首頁 | 使用者選擇 AI Hub 登入或匿名試用 |
| 匿名使用已分享 Agent | No | Yes | Runner | 載入公開/分享的 `python_source`，進入唯讀對話 |
| 已登入，新建設定 | Token 或站內帳密 | No | Builder | 建立可編輯的新 Playground 設定 |
| 已登入，恢復既有設定 | Token 或站內帳密 | Yes | Runner | 載回既有 `python_source`；若有 SemanticRetrieve bundle，會一併還原參考文件與 vectorstore |

## Base URL

正式 Playground：

```text
https://agentic-sdk-playground.azurewebsites.net
```

所有 API 都使用 HTTPS。正式 AI Hub handoff 的 `token`、`api_base_url` 與 `agent_id` 放在 request body；手動登入相容流程的 `username`、`password` 與 `agent_id` 也放在 request body。`shared-runner` 與公開 Runner 也支援用 `GET` query string 帶 `agent_id` / `agentId`，公開 Runner 可附帶 `owner`。

## Playground 入口 API

| API | Method | Path | 用途 |
| --- | --- | --- | --- |
| 匿名 Runner 入口 | `GET` / `POST` | `/playground/aihub/navigation/shared-runner` | 匿名使用者載入已分享 Agent，成功後進唯讀 Runner。 |
| 新建設定入口 | `POST` | `/playground/aihub/navigation/builder` | AI Hub 已登入使用者以 handoff token 建立新的 Playground 設定，成功後進 Builder。 |
| 既有設定入口 | `POST` | `/playground/aihub/navigation/runner` | AI Hub 已登入使用者以 handoff token 與 `agent_id` 載入既有 Playground 設定，成功後進 Runner。 |

`shared-runner` 是匿名使用已分享 Agent 的入口，進入後提供唯讀 Runner。`builder` 與 `runner` 是 AI Hub 已登入使用者進入 Playground 的正式入口。Runner 進入後的 save/load/reload 行為依照 AI Hub connection model 執行。

匿名試用入口由 Playground 自己提供：

- `GET /playground/`
- `POST /playground/start/anonymous`

AI Hub 或其他外部入口需要讓使用者自行選擇登入或匿名試用時，可以導向 `GET /playground/`。Playground 首頁會呈現「AI Hub 登入」與「匿名試用」兩種選擇。`POST /playground/start/anonymous` 是首頁表單提交後建立匿名 session 的內部入口。

## GET / POST /playground/aihub/navigation/shared-runner

AI Hub 用這個入口讓未登入使用者直接使用已分享的 Agent。Playground 會進入 `aihub_readonly` 模式，畫面只提供 Runner 對話能力。

AI Hub 會用公開載入 API 判斷該 `agent_id` 是否允許匿名使用。

### Request

支援 query string、`application/x-www-form-urlencoded` 或 `application/json`。

```http
GET /playground/aihub/navigation/shared-runner?agent_id=agt_public_123 HTTP/1.1
Host: agentic-sdk-playground.azurewebsites.net
```

或：

```http
POST /playground/aihub/navigation/shared-runner HTTP/1.1
Host: agentic-sdk-playground.azurewebsites.net
Content-Type: application/json

{"agent_id":"agt_public_123"}
```

| 欄位 | 型別 | 必填 | 說明 |
| --- | --- | --- | --- |
| `agent_id` | string | Yes | 要匿名使用的 AI Hub Agent id。AI Hub 必須確認此 Agent 可被分享或公開使用。 |

### Playground 對 AI Hub 的載入呼叫

Playground 會呼叫 AI Hub 的公開載入 API：

```http
POST /api/playground/agents/<agent_id>/config/public/load
Content-Type: application/json

{}
```

成功回傳至少需要包含 `python_source`；可選包含 `agent_id`、`agent_name`、`workflow_name`、`description`、`playground_exported_at`。

### Success Response

```http
HTTP/1.1 302 Found
Location: /playground/run
Set-Cookie: session=...
```

Playground 會完成以下動作：

1. 以公開載入 API 回傳的 `python_source` 建立 Runner session。
2. 保持匿名使用狀態。
3. 設定 `mode=aihub_readonly` 與 `source_origin=aihub_shared_readonly`。
4. Redirect 到 `/playground/run`。

### 唯讀 Runner 能力

匿名 shared Runner 提供以下能力：

- 可以送出訊息並取得 Agent 回覆。
- 畫面停留在 Runner。
- Agent 設定由 AI Hub 的公開載入結果提供。
- 不提供保存、reload 為擁有者、編輯設定或其他 owner-only controls。

### Error Response

| 狀態碼 | 條件 | 行為 |
| --- | --- | --- |
| `400` | `agent_id` 缺漏 | 回傳登入頁 HTML，顯示 `Missing AI Hub agent id.`。 |
| `502` | AI Hub public load 失敗或拒絕匿名使用 | 回傳登入頁 HTML，顯示 AI Hub public load 錯誤。 |

## POST /playground/aihub/navigation/builder

AI Hub 用這個 API 讓已登入使用者直接進入 Playground Builder，建立新的 Agent config。正式 AI Hub WebUI 送出短效 handoff token；`username` / `password` 欄位保留給手動登入或相容流程。

### Request

支援 `application/x-www-form-urlencoded` 或 `application/json`。

```http
POST /playground/aihub/navigation/builder HTTP/1.1
Host: agentic-sdk-playground.azurewebsites.net
Content-Type: application/x-www-form-urlencoded

token=<handoff-token>&api_base_url=https://ai-hub-portal.azurewebsites.net
```

| 欄位 | 型別 | 必填 | 說明 |
| --- | --- | --- | --- |
| `token` | string | Yes，正式 handoff 使用 | AI Hub 簽發的短效 handoff token。 |
| `api_base_url` | string | Yes，正式 handoff 使用 | AI Hub public base URL，供 Playground 驗證 token 與後續呼叫 API。 |
| `username` | string | 相容流程使用 | AI Hub 使用者帳號。 |
| `password` | string | 相容流程使用 | AI Hub 使用者密碼。 |

### Success Response

```http
HTTP/1.1 302 Found
Location: /playground/builder
Set-Cookie: session=...
```

Playground 會完成以下動作：

1. 呼叫 AI Hub `POST /api/playground/handoff/verify` 驗證 token；相容帳密流程則呼叫 `POST /api/playground/auth/verify`。
2. 建立可供後續 save/reload 使用的已登入 Playground 編輯上下文。
3. 以新的預設 `python_source` 開始一份新設定。
4. Redirect 到 `/playground/builder`。

### Error Response

| 狀態碼 | 條件 | 行為 |
| --- | --- | --- |
| `400` | `token` / `api_base_url` 缺漏、token 無效，或相容帳密流程驗證失敗 | 回傳登入頁 HTML，顯示驗證錯誤。 |

## POST /playground/aihub/navigation/runner

AI Hub 用這個 API 讓已登入使用者直接載入某個已保存過的 Agent config，並進入 Runner。正式 AI Hub WebUI 送出短效 handoff token；`username` / `password` 欄位保留給手動登入或相容流程。

### Request

支援 `application/x-www-form-urlencoded` 或 `application/json`。

```http
POST /playground/aihub/navigation/runner HTTP/1.1
Host: agentic-sdk-playground.azurewebsites.net
Content-Type: application/x-www-form-urlencoded

token=<handoff-token>&api_base_url=https://ai-hub-portal.azurewebsites.net&agent_id=agt_dbc780b2d07445ef
```

| 欄位 | 型別 | 必填 | 說明 |
| --- | --- | --- | --- |
| `token` | string | Yes，正式 handoff 使用 | AI Hub 簽發的短效 handoff token。 |
| `api_base_url` | string | Yes，正式 handoff 使用 | AI Hub public base URL，供 Playground 驗證 token 與後續呼叫 API。 |
| `agent_id` | string | Yes | AI Hub Agent id。必須是該使用者可讀寫的 Agent。 |
| `username` | string | 相容流程使用 | AI Hub 使用者帳號。 |
| `password` | string | 相容流程使用 | AI Hub 使用者密碼。 |

### Success Response

```http
HTTP/1.1 302 Found
Location: /playground/run
Set-Cookie: session=...
```

Playground 會完成以下動作：

1. 呼叫 AI Hub `POST /api/playground/handoff/verify` 驗證 token；相容帳密流程則呼叫 `POST /api/playground/auth/verify`。
2. 建立可供後續 save/reload 使用的已登入 Playground 編輯上下文。
3. 依 AI Hub connection model 載入指定 `agent_id` 的 Playground config。
4. Redirect 到 `/playground/run`。

### Error Response

| 狀態碼 | 條件 | 行為 |
| --- | --- | --- |
| `400` | `agent_id` 缺漏 | 回傳登入頁 HTML，顯示 `Missing AI Hub agent id.`。 |
| `400` | `token` / `api_base_url` 缺漏、token 無效，或相容帳密流程驗證失敗 | 回傳登入頁 HTML，顯示驗證錯誤。 |
| `502` | AI Hub connection model 的 config load 失敗 | 回傳登入頁 HTML，顯示 AI Hub load 錯誤。 |

## AI Hub 既有 API

以下 API 由 AI Hub 文件定義，本頁引用它們作為 Playground 入口流程的一部分：

- 驗證帳密或 handoff token，並回傳 `username` 與帳戶層級 `display_name`
- 列出使用者 Agent
- 載入指定 Agent config
- 儲存或建立 Agent config

AI Hub 文件：<https://r300-ai.github.io/ai-hub-webui/playground/connection-model/>。

## Playground 站內登入流程

Playground 首頁另有互動式登入流程，供使用者直接在 Playground 站內操作：

1. 使用者先進入 `GET /playground/`。
2. 若選擇 AI Hub 登入，首頁送出 `POST /playground/auth/login`。
3. Playground 驗證 AI Hub 帳密後，進入已登入操作狀態。
4. Redirect 到 `/playground/agents`。
5. 使用者在 Agent 清單中選擇：
   - 既有 Agent：載回既有 `python_source`，進 Runner。
   - 新建 Agent：初始化新的預設 `python_source`，進 Builder。
6. 若使用者在首頁選擇匿名試用，首頁送出 `POST /playground/start/anonymous`，Playground 建立匿名 session 並進 Builder；設定留在本機 session。
7. 若使用者是透過已分享 Agent 連結進入，外部入口使用 `/playground/aihub/navigation/shared-runner`，直接進唯讀 Runner。

這條流程適合由 Playground 首頁的人類操作觸發。AI Hub 已經知道使用者狀態與目標時，可以直接使用本頁定義的入口 API。

## 瀏覽器送出範例

瀏覽器可以用表單提交上述 API。AI Hub 前端可以用 hidden form 送出 top-level `POST`，讓瀏覽器切到 Playground 並接收 Playground session cookie。

```html
<form method="post" action="https://agentic-sdk-playground.azurewebsites.net/playground/aihub/navigation/runner">
  <input type="hidden" name="token" value="{{ handoff_token }}">
  <input type="hidden" name="api_base_url" value="https://ai-hub-portal.azurewebsites.net">
  <input type="hidden" name="agent_id" value="{{ agent_id }}">
  <button type="submit">在 Playground 編輯</button>
</form>
```

建議用 top-level form POST。這種方式會切換使用者畫面，也能讓 Playground 建立瀏覽器 session。正式 AI Hub handoff 應把 `token`、`api_base_url` 與 `agent_id` 放在表單 body；帳號與密碼只用於 Playground 站內登入或相容流程。

## 建議的下一版安全設計

目前正式 AI Hub WebUI 已改用短效 handoff token：AI Hub 後端發 token，Playground 用 token 向 AI Hub 驗證並建立短效 session。帳密流程仍保留給 Playground 站內登入與相容呼叫；維運時應優先確認 token、`api_base_url`、`agent_id` 與 `display_name` 是否沿著 handoff 驗證回應進入 Playground session。