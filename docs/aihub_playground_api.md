# AI Hub Playground Handoff API

當你要把使用者從 AI Hub 導入 Agentic SDK Playground，並決定他是要建立新的 Playground 設定，還是恢復既有的 Playground 設定時，就看這一頁。這一頁只定義進入 Playground 的 handoff API，不重寫 AI Hub 已經定義好的驗證、Agent 清單、config load、config save 契約。

AI Hub 既有 API 以 AI Hub connection model 文件為準：<https://r300-ai.github.io/ai-hub-webui/playground/connection-model/>。

## 這份文件會幫你完成什麼

完成這一頁後，你應該能清楚分辨三種進入 Playground 的方式：

1. 不登入，先在本機試用。
2. AI Hub 已登入使用者要建立新的 Playground 設定。
3. AI Hub 已登入使用者要恢復既有的 Playground 設定。

同時，你也能知道 AI Hub 在什麼情境下應該把使用者送到 Builder，什麼情境下應該直接送到 Runner。

## 開始之前

開始前，先確認三件事：

1. Playground 的來源網域已被 AI Hub 的 Playground Origin 設定允許。
2. 你現在要處理的是匿名試用、新建設定，還是恢復既有設定。
3. 如果要恢復既有設定，AI Hub 已經知道要載入的 `agent_id`。

## 入口模式

| 模式 | 是否帶帳密 | 是否帶 `agent_id` | 進入位置 | 主要結果 |
| --- | --- | --- | --- | --- |
| 匿名試用 | No | No | Builder | 初始化新的預設 `python_source` |
| 已登入，新建設定 | Yes | No | Builder | 建立可編輯的新 Playground 設定 |
| 已登入，恢復既有設定 | Yes | Yes | Runner | 載回既有 `python_source` |

## Base URL

正式 Playground：

```text
https://agentic-sdk-playground.azurewebsites.net
```

所有 API 都必須使用 HTTPS。請勿把 `username`、`password` 或 `agent_id` 放在 query string。

## API Overview

| API | Method | Path | 用途 |
| --- | --- | --- | --- |
| Create Agent Handoff | `POST` | `/playground/aihub/navigation/builder` | AI Hub 已登入使用者建立新的 Playground 設定，成功後進 Builder。 |
| Existing Agent Handoff | `POST` | `/playground/aihub/navigation/runner` | AI Hub 已登入使用者帶 `agent_id` 載入既有 Playground 設定，成功後進 Runner。 |

這兩個 endpoint 是 AI Hub 已登入使用者進入 Playground 的正式入口。Runner 進入後的 save/load/reload 行為會依照 AI Hub connection model 執行，不在本頁重複定義。

匿名試用入口由 Playground 自己提供：

- `POST /playground/start/anonymous`

這條入口不需要 AI Hub 帳密，也不屬於 AI Hub handoff API。

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

## Canonical AI Hub API Contract

以下 API 由 AI Hub 文件定義，本頁只引用，不重寫 request/response：

- 驗證帳密
- 列出使用者 Agent
- 載入指定 Agent config
- 儲存或建立 Agent config

Canonical 文件：<https://r300-ai.github.io/ai-hub-webui/playground/connection-model/>。

## Playground 站內登入流程

Playground 首頁另有互動式登入流程，供使用者直接在 Playground 站內操作：

1. 使用者在首頁送出 `POST /playground/auth/login`。
2. Playground 驗證 AI Hub 帳密後，進入已登入操作狀態。
3. Redirect 到 `/playground/agents`。
4. 使用者在 Agent 清單中選擇：
   - 既有 Agent：載回既有 `python_source`，進 Runner。
   - 新建 Agent：初始化新的預設 `python_source`，進 Builder。

這條流程適合由 Playground 首頁的人類操作觸發。AI Hub 若已經知道使用者要新建還是恢復既有設定，應直接使用本頁定義的 handoff API。

## Browser Handoff Example

瀏覽器 handoff 只是上述 API 的一種提交方式。AI Hub 前端可以用 hidden form 送出 top-level `POST`，讓瀏覽器切到 Playground 並接收 Playground session cookie。

```html
<form method="post" action="https://agentic-sdk-playground.azurewebsites.net/playground/aihub/navigation/runner">
  <input type="hidden" name="username" value="{{ username }}">
  <input type="hidden" name="password" value="{{ password }}">
  <input type="hidden" name="agent_id" value="{{ agent_id }}">
  <button type="submit">在 Playground 編輯</button>
</form>
```

不建議使用 query string 或 cross-origin `fetch` 做 handoff：query string 會留下敏感資訊；`fetch` 不會自然切換使用者畫面，也不適合建立跨站後的瀏覽器 session。

## 建議的下一版安全設計

目前 contract 依需求支援 AI Hub 直接提交帳密給 Playground。正式長期版本建議改成一次性 handoff token：AI Hub 後端發 token，Playground 用 token 向 AI Hub 換取短效 scoped session。這樣可以避免跨系統轉送使用者密碼，也能支援過期、撤銷、audience 限制與 replay protection。