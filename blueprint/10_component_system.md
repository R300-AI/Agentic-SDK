# Component System Specification

## 目的

這份文件定義 Playground V2 的共用元件系統，避免不同頁面各自長出不一致的 UI 與交互。

## 元件分層

### Foundation Components

1. Button
2. Input
3. Password Input
4. Select
5. Textarea
6. Card
7. Badge
8. Divider
9. Toast
10. Inline Status

### Product Components

1. Entry Choice Card
2. Context Bar
3. Workflow Step Rail
4. Starter Template Picker
5. Input Contract Designer
6. Module Config Section
7. Output Contract Panel
8. Run Readiness Checklist
9. Workflow Summary Panel
10. Runner Shell Header
11. Runner Slot Container
12. Input Composer
13. Result Surface
14. Context Side Panel
15. Artifact Panel
16. Evidence Panel
17. History Panel
18. Action Tray
19. Chat Message Bubble
20. Attachment Picker
21. Code Preview Drawer
22. Save Status Panel
23. Powered by Agentic SDK Footer

## 元件規格

### Entry Choice Card

用途：入口頁的登入/匿名選擇。

狀態：

1. default
2. hover
3. active
4. disabled
5. loading

規則：

1. 整張卡可點擊
2. 必須有主標題、說明文與主 CTA
3. 不可把錯誤訊息做成瀏覽器原生 alert

### Context Bar

用途：在建構頁與試跑頁顯示當前模式與來源。

至少顯示：

1. 當前模式
2. 是否已登入
3. 是否來自 AI Hub
4. 是否為既有 Workflow 更新

### Workflow Step Rail

用途：建構頁左欄的步驟導航。

步驟：

1. Workflow Name
2. Perceive
3. Plan
4. Retrieve
5. Action
6. Reflect

狀態：

1. pending
2. current
3. complete
4. blocked

它不只列模組名，也可列配置工作，如 Input Design、Run Readiness。

### Starter Template Picker

用途：幫使用者從合理的 workflow 起手式開始，而不是從空白頁亂配。

至少支援：

1. 最小三模組模板
2. OpenAI client 型模板
3. Custom Action 型模板

### Input Contract Designer

用途：定義這個 Agent 接收哪種輸入。

至少支援：

1. text only
2. text + fields
3. text + images
4. fields first

規則：

1. 這是 Builder 的高優先元件，不可被埋進 advanced 區
2. 後續 Perceive 選項要依這裡的決策收斂

### Module Config Section

用途：建構頁中欄顯示目前模組的設定表單。

規則：

1. 模組說明在上，表單欄位在下
2. 進階欄位折疊在 advanced 區
3. 欄位錯誤需內聯顯示
4. 若當前模組只有單一推薦路徑，應以說明 + 必要欄位為主，而不是假裝有很多選項

### Output Contract Panel

用途：定義 Action 產出的交付形態。

至少支援：

1. direct answer
2. generative answer
3. structured result

規則：

1. 必須清楚說明這個決策會影響 Runner 如何呈現結果
2. structured result 應能補充欄位結構摘要

### Run Readiness Checklist

用途：在進 Runner 前做語義化檢查。

至少檢查：

1. 是否存在合法輸入契約
2. 是否存在合法輸出契約
3. 是否可生成 Python source
4. 是否屬可回朔子集
5. 是否有 run-blocking risk

### Workflow Summary Panel

用途：建構頁右欄顯示即時摘要。

內容：

1. Workflow 名稱
2. 輸入契約摘要
3. 目前模組選擇
4. 輸出契約摘要
5. 關鍵參數摘要
6. 試跑條件是否已滿足

### Chat Message Bubble

用途：試跑頁顯示使用者與 assistant 訊息。

差異：

1. user bubble
2. assistant bubble
3. system/error bubble

### Runner Shell Header

用途：顯示 Agent 名稱、模式、來源與高階狀態。

規則：

1. 永遠存在
2. 不依賴特定 use case 命名
3. 可承載 agent-level subtitle 或 scene label

### Runner Slot Container

用途：承載可場景化的 runner 區塊。

規則：

1. 每個 slot 都必須可獨立顯示或隱藏
2. slot 開關由 `runner_scene_profile` 或 capability map 決定
3. slot 命名必須通用，不綁特定產業案例

建議 slot 類型：

1. `primary_input`
2. `conversation`
3. `result_summary`
4. `artifacts`
5. `evidence`
6. `history`
7. `actions`
8. `metadata`

### Input Composer

用途：統一承載對話輸入、結構化輸入、附件輸入的容器。

規則：

1. 可退化成純聊天輸入
2. 可擴充成表單 + 附件 + prompt 混合輸入
3. 不為單一 use case 寫死欄位
4. 前台呈現應像任務輸入區，而不是開發者 prompt 面板

### Result Surface

用途：承載 runner 的主要輸出結果。

規則：

1. 可顯示 chat response
2. 可顯示 structured summary card
3. 可顯示 artifact 列表
4. 不假設所有結果都應以聊天泡泡呈現
5. 優先選擇對真實使用者最自然的結果容器，而不是技術上最容易的容器

### Context Side Panel

用途：取代純 sidebar 心智，作為通用上下文與操作面板。

內容可包含：

1. workflow identity
2. source status
3. runner actions
4. save status
5. code preview entry

### Artifact Panel

用途：顯示 agent 產出的可瀏覽物件，例如表格、摘要卡、輸出片段、檔案。

### Evidence Panel

用途：顯示 retrieval / reasoning / source-backed evidence。

前台可轉譯為：

1. 參考依據
2. 建議原因
3. 你可以查看的來源

### History Panel

用途：顯示同一 agent 在多輪或多次執行中的對照資訊。

### Action Tray

用途：顯示 agent-specific 但仍屬通用產品語言的快捷操作。

規則：

1. 只能承載以 capability 啟用的操作
2. 不能破壞模式權限規則
3. 不得把 builder 操作混進 runner 主互動區
4. 前台命名應優先用任務語言，而不是 capability / runtime 語言

### Attachment Picker

用途：試跑頁上傳圖片或檔案。

規則：

1. 已選附件需有縮圖或檔名預覽
2. 上傳進行中要有進度或 loading 狀態
3. 可刪除待送出附件

### Code Preview Drawer

用途：試跑頁輔助查看 Python source。

規則：

1. 預設收合
2. 可複製
3. 可匯出 `.py`
4. AI Hub 唯讀模式不可見

### Save Status Panel

用途：試跑頁呈現保存到 AI Hub 的狀態。

狀態：

1. not_saved
2. saving
3. saved
4. failed

### Powered by Agentic SDK Footer

用途：所有試跑頁模式都必須露出產品來源。

AI Hub 唯讀體驗模式下，它應比 builder 模式更明顯，但不能搶主體互動。

## 元件一致性原則

1. 同一類錯誤提示樣式一致
2. 所有 destructive / save / primary CTA 的視覺層級固定
3. AI Hub 唯讀模式不因隱藏功能而破壞版面平衡
4. 場景化 runner 的差異應來自 slot 組合，不是另做一套新頁面設計
5. Builder 的主要元件必須對應實際配置決策，而不是抽象的流程裝飾

## PM 驗收標準

1. 相同功能在不同頁面不出現不同命名或不同互動方式。
2. builder 與 runner 的共用元件外觀一致。
3. AI Hub 唯讀模式隱藏功能後，頁面仍完整而非殘缺。
4. 新 Agent 若要場景化，不需要重畫整頁，只需重組既有 runner slots 與 panels。
5. Builder 中至少存在 Input Contract Designer、Output Contract Panel、Run Readiness Checklist 三類高語義元件。