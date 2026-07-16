# Roles, Modes, and Permissions

## 目的

這份文件定義 Playground V2 的使用模式與權限矩陣。所有頁面、按鈕、deep link 行為與保存能力，都必須以此矩陣為準。

## 模式定義

本文件有兩個維度：

1. `Mode`：使用者如何進站、是否有帳號上下文
2. `Role`：使用者在實際場域中的責任，是建立者還是直接使用者

Mode 不等於 Role。同樣是已登入使用者，可能是建立者，也可能只是有權限的內部直接使用者。

## 角色定義

### Role 1: 建立者

例如 FAE、行政、產品助理、內部營運人員。主要工作是進 Builder 建立、調整、試跑與保存 Agent。

### Role 2: 直接使用者

例如門市人員、客服人員、照護助理、外勤、顧客。主要工作是在 Runner 直接完成任務，而不是理解 workflow 結構。

### Role 3: 回編使用者

可先以直接使用者身份體驗既有 Agent，但在特定權限下也可返回 Builder 更新配置。

### 角色硬規則

1. 建立者會使用 Entry、Builder、Runner 三個頁面。
2. 直接使用者只會接觸 Runner。
3. 對建立者來說，Runner 是預覽實際效果的地方；對直接使用者來說，Runner 是完成任務的地方。

### Mode A: 手動匿名模式

使用者從入口頁主動選擇匿名使用，不依賴 AI Hub 登入，也不保存到 AI Hub。

### Mode B: 手動登入模式

使用者從入口頁登入 AI Hub 帳密，經驗證後進入建構頁。這是完整建立與保存模式。

### Mode C: AI Hub 導流唯讀體驗模式

使用者從 AI Hub deep link 直接進入既有 Workflow 的試跑頁，但沒有可編輯帳號上下文，只能體驗。

### Mode D: AI Hub 導流可回編模式

使用者從 AI Hub deep link 直接進入既有 Workflow 的試跑頁，且帶有可編輯帳號上下文，可回建構頁更新配置並保存回 AI Hub。

## 權限矩陣

| 能力 | Mode A 匿名 | Mode B 手動登入 | Mode C AI Hub 唯讀 | Mode D AI Hub 可回編 |
| --- | --- | --- | --- | --- |
| 看到入口頁 | 是 | 是 | 否 | 否 |
| 直接進建構頁 | 是 | 是 | 否 | 否 |
| 直接進試跑頁 | 否 | 否 | 是 | 是 |
| 試跑互動 | 是 | 是 | 是 | 是 |
| 上傳附件 | 視 Workflow 能力而定 | 視 Workflow 能力而定 | 視 Workflow 能力而定 | 視 Workflow 能力而定 |
| 查看 code preview | 是 | 是 | 否 | 是 |
| 匯出 `.py` | 是 | 是 | 否 | 是 |
| 保存到 AI Hub | 否 | 是 | 否 | 是 |
| 返回建構頁 | 是 | 是 | 否 | 是 |
| 修改模組配置 | 是 | 是 | 否 | 是 |
| 顯示 Workflow 細節 | 是 | 是 | 否 | 受限顯示 |

## 角色導向 UI 原則

### 建立者

1. 可看到 Builder
2. 在 Runner 中可看到較完整的預覽與調整入口
3. 需要知道目前 Agent 是否已準備好交給第一線使用

### 直接使用者

1. 預設只看到 Runner
2. 不需要理解 module、workflow、source 或 code preview
3. 應優先看到任務、輸入區、結果、依據與下一步操作

### 回編使用者

1. 預設仍先看到 Runner
2. 只有在具備明確權限與上下文時，才看到返回 Builder 的入口

## UI 顯示規則

### 入口頁

只對 Mode A 與 Mode B 顯示。

### 建構頁

對 Mode A 與 Mode B 顯示。

對 Mode D，只能由試跑頁上的「回到建構頁更新配置」操作進入，不可從入口直接進來。

但產品假設 Builder 的主要使用者是建立者，而不是直接使用者。

### 試跑頁

所有模式都會使用試跑頁，但有不同操作層級。

試跑頁在產品上只有一個頁面；系統可依角色與權限，自動調整資訊密度與可見操作。

#### 試跑頁共同內容

1. Agent/Workflow 名稱
2. 聊天互動區
3. 執行結果
4. Powered by Agentic SDK 標記

#### 試跑頁受限內容

1. code preview
2. 保存到 AI Hub
3. 返回建構頁
4. 進階 workflow 摘要

## AI Hub 導流模式差異

Mode C 與 Mode D 的差異，不是頁面不同，而是頁面操作權限不同。

### Mode C 顯示原則

應盡量讓頁面看起來像「產品互動頁」，而不是「可編輯的 Playground」。

### Mode D 顯示原則

預設仍先落在試跑頁，但必須清楚告知：

1. 這是既有 Workflow
2. 你可以先體驗
3. 也可以返回建構頁更新後保存回 AI Hub

## 權限判定來源

模式必須由以下資訊判定：

1. 是否為手動進站
2. 是否通過 AI Hub deep link 導入
3. 是否存在已驗證的帳號上下文
4. 是否存在既有 Workflow source string

## 不可接受的設計

1. 在 Mode C 顯示 code preview。
2. 在 Mode C 顯示返回建構頁按鈕。
3. 在 Mode A 顯示保存到 AI Hub。
4. 在 Mode D 讓使用者不清楚自己是否正在更新 AI Hub 既有 Workflow。

## PM 驗收清單

1. 不同模式是否正確顯示/隱藏對應按鈕。
2. AI Hub 唯讀模式是否無法回建構頁。
3. AI Hub 可回編模式是否能由試跑頁回建構頁。
4. 手動登入模式是否可以保存到 AI Hub。
5. 匿名模式是否沒有任何 AI Hub 保存入口。
6. 直接使用者是否不需要接觸 Builder 也能順利完成任務。