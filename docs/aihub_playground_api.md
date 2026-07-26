# AI Hub Playground API

這份文件是給 AI Hub 串接 Agentic SDK Playground 使用的 API contract。重點不是一般使用者導覽，而是 AI Hub 在「使用者已登入」的狀態下，如何把必要資訊交給 Playground，讓 Playground 建立自己的 session 並進入 Builder 或 Runner。

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
| Save Current Config | `POST` | `/playground/aihub/config/save` | Runner 儲存目前 Playground config 到 AI Hub。 |
| Reload Current Config | `POST` | `/playground/aihub/config/reload` | Runner 重新從 AI Hub 載入目前 `agent_id` 的 config。 |

前兩個 handoff API 是 AI Hub 進入 Playground 的入口；後兩個 API 是 Playground Runner 進入後使用的 session API。

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
3. 建立 AI Hub credential ticket，供後續 save/reload 使用。
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
3. 呼叫 AI Hub `POST /api/playground/agents/<agent_id>/config/load` 載入 config。
4. 建立 Playground server-side session。
5. 設定 `mode=aihub_editable`。
6. 寫入 `agent_id`、`agent_name`、`python_source`、`source_origin=aihub_loaded`。
7. Redirect 到 `/playground/run`。

### Error Response

| 狀態碼 | 條件 | 行為 |
| --- | --- | --- |
| `400` | `agent_id` 缺漏 | 回傳登入頁 HTML，顯示 `Missing AI Hub agent id.`。 |
| `400` | `username` / `password` 缺漏或驗證失敗 | 回傳登入頁 HTML，顯示驗證錯誤。 |
| `502` | AI Hub config load 失敗 | 回傳登入頁 HTML，顯示 AI Hub load 錯誤。 |

## POST /playground/aihub/config/save

這是 Runner 裡的 session API。AI Hub 不需要直接呼叫它；使用者在 Runner 按「儲存」時，Playground 前端會呼叫此 API。

### Request

```http
POST /playground/aihub/config/save HTTP/1.1
Cookie: session=...
Content-Type: application/json

{}
```

可選 payload：

| 欄位 | 型別 | 必填 | 說明 |
| --- | --- | --- | --- |
| `agent_id` | string | No | 若提供，覆蓋 session 裡的 `agent_id`。 |
| `python_source` | string | No | 若提供，覆蓋 session 裡的 `python_source`。 |

### Success Response

```json
{
  "saved": true,
  "agent_id": "agt_dbc780b2d07445ef",
  "agent_name": "Playground Agent - admin",
  "integration_status": "aihub",
  "requires_real_aihub_api": false
}
```

如果 session 尚無 `agent_id`，Playground 會呼叫 AI Hub `POST /api/playground/config/save` 並讓 AI Hub 建立新 Agent。AI Hub 回傳 `agent_id` 後，Playground 會把它保存到 session，後續 save/reload 都會針對同一個 Agent。

### Error Response

| 狀態碼 | 條件 |
| --- | --- |
| `403` | 目前 session 不是可儲存模式，或 Origin 不允許。 |
| `401` | session 沒有 AI Hub credential ticket。 |
| `400` | 沒有可儲存的 `python_source`。 |
| `502` | AI Hub save API 失敗。 |

## POST /playground/aihub/config/reload

這是 Runner 裡的 session API。使用者按「重新載入」時，Playground 會用 session 裡的 `agent_id` 重新向 AI Hub 取得 config。

### Request

```http
POST /playground/aihub/config/reload HTTP/1.1
Cookie: session=...
```

### Success Response

```json
{
  "loaded": true,
  "agent_id": "agt_dbc780b2d07445ef",
  "agent_name": "Playground Agent - admin",
  "python_source": "..."
}
```

### Error Response

| 狀態碼 | 條件 |
| --- | --- |
| `403` | Origin 不允許。 |
| `401` | session 沒有 AI Hub credential ticket。 |
| `502` | AI Hub load API 失敗。 |

## AI Hub Upstream API Requirements

Playground 會呼叫 AI Hub 這些 API。這些 API 位於 `AI_HUB_BASE_URL`，目前正式設定為：

```text
https://ai-hub-portal.azurewebsites.net
```

| AI Hub API | Method | 說明 |
| --- | --- | --- |
| `/api/playground/auth/verify` | `POST` | 驗證 `username` / `password` 是否合法。 |
| `/api/playground/agents` | `POST` | 列出該帳號可用 Agent。 |
| `/api/playground/agents/<agent_id>/config/load` | `POST` | 載入指定 Agent 的 Playground config。 |
| `/api/playground/config/save` | `POST` | 儲存 config；沒有 `agent_id` 時建立新 Agent，有 `agent_id` 時更新既有 Agent。 |

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