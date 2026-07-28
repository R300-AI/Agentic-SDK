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
| 已登入使用者要建立新 Agent | 送出 AI Hub 帳密 | `POST /playground/aihub/navigation/builder` | `username`、`password` | Builder |
| 已登入使用者要打開既有 Agent | 送出 AI Hub 帳密與 `agent_id` | `POST /playground/aihub/navigation/runner` | `username`、`password`、`agent_id` | Runner |

## Playground 頁面階段與入口方式

AI Hub 設計導覽時，請先分清楚「頁面階段」與「handoff API」。`/playground` 是服務首頁；builder / runner handoff 才會建立 AI Hub 帳號與 Agent 狀態。

| 入口方式 | URL / Handoff | 使用情境 | 目標頁面 | 權限狀態 |
| --- | --- | --- | --- | --- |
| Playground 首頁入口 | `GET /playground/` | 未登入使用者、公開入口、單純進入 Playground 服務首頁 | `/playground/` | 尚未建立 AI Hub handoff session；使用者自行選擇登入或匿名試用 |
| Create Agent Handoff | `POST /playground/aihub/navigation/builder` | AI Hub 已登入使用者建立新的 Agent / workflow | `/playground/builder` | 可編輯；後續可保存到 AI Hub |
| Existing Agent Handoff | `POST /playground/aihub/navigation/runner` | AI Hub 已登入使用者載入自己擁有或有權編輯的既有 Agent | `/playground/run` | 可編輯；`mode=aihub_editable`，可 reload/save |
| Public / Anonymous Runner | `GET` / `POST /playground/aihub/navigation/shared-runner` | 匿名、未登入、或沒有編輯權限但允許公開使用的既有 Agent | `/playground/run` | 可使用、不可編輯；`mode=aihub_readonly` |
| Runner 頁面 | `GET /playground/run` | 已由首頁、builder、runner handoff 或 shared-runner 建立 Playground session 後進入 | `/playground/run` | 依 session 決定可編輯或唯讀；它本身不是載入既有 Agent 的 handoff API |

導覽規則：

1. 未登入或公開入口導到 `GET /playground/`。
2. 已登入且要新建 Agent，使用 `POST /playground/aihub/navigation/builder`。
3. 已登入且要開啟自己擁有或有權編輯的既有 Agent，使用 `POST /playground/aihub/navigation/runner`。
4. 匿名、未登入、或沒有編輯權限但允許公開使用的既有 Agent，使用 `GET` / `POST /playground/aihub/navigation/shared-runner`，進入可使用但不可編輯的 Runner。

`/playground` 不建立 AI Hub handoff session；AI Hub 已登入使用者若要帶入帳號、Agent id 與編輯權限，應使用 builder 或 runner handoff。Runner 頁面需要明確標示權限狀態：擁有者或有權限者是可編輯，匿名或公開使用者是可使用但不可編輯。

目前 AI Hub WebUI 維運文件描述的是 API-based integration：Playground 作為外部自訂遊樂場服務，呼叫 AI Hub 的 auth、config、bundle API 完成登入、載入、保存與讀回。若要改成 AI Hub 以 bridge token query string 直接導入頁面，需另行定義相容入口；那不是目前三份維運文件中的既有契約。

目前正式 handoff 入口不是下列直接頁面 URL：

```text
{PLAYGROUND_ORIGIN}/builder/
{PLAYGROUND_ORIGIN}/runner/
{PLAYGROUND_ORIGIN}/runner/?mode=edit
{PLAYGROUND_ORIGIN}/runner/?mode=read
```

如果 AI Hub 只要產生一般頁面 URL，路徑保留 `/playground` 前綴：`/playground/`、`/playground/builder`、`/playground/run`。如果 AI Hub 要帶入帳號、`agent_id` 或公開 Agent 狀態，請使用本頁定義的 handoff API。`runtimeMode`、`token`、`owner` 或 `mode=edit/read` query string 可作為 bridge-token 相容模式的設計項目，但需要與目前 API-based 契約分開定義與測試。

AI Hub 端需要提供三類能力：

1. 驗證帳密，讓 Playground 建立已登入操作狀態。
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
| 已登入，新建設定 | Yes | No | Builder | 建立可編輯的新 Playground 設定 |
| 已登入，恢復既有設定 | Yes | Yes | Runner | 載回既有 `python_source`；若有 SemanticRetrieve bundle，會一併還原參考文件與 vectorstore |

## Base URL

正式 Playground：

```text
https://agentic-sdk-playground.azurewebsites.net
```

所有 API 都使用 HTTPS。`POST` 入口的 `username`、`password` 與 `agent_id` 放在 request body；`shared-runner` 也支援用 `GET` query string 帶 `agent_id`。

## Playground 入口 API

| API | Method | Path | 用途 |
| --- | --- | --- | --- |
| 匿名 Runner 入口 | `GET` / `POST` | `/playground/aihub/navigation/shared-runner` | 匿名使用者載入已分享 Agent，成功後進唯讀 Runner。 |
| 新建設定入口 | `POST` | `/playground/aihub/navigation/builder` | AI Hub 已登入使用者建立新的 Playground 設定，成功後進 Builder。 |
| 既有設定入口 | `POST` | `/playground/aihub/navigation/runner` | AI Hub 已登入使用者帶 `agent_id` 載入既有 Playground 設定，成功後進 Runner。 |

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

### Error Response

| 狀態碼 | 條件 | 行為 |
| --- | --- | --- |
| `400` | `agent_id` 缺漏 | 回傳登入頁 HTML，顯示 `Missing AI Hub agent id.`。 |
| `502` | AI Hub public load 失敗或拒絕匿名使用 | 回傳登入頁 HTML，顯示 AI Hub public load 錯誤。 |

## POST /playground/aihub/navigation/builder

AI Hub 用這個 API 讓已登入使用者直接進入 Playground Builder，建立新的 Agent config。

### Request

支援 `application/x-www-form-urlencoded` 或 `application/json`。

```http
POST /playground/aihub/navigation/builder HTTP/1.1
Host: agentic-sdk-playground.azurewebsites.net
Content-Type: application/x-www-form-urlencoded

username=admin&password=admin
```

| 欄位 | 型別 | 必填 | 說明 |
| --- | --- | --- | --- |
| `username` | string | Yes | AI Hub 使用者帳號。 |
| `password` | string | Yes | AI Hub 使用者密碼。 |

### Success Response

```http
HTTP/1.1 302 Found
Location: /playground/builder
Set-Cookie: session=...
```

Playground 會完成以下動作：

1. 呼叫 AI Hub `POST /api/playground/auth/verify` 驗證帳密。
2. 建立可供後續 save/reload 使用的已登入 Playground 編輯上下文。
3. 以新的預設 `python_source` 開始一份新設定。
4. Redirect 到 `/playground/builder`。

### Error Response

| 狀態碼 | 條件 | 行為 |
| --- | --- | --- |
| `400` | `username` / `password` 缺漏或驗證失敗 | 回傳登入頁 HTML，顯示驗證錯誤。 |

## POST /playground/aihub/navigation/runner

AI Hub 用這個 API 讓已登入使用者直接載入某個已保存過的 Agent config，並進入 Runner。

### Request

支援 `application/x-www-form-urlencoded` 或 `application/json`。

```http
POST /playground/aihub/navigation/runner HTTP/1.1
Host: agentic-sdk-playground.azurewebsites.net
Content-Type: application/x-www-form-urlencoded

username=admin&password=admin&agent_id=agt_dbc780b2d07445ef
```

| 欄位 | 型別 | 必填 | 說明 |
| --- | --- | --- | --- |
| `username` | string | Yes | AI Hub 使用者帳號。 |
| `password` | string | Yes | AI Hub 使用者密碼。 |
| `agent_id` | string | Yes | AI Hub Agent id。必須是該使用者可讀寫的 Agent。 |

### Success Response

```http
HTTP/1.1 302 Found
Location: /playground/run
Set-Cookie: session=...
```

Playground 會完成以下動作：

1. 呼叫 AI Hub `POST /api/playground/auth/verify` 驗證帳密。
2. 建立可供後續 save/reload 使用的已登入 Playground 編輯上下文。
3. 依 AI Hub connection model 載入指定 `agent_id` 的 Playground config。
4. Redirect 到 `/playground/run`。

### Error Response

| 狀態碼 | 條件 | 行為 |
| --- | --- | --- |
| `400` | `agent_id` 缺漏 | 回傳登入頁 HTML，顯示 `Missing AI Hub agent id.`。 |
| `400` | `username` / `password` 缺漏或驗證失敗 | 回傳登入頁 HTML，顯示驗證錯誤。 |
| `502` | AI Hub connection model 的 config load 失敗 | 回傳登入頁 HTML，顯示 AI Hub load 錯誤。 |

## AI Hub 既有 API

以下 API 由 AI Hub 文件定義，本頁引用它們作為 Playground 入口流程的一部分：

- 驗證帳密
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
  <input type="hidden" name="username" value="{{ username }}">
  <input type="hidden" name="password" value="{{ password }}">
  <input type="hidden" name="agent_id" value="{{ agent_id }}">
  <button type="submit">在 Playground 編輯</button>
</form>
```

建議用 top-level form POST。這種方式會切換使用者畫面，也能讓 Playground 建立瀏覽器 session。帳號、密碼與 `agent_id` 應放在表單 body。

## 建議的下一版安全設計

目前流程依需求支援 AI Hub 直接提交帳密給 Playground。正式長期版本建議改成一次性進入 token：AI Hub 後端發 token，Playground 用 token 向 AI Hub 換取短效 session。這樣可以集中管理過期、撤銷、使用範圍與重放保護。