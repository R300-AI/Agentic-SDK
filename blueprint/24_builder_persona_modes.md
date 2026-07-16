# Builder Information Depth Specification

## 目的

這份文件定義 Builder 對不同建立者應如何控制資訊深度。它不要求前台一定做成兩個明確模式頁，而是定義：

1. 預設資訊應多淺
2. 進階資訊應如何展開
3. 建立者何時需要看到更技術的對應內容

## 核心結論

Builder 應以單一頁面為主，但支援兩層資訊深度：

1. `default depth`: 給大多數建立者
2. `advanced depth`: 給需要更多技術對應資訊的人

也就是說，這更像資訊展開策略，而不一定是兩個顯性切換模式。

## Depth 1: Default Depth

### 適用對象

1. FAE
2. 行政
3. 內部營運
4. 產品助理
5. 需要替第一線建立 Agent 的非工程建立者

### 核心任務

1. 選合理模板
2. 定義輸入方式
3. 選資料策略
4. 選結果型態
5. 檢查交給第一線是否可用

### UI 原則

1. 以任務語言為主，不以 SDK 類名為主
2. 以卡片、選擇器、範例與短說明為主
3. 進階設定折疊
4. 預設先完成配置，再到 Runner 預覽實際效果

### 不應暴露的內容

1. 過多類名
2. 原始技術欄位名
3. 與第一線使用無關的內部細節
4. 看似高級但不影響交付的工程控制

## Depth 2: Advanced Depth

### 適用對象

1. 懂 Agentic SDK 的工程或技術使用者
2. 需要更精準控制 module 行為的人
3. 要確認 source 與配置映射的人

### 核心任務

1. 精準選 module variant
2. 直接檢查 advanced 參數
3. 驗證 round-trip 邊界
4. 對照 `python_source` 與 UI 狀態

### UI 原則

1. 仍維持同一套視覺家族
2. 但可顯示更多技術對應資訊
3. 可顯示 module 標準名與對應類別名
4. 可顯示更完整的 readiness / compatibility 訊息

### 不應變成的樣子

1. 不是 raw config editor
2. 不是 IDE
3. 不是第二個 code page

## 模式切換規則

### 預設值

1. Mode A 匿名：`guided builder`
2. Mode B 手動登入：`guided builder`
3. Mode D 可回編：返回 Builder 時預設沿用上次模式，若無紀錄則 `guided builder`

### 進入 advanced depth 的方式

1. 明確的 `進階設定` 或 `切換為技術模式`
2. 不應在第一屏預設打開

### 返回預設深度的方式

1. 可一鍵返回
2. 不遺失已填設定

## FAE / 建立者最常見反饋

### 反饋 1

`我知道我要做什麼 Agent，但我不想先理解 SDK 家族名詞。`

對應修正：

1. 預設使用 guided builder
2. 所有主標題改為任務語言

### 反饋 2

`我做得出來，但我不知道實際跑起來看起來對不對。`

對應修正：

1. 讓建立者快速進 Runner 預覽
2. 不在 Builder 內額外塞一個正式交付關卡

### 反饋 3

`我需要精準控制，但不想整頁都像工程後台。`

對應修正：

1. 以 expert builder 承接進階資訊
2. 不改變整體產品化外觀

## 與現有 Builder 的關係

現有 [07_page_builder.md](07_page_builder.md) 應視為 Builder 的基礎語義規格；本文件補的是角色分層與資訊層級策略。

## PM 驗收標準

1. 預設 Builder 是否以 guided builder 呈現。
2. FAE 是否能不理解內部類名也完成設定。
3. 技術使用者是否仍能切到 expert builder 查看更細資訊。
4. 建立者是否能在不被技術資訊淹沒的情況下完成設定，並快速進 Runner 預覽。