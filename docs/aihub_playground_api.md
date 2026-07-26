# AI Hub Playground Handoff API

這份文件只定義 AI Hub 進入 Agentic SDK Playground 的 handoff API。AI Hub 已經定義好的 Agent list、config load、config save 等 API，以 AI Hub connection model 文件為準：<https://r300-ai.github.io/ai-hub-webui/playground/connection-model/>。

本頁不重新定義 AI Hub 的 save/load request 或 response，避免兩邊文件 drift。

## Base URL

正式 Playground：

```text
https://agentic-sdk-playground.azurewebsites.net
```

所有 API 都必須使用 HTTPS。請勿把 `username`、`password` 或 `agent_id` 放在 query string。

## API Overview

| API | Method | Path | 用途 |
| --- | --- | --- | --- |
| Create Agent Handoff | `POST` | `/playground/aihub/navigation/builder` | AI Hub 已登入使用者直接建立新 Agent，成功後進 Builder。 |
| Existing Agent Handoff | `POST` | `/playground/aihub/navigation/runner` | AI Hub 已登入使用者帶 `agent_id` 載入既有 Agent，成功後進 Runner。 |

這兩個 endpoint 是 AI Hub 把已登入使用者送入 Playground 的入口。Runner 進入後的 save/load/reload 行為會依照 AI Hub connection model 執行，不在本頁重複定義。

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
2. 建立 Playground server-side session。
3. 建立 AI Hub credential ticket，供後續依 AI Hub connection model 執行 save/reload 時使用。
4. 清除舊的 `agent_id`、`agent_name`、`last_aihub_save`。
5. 初始化預設 `python_source`。
6. Redirect 到 `/playground/builder`。

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
2. 清除目前瀏覽器上的舊 Playground session 狀態。
3. 依 AI Hub connection model 載入指定 `agent_id` 的 Playground config。
4. 建立 Playground server-side session。
5. 設定 `mode=aihub_editable`。
6. 寫入 `agent_id`、`agent_name`、`python_source`、`source_origin=aihub_loaded`。
7. Redirect 到 `/playground/run`。

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