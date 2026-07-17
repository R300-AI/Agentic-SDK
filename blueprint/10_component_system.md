# Component System Specification

## 目的

這份文件定義 Playground V2 的共用元件系統，避免不同頁面各自長出不一致的 UI 與交互。

本文件中的元件名稱，多數是設計與工程用的內部抽象；它們不等於前台一定會直接顯示同名區塊或術語。

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
11. Task Promise Block
12. Runner Slot Container
13. Input Composer
14. Result Surface
15. Result Adoption State
16. Trust Disclosure Toggle
17. Context Side Panel
18. Artifact Panel
19. Evidence Panel
20. History Panel
21. Action Tray
22. Recommendation Card
23. Reply Draft Card
24. Next Step Strip
25. Chat Message Bubble
26. Attachment Picker
27. Code Preview Drawer
28. Save Status Panel
29. Powered by Agentic SDK Footer

上述名稱是內部元件分類語言，不是頁面上必須原樣出現的使用者語言。

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

內部結構步驟：

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

前台顯示規則：

1. 左欄主標不應直接裸露 `Perceive`、`Retrieve`、`Reflect` 等術語
2. 主標應使用任務語言
3. 內部結構名可作為次標、tooltip 或工程對應資訊
4. 外觀應更接近 setup wizard progress rail，而不是高密度 navigation tree

### Starter Template Picker

用途：幫使用者從合理的 workflow 起手式開始，而不是從空白頁亂配。

至少支援：

1. 最小三模組模板
2. OpenAI client 型模板
3. Custom Action 型模板

它也可以承載更接地的任務 archetype 命名，但這些 archetype 必須最終映射回既有 Workflow / Modules 配置，而不是另存一份獨立正式設定。

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
5. 同一時間應以單一步驟主卡為主，不應在主舞台並列過多設定區塊

### Builder Primary Step Card

用途：承載 Builder 當前步驟的主要設定舞台。

規則：

1. 每次只聚焦一個主要任務
2. 包含大標、短說明、核心選擇與下一步 CTA
3. 外觀應更接近 Windows 設定精靈的大步驟卡，而不是後台設定表單

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

### Runner Shell Header

用途：顯示 Agent 名稱、模式、來源與高階狀態。

規則：

1. 永遠存在
2. 不依賴特定 use case 命名
3. 可承載 agent-level subtitle 或 scene label

### Task Promise Block

用途：在 Runner 首屏回答三個問題：

1. 這頁現在能幫你完成什麼
2. 你要先做什麼
3. 你會得到什麼結果

規則：

1. 若產品決定在首屏明確呈現，則對 direct-use 視角為高優先元件
2. 若未顯性做成獨立區塊，仍應由頁面整體結構隱性回答這三個問題

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

### Runner Slot Container

用途：承載可場景化的 runner 區塊。

規則：

1. 每個 slot 都必須可獨立顯示或隱藏
2. slot 開關由 `runner_scene_profile` 或 capability map 決定
3. slot 命名必須通用，不綁特定產業案例

這些 slot 是內部組裝概念；前台使用者不應感受到自己正在操作 slot-based 系統。

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

同時應遵守：每個 Agent 只應有一個主輸入入口，其餘輸入能力作為輔助層。

### Result Surface

用途：承載 runner 的主要輸出結果。

規則：

1. 可顯示 chat response
2. 可顯示 structured summary card
3. 可顯示 artifact 列表
4. 不假設所有結果都應以聊天泡泡呈現
5. 優先選擇對真實使用者最自然的結果容器，而不是技術上最容易的容器

同時應遵守：每個 Agent 只應有一個主結果容器，其餘結果區塊作為補充層。

### Recommendation Card

用途：承載推薦型 Agent 的主結果。

內容可包含：

1. 主要建議
2. 簡潔理由
3. 可選的下一句說法或下一步

### Reply Draft Card

用途：承載回覆助手型 Agent 的主結果。

內容可包含：

1. 可直接採用的回覆內容
2. 簡短理由或依據入口
3. 可能的下一步操作

### Next Step Strip

用途：在結果主體下方以輕量方式提示下一步。

規則：

1. 不可喧賓奪主
2. 只顯示 1-3 個最合理的後續動作

### Result Adoption State

用途：在需要時，用輕量方式告知第一線目前結果的可採用程度。

至少支援：

1. `可直接使用`
2. `建議人工確認`
3. `先補資料再判斷`

規則：

1. 在任務風險較高的 Agent 中優先考慮
2. 應接近結果主體顯示
3. 不可比結果本身更搶眼
4. 不可只靠顏色表達差異

### Trust Disclosure Toggle

用途：在回應或結果卡下方展開 `查看依據` / `參考來源` / `為什麼這樣建議`。

規則：

1. 預設收合
2. 對不需要的使用者零干擾
3. 展開後顯示理由摘要、來源片段或引用內容

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

它通常應作為 Trust Disclosure Toggle 展開後的內容容器，而不是固定常駐大面板。

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
6. Builder 的主要編輯元件應以單一步驟主卡為中心，而不是三欄平均分散注意力
6. Runner 首屏的 Task Promise Block、結果採用狀態與信任揭露若存在，應保持同一家族語言

## PM 驗收標準

1. 相同功能在不同頁面不出現不同命名或不同互動方式。
2. builder 與 runner 的共用元件外觀一致。
3. AI Hub 唯讀模式隱藏功能後，頁面仍完整而非殘缺。
4. 新 Agent 若要場景化，不需要重畫整頁，只需重組既有 runner slots 與 panels。
5. Builder 中至少存在 Input Contract Designer、Output Contract Panel、Run Readiness Checklist 三類高語義元件。
6. Runner 若採用首屏承諾、結果採用等級與信任揭露，是否仍保持一致產品語言。