# AI Hub Integration Contract

## 目的

這份文件定義 Playground V2 與 AI Hub 的串接責任邊界、API 使用方式與 UX 約束。

## 來源依據

依據 AI Hub 文件：

`https://r300-ai.github.io/ai-hub-webui/playground/connection-model/`

## 責任邊界

### AI Hub 負責

1. 帳密驗證真偽
2. 既有 Agent 最近 Playground 配置的讀取
3. 最新 Playground 配置的保存
4. 我的 Agents 清單中的保存狀態顯示

### Playground Host 負責

1. 入口頁與登入畫面
2. 匿名模式
3. builder UI 與 runner UI
4. Python code 生成與回朔
5. deep link URL 處理
6. 權限判斷與 UI 顯示差異
7. 依角色與權限自動調整 Runner 的資訊密度與可見操作

## API 參考

| 用途 | 方法與路徑 | 請求內容 | 回應重點 |
| --- | --- | --- | --- |
| 驗證登入帳密 | `POST /api/playground/auth/verify` | `username`, `password` | `valid=true/false` |
| 讀取 Agent 最近配置 | `POST /api/playground/agents/<agent_id>/config/load` | `username`, `password` | `python_source`, `exported_at` |
| 保存 Agent 最新配置 | `POST /api/playground/agents/<agent_id>/config/save` | `username`, `password`, `python_source` | `saved=true`, `exported_at` |

## 必要前提

1. Playground host 的來源網域必須被 AI Hub 允許。
2. 要被回存配置的 Agent 必須存在於使用者的 AI Hub 我的 Agents 清單。
3. 訪客模式不依賴 AI Hub session，也不寫回資料庫。

## 串接流程

### 手動登入流程

1. 使用者在入口頁輸入帳號與密碼。
2. Playground host 呼叫 AI Hub 驗證 API。
3. 驗證成功後，Playground host 自己建立站內 session。
4. 使用者進入建構頁。

### 手動保存流程

1. 使用者完成建構並進試跑頁。
2. 點擊保存到 AI Hub。
3. Playground host 呼叫 save API，提交 `agent_id` 與 `python_source`。
4. AI Hub 返回最新保存時間。

### AI Hub 唯讀導流流程

1. AI Hub 將既有 Workflow 以 deep link 導到 Playground。
2. Playground host 解析既有 source。
3. 直接進入試跑頁唯讀體驗模式。
4. 不允許回建構頁，也不允許保存。

### AI Hub 可回編導流流程

1. AI Hub 導到 Playground。
2. Playground host 取得既有 source 與可編輯帳號上下文。
3. 先進試跑頁。
4. 使用者若要更新，再返回建構頁。
5. 更新後保存回 AI Hub。

## 帳號上下文安全規則

### 不可接受做法

1. 在 URL query string 直接帶明文帳號密碼。
2. 在前端 localStorage 永久保存密碼。

### 可接受做法

1. Playground host 於登入後建立 server-side session。
2. AI Hub 若要支援 deep link 可回編模式，應提供安全上下文，例如 host 可驗證的臨時票證或已知使用者會話識別。

### 若無安全上下文

若 AI Hub 無法安全提供 edit-capable context，Playground 必須自動降級為 readonly 體驗。

## UX 對應要求

### 手動登入

1. 進 builder
2. 可保存
3. 可看 code preview

### AI Hub 唯讀

1. 直接進 runner
2. 不顯示 code preview
3. 不顯示返回建構頁
4. 頁面應優先像任務頁，而不是建立者預覽頁

### AI Hub 可回編

1. 直接進 runner
2. 顯示「回到建構頁更新配置」
3. 顯示保存到 AI Hub
4. 建立者可先在 Runner 中預覽效果，再決定是否回 Builder

Runner 顯示多少建立者資訊，應由 host 依角色與權限自動調整，不必把 `preview` / `direct_use` 當成對外暴露的產品模式名稱。

## 失敗與降級規則

1. 驗證失敗：停留入口頁，提示帳密無效。
2. 來源網域不允許：顯示不可進入錯誤頁。
3. 可讀取配置失敗：若是 AI Hub deep link，顯示專屬錯誤，不導 builder。
4. deep link 標示 editable 但缺安全上下文：降級為 readonly。
5. 保存失敗：停留 runner，顯示失敗原因與重試入口。

## PM 驗收標準

1. 手動登入可以正常驗證並進 builder。
2. 保存回 AI Hub 的 payload 僅以 `python_source` 為核心。
3. AI Hub 唯讀導流不可進 builder。
4. AI Hub 可回編導流可由 runner 返回 builder。
5. 沒有任何設計要求把密碼放進 URL。