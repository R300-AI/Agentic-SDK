# Page Spec: Builder

## 頁面目標

建構頁是手動使用者建立或更新 Workflow 的主頁。它的任務是引導使用者用網頁互動完成 Agentic SDK Python Workflow 的組裝。

這一頁不以圖形接線為主，不顯示獨立程式碼頁，也不承擔聊天互動主責。

這一頁的核心是 guided configuration，不是 graph editing。

更精確地說，Builder 的核心任務不是「排版一條流程」，而是幫使用者做出下列有語義的配置決策：

1. 這個 Agent 接收什麼型態的輸入
2. 這個 Agent 需要如何理解與路由請求
3. 這個 Agent 需要查什麼類型的資料
4. 這個 Agent 要輸出自然語言還是結構化結果
5. 這個 Agent 要如何檢查輸出是否可交付

但這些決策不應以工程後台語言裸露給前台使用者。前端呈現可以比 SDK 名詞更自由，只要不扭曲實際配置含義。

同時，Builder 的每個核心決策都應被視為在定義 Runner 的使用節奏，而不是只在定義 workflow 邏輯。

## 進入條件

可進入建構頁的情境：

1. 手動匿名模式
2. 手動登入模式
3. AI Hub 可回編模式從試跑頁返回建構頁

但從產品角色來看，Builder 的主要使用者應是建立者，例如 FAE、行政、內部營運與可回編人員，而不是第一線直接使用者。

## 頁面結構

### 整體版型

Builder 不應是平均權重的三欄工作台，而應更接近 Windows 初次安裝完成後、一步步帶使用者完成設定的 setup wizard。

桌面版建議結構：

1. 左側輕量 progress rail
2. 中央單一主設定舞台
3. 右側可收合的摘要區或次層 drawer

其中視覺主角永遠是中央的單一步驟卡，不是三欄同時搶焦點。

### 真正的工作模型

Builder 應讓使用者感受到自己在完成一份 Agent 配置，而不是在填零散表單。

因此頁面主流程應依照 Agentic SDK 的實際配置語義展開：

1. 選擇起始模板或空白起手式
2. 定義輸入契約
3. 選擇五個模組家族的 variant
4. 補齊各模組必要參數
5. 確認輸出契約與驗收方式
6. 檢查是否可生成與回朔 Python source

Builder 的責任到這裡為止；建立者是否覺得這份 Agent 真的適合交付，應到 Runner 預覽實際效果後判斷。

### 任務模板優先原則

建立者在 Builder 中，不應先被迫思考抽象版型或內部分類，而應先思考：

1. 這是一個問答型 Agent
2. 這是一個表單評估型 Agent
3. 這是一個推薦型 Agent
4. 這是一個摘要 / 判讀型 Agent

這些任務模板不是獨立保存格式，而是幫助建立者從工作任務切入，再映射到既有 Workflow / Modules 配置。

### Wizard 化原則

Builder 應讓使用者感受到：

1. 我現在只需要完成眼前這一步
2. 系統會告訴我上一題做了什麼、下一題要做什麼
3. 我不需要同時理解整張 Agent 地圖

這意味著 Builder 應優先採用：

1. 單一步驟聚焦
2. 大卡片式設定區
3. 明確的上一題 / 下一題節奏
4. 柔和的進度導覽

而不是：

1. 三欄同時高密度編輯
2. 多區塊同時要求使用者掃讀
3. 一上來就暴露全部設定面

### 前台語言原則

Builder 不要求所有使用者理解 `Perceive`、`Retrieve`、`Reflect` 這些家族名詞。

前台文案應優先使用使用者能理解的任務語言，例如：

1. `Input Design` 可顯示為 `你想讓這個 Agent 看懂什麼？`
2. `Perceive` 可顯示為 `理解使用者輸入`
3. `Retrieve` 可顯示為 `補充參考資料`
4. `Action` 可顯示為 `決定最後怎麼回答`
5. `Reflect` 可顯示為 `回答前再檢查一次`

技術名詞可以保留在次層說明、advanced 區或 tooltip，不應主導整頁閱讀體驗。

### 不採用的互動模型

V2 Builder 明確不採用下列模式作為主互動：

1. 自由拖曳節點
2. 自由接線 graph canvas
3. 以線條拓樸作為主要設定入口
4. 只為了看起來像 AI workflow builder 而存在的拖放效果

原因是目前 Agentic SDK 文件定義的 workflow，重點在五個模組家族的有序組裝與參數設定，而不是自由圖形拓樸設計。

同樣地，下列只有「看起來專業」但沒有配置意義的元素，也不應存在：

1. 裝飾性 pipeline 圖
2. 沒有對應 runtime 行為的進度儀表
3. 與實際 module 選擇無關的 AI 分析動畫
4. 不能改變 `python_source` 的虛假切換器

### 頂部 Context Bar

必須固定顯示當前模式：

1. 匿名建立模式
2. 已登入，可保存到 AI Hub
3. AI Hub 既有 Workflow 更新模式

若為第 3 種，頂部必須顯示：

1. Agent 名稱
2. 這是從 AI Hub 載入的既有 Workflow
3. 最後一次保存時間（若可取得）

## 外觀語氣

Builder 雖然是工作台，但不應像工程控制台。

它的視覺應更接近：

1. 一個 Windows OOBE 風格的引導式設定精靈
2. 一個有步驟感、低壓力的設定工作室
3. 一個能讓非工程建立者願意一路完成的精緻產品頁

這裡的「非工程使用者」主要是建立者角色，不等於所有第一線直接使用者都應進 Builder。

### 應有的畫面感

1. 左欄像 Windows 設定精靈的進度導覽，而不是系統 navigation tree
2. 中央像單一大步驟卡，一次只讓使用者專注一個設定主題
3. 右側摘要若存在，應像輔助說明板，而不是第三個主編輯區
4. 每一步都有大標題、簡短副標與清楚 CTA，不讓使用者先撞到技術詞
5. 整體節奏像被系統帶著走，而不是自己摸索一堆設定抽屜

### 不應有的畫面感

1. 不像 workflow IDE
2. 不像資料庫後台
3. 不像 deployment console
4. 不像需要先懂 SDK 類名才能操作的管理介面
5. 不像高密度 BI dashboard

## 左欄規格

### 內容

1. Builder 任務清單
2. 當前步驟與整體進度
3. 配置步驟導航
4. 目前完成度

左欄應更像 progress rail，不是操作面板；它的作用是降低迷失感，而不是提供大量資訊。

### 建議步驟結構

下列是 Builder 的內部結構順序，用來描述配置流程骨架；它不等於前台必須原樣顯示的標題：

1. `Workflow Name`
2. `Starter Template`
3. `Input Design`
4. `Perceive`
5. `Plan`
6. `Retrieve`
7. `Action`
8. `Reflect`
9. `Run Readiness`

其中五個模組家族仍然保留，但前後增加真正重要的配置上下文。

### WORKFLOW / 設計決策流程：九步完整配置映射

Builder 的九步不是單純頁面導覽，而是 `Workflow`、五個模組家族與 runtime 初始參數的決策流程。主畫面仍使用自然語言提問；每一步背後都必須能落到 `python_source` 中的明確配置。若某個前台選項不能改變 `python_source`、Runner profile 或可執行性判斷，就不應出現在主流程。

每一步採兩層設計：

1. 主流程只問建立者能理解的必要決策。
2. 進階區只在該步驟有實際模組參數時出現，並且必須直接對應 SDK 參數。

#### 1. Workflow Name

前台問題：`這個 Agent 要如何命名？`

主要配置：

| 使用者輸入 | Python source 對應 | 初始值 |
| --- | --- | --- |
| Agent 名稱 | `Workflow(workflow_name=...)` | `Customer Helper` |

規則：

1. 名稱是 workflow 的持久識別，不是畫面暱稱。
2. Builder 可顯示產品化中文名稱，但 source 必須保留可回朔的 `workflow_name`。
3. 名稱清理只處理空白與長度，不應替使用者改寫語意。

#### 2. Starter Template

前台問題：`這個任務屬於哪一種類型？`

主要配置：任務模板決定初始 module preset，但不是獨立保存格式。

| 前台選項 | Workflow preset | 初始模組與參數 |
| --- | --- | --- |
| 基本回覆 | 最小三模組 | `PassThroughPerceive()`、`KeywordRetrieve(items=[])`、`DirectAnswerAction()` |
| 模型回覆 | LLM 回覆 | `PassThroughPerceive()`、`KeywordRetrieve(items=[])`、`GenerativeAction(api_key=..., base_url=..., model=...)` |
| 自訂處理 | Custom Action 出口 | `PassThroughPerceive()`、`KeywordRetrieve(items=[])`、`SummaryAction()` 範例出口 |
| 問答引導 | 問答型 preset | `TextPerceive(...)`、`NextStepPlan(...)`、`KeywordRetrieve(...)`、`GenerativeAction(...)` |
| 建議卡 | 推薦型 preset | `TextPerceive(...)`、`NextStepPlan(...)`、`HybridRetrieve(...)` 或 `SemanticRetrieve(...)`、`StructuredAction(...)` |
| 摘要審閱 | 摘要/判讀 preset | `TextPerceive(...)` 或 `StructuredPerceive(...)`、`SemanticRetrieve(...)`、`GenerativeAction(...)`、可選 `ResponseCheckReflect(...)` |

規則：

1. Template 只設定合理起點，後續每一步都可覆寫對應模組。
2. 需要 LLM client 的 preset 必須標記為「需要模型連線」，Runner 不可假裝離線可完整執行。
3. `Advisor`、`Recommendation`、`Review` 不可只改 profile hint；必須映射到 module preset。

#### 3. Input Design

前台問題：`這個 Agent 需要理解什麼資料？`

主要配置：決定 Runner 主要輸入節奏，也決定 Perceive 預設 variant。

| 前台選項 | Perceive 預設 | Runner profile | 初始參數 |
| --- | --- | --- | --- |
| 文字訊息 | `PassThroughPerceive()` 或 `TextPerceive(...)` | chat first | 無欄位 schema；可選語意整理 |
| 檔案或長文字 | `TextPerceive(...)` | result first 或 review first | `welcome_message`、`options=[]`；附件解析未完成時必須標記 Partial |
| 固定欄位 | `StructuredPerceive(...)` | form first | `options=[]`、欄位 schema / field hints |
| 文字與圖片 | `TextImagePerceive(...)` | multimodal first | 圖片 mime 限制與 vision query 設定 |

規則：

1. 這一步不能只改 Runner layout；必須同步影響 Perceive variant。
2. 若實作尚未支援圖片或文件解析，UI 必須顯示為不可用或 Partial，而不是生成假設定。

#### 4. Perceive

前台問題：`要如何讀取使用者需求？`

主要配置：選擇 Perceive 模組與必要初始參數。

| 前台選項 | 模組 | 初始參數 |
| --- | --- | --- |
| 直接讀取文字訊息 | `PassThroughPerceive()` | 無 |
| 先整理需求重點 | `TextPerceive(...)` | `welcome_message`、`options=[]`、`importance=1.0`、`model` 可進階設定 |
| 依欄位理解需求 | `StructuredPerceive(...)` | 同 `TextPerceive`，並承接 Input Design 的欄位設定 |
| 同時參考文字與圖片 | `TextImagePerceive(...)` | 同 `TextPerceive`，並承接圖片限制 |

進階參數：

| 參數 | 所屬模組 | 顯示時機 |
| --- | --- | --- |
| `welcome_message` | `TextPerceive` family | 選擇語意/欄位/圖文理解時 |
| `options` | `TextPerceive` family | 需要提供可選意圖或服務範圍時 |
| `importance` | `TextPerceive` family | 需要寫入記憶權重時 |
| `model` | `TextPerceive` family | 進階模型設定 |

#### 5. Plan

前台問題：`是否需要決策路徑？`

主要配置：是否加入 Plan 模組。

| 前台選項 | 模組 | 初始參數 |
| --- | --- | --- |
| 不需要，直接產生回覆 | 無 `plan` | Workflow 由 Perceive 直接進 Retrieve / Action |
| 需要，先判斷是否查詢支援資料 | `NextStepPlan(...)` | `retrieve_name="支援資料"`、`retrieve_description` 由 Retrieve 設定推導 |

進階參數：

| 參數 | 初始值 | 說明 |
| --- | --- | --- |
| `system_prompt` | 由 SDK 預設產生 | 只有建立者明確需要改決策規則時才展開 |
| `model` | settings default | 需要模型連線 |

#### 6. Retrieve

前台問題：`可以使用哪些支援資料？`

主要配置：選擇 Retrieve 模組與資料來源。

| 前台選項 | 模組 | 初始參數 |
| --- | --- | --- |
| 暫不加入支援資料 | `KeywordRetrieve(items=[])` | 空 items，表示不注入假知識 |
| 用關鍵字對應內容 | `KeywordRetrieve(...)` | `items=[{"keywords": [...], "content": ...}]` |
| 從知識庫語意查找 | `SemanticRetrieve(...)` | `top_k=3`、`similarity_weight=0.5`、`recency_weight=0.3`、`importance_weight=0.2`、`knowledge_base` 可選 |
| 混合查找 | `HybridRetrieve(...)` | 同 `SemanticRetrieve`，可加關鍵字/欄位條件 |

進階參數：

| 參數 | 所屬模組 | 初始值 |
| --- | --- | --- |
| `items` | `KeywordRetrieve` | `[]` |
| `top_k` | `SemanticRetrieve` / `HybridRetrieve` | `3` |
| `similarity_weight` | `SemanticRetrieve` / `HybridRetrieve` | `0.5` |
| `recency_weight` | `SemanticRetrieve` / `HybridRetrieve` | `0.3` |
| `importance_weight` | `SemanticRetrieve` / `HybridRetrieve` | `0.2` |
| `knowledge_base` / `knowledge_base_ref` | `SemanticRetrieve` / `HybridRetrieve` | 未選擇時不注入 |
| `vision_query` | `SemanticRetrieve` / `HybridRetrieve` | 只有圖文輸入時可用 |

#### 7. Action

前台問題：`最後的回覆應該長什麼樣子？`

主要配置：選擇 Action 模組與輸出契約。

| 前台選項 | 模組 | 初始參數 |
| --- | --- | --- |
| 直接回覆取回內容 | `DirectAnswerAction()` | 無 |
| 由模型整理自然語言 | `GenerativeAction(...)` | `api_key`、`base_url`、`model`、可選 `system_prompt` |
| 產生結構化結果 | `StructuredAction(...)` | `api_key`、`base_url`、`model`、可選 `system_prompt` |
| 自訂處理 | 自訂 Action class | 由模板或進階設定提供 class skeleton |

進階參數：

| 參數 | 所屬模組 | 初始值 |
| --- | --- | --- |
| `system_prompt` | `GenerativeAction` / `StructuredAction` | SDK 預設；使用者填寫時覆寫 |
| `model` | `GenerativeAction` / `StructuredAction` | settings default |
| `temperature` | `GenerativeAction` / `StructuredAction` | `None` |

#### 8. Reflect

前台問題：`是否需要先檢查答案？`

主要配置：是否加入 Reflect 模組與失敗路徑。

| 前台選項 | 模組 | 初始參數 |
| --- | --- | --- |
| 不先檢查 | 無 `reflect` | 無 |
| 檢查回覆是否回答問題 | `ResponseCheckReflect(...)` | `on_failure="retry_plan"` 或 `"end"` |
| 檢查是否有可交付證據 | `EvidenceCheckReflect(...)` | `on_failure="retry_plan"` 或 `"end"` |

規則：

1. `ResponseCheckReflect` 需要模型連線。
2. `EvidenceCheckReflect` 不需要 LLM，適合離線 fallback。
3. 若選 `retry_plan`，Builder 必須檢查 Plan 是否存在；沒有 Plan 時要提示或改成 `end`。

#### 9. Run Readiness

前台問題：`現在可以試跑了嗎？`

主要配置：檢查 source 是否完整、是否需要模型連線，以及 runtime gates。

| 配置面 | Python source 對應 | 初始值 |
| --- | --- | --- |
| 入口模組 | `Workflow(entry_module=...)` | `"perceive"` |
| 最大節點跳數 | `Gates(max_node_hops=...)` | `50` |
| 單模組重訪上限 | `Gates(max_revisit=...)` | `5` |
| 逾時秒數 | `Gates(timeout_sec=...)` | `300.0` |

規則：

1. Runtime / credential / store 類設定不可混在每一步主問題裡。
2. 這些設定可放在 Run Readiness 的進階區，或由環境提供預設。
3. Builder 必須誠實標示需要模型連線、AI Hub 權限或尚未支援的執行能力。

#### 跨步驟一致性規則

1. `Input Design` 選固定欄位時，Perceive 預設應切到 `StructuredPerceive`，Runner profile 應切到 form first。
2. `Input Design` 選圖文時，Perceive 預設應切到 `TextImagePerceive`；若 `vision_query` 尚未可執行，標記 Partial。
3. `Retrieve` 選語意或混合查找時，Runner 與 readiness 必須標記是否已提供 KB / memory store。
4. `Action` 選模型或結構化輸出時，必須建立 OpenAI-compatible client 設定，且 readiness 顯示需要模型連線。
5. `Reflect` 選 `retry_plan` 時，若沒有 Plan，Builder 必須阻止或自動加入 `NextStepPlan`。
6. 任何主流程選項都不得只改前端畫面；至少要改變 `python_source`、Runner profile 或 readiness 判斷之一。

### 前台顯示名原則

建立者在頁面上看到的，應優先是任務語言，不是這些內部結構名。

換句話說：

1. 內部結構名用於文件、工程對應、tooltip 與次層說明
2. 前台主標題只應使用使用者語言
3. 若使用者不理解 `Perceive` / `Retrieve` / `Reflect`，不應影響完成設定

### 步驟標題的前台呈現

左欄可採雙層文案：

1. 主標使用使用者語言
2. 次標或 tooltip 才顯示對應技術名詞

例如：

1. `你想讓這個 Agent 看懂什麼？` / `Input Design`
2. `理解使用者輸入` / `Perceive`
3. `補充參考資料` / `Retrieve`
4. `決定最後怎麼回答` / `Action`
5. `回答前再檢查一次` / `Reflect`

`Workflow Name`、`Starter Template`、`Input Design`、`Run Readiness` 也應採相同原則，例如：

1. `這個 Agent 叫什麼名字？` / `Workflow Name`
2. `你想從哪種範本開始？` / `Starter Template`
3. `你想讓這個 Agent 看懂什麼？` / `Input Design`
4. `現在可以開始試跑了嗎？` / `Run Readiness`

### 行為

1. 點選模組步驟切換中欄表單
2. 未滿足最低可執行條件時，試跑 CTA disabled
3. 左欄步驟的視覺作用是表示 workflow family 順序，不是表示可任意重排的節點圖
4. 每個步驟都要能顯示「尚未定義 / 已完成 / 需補參數 / 與其他步驟衝突」

但預設互動應仍以「下一步 / 上一步」為主，而不是要求使用者頻繁跳欄。

## 中欄規格

### 內容定位

中欄專注在「目前選中模組」的初始化參數設定。

但它不應只是裸表單區，而應依使用者正在做的配置決策，切成具意義的工作段落。

它也不應像長頁設定面板，而應更像單一步驟舞台：

1. 頂部是這一步要完成什麼
2. 中段是主要選擇
3. 底部是下一步 CTA 與必要提示

### 中欄的主要設計原則

每個步驟畫面都應回答這個問題：

「這一步在這個 Agent 裡的責任是什麼？使用者現在需要做哪個決策？」

如果某個區塊無法回答這兩句，就代表它只是裝飾或資訊噪音。

同時，每個區塊都應具備「產品卡片感」：

1. 清楚標題
2. 一句簡短用途說明
3. 1-2 個核心選擇
4. 必要時才展開進階設定

不要讓中欄看起來像長篇設定文件被直接貼到網頁上。

更具體地說，每一步最好是一張主卡，最多再加一張次卡；避免同一步內出現四五個並列設定區。

### 建議工作段落

#### 1. Starter Template

用途：讓使用者先從「最小三模組」、「OpenAI client 型」、「Custom Action 型」等合理起點開始，而不是空白頁亂配。

使用者決策：

1. 我要從什麼骨架開始
2. 我是否需要模型能力
3. 我是否要保留自訂 Action 出口

前台可以用更產品化的模板名稱，例如：

1. `快速問答型`
2. `知識查找型`
3. `自訂邏輯型`

若要更接地，也可以讓模板首先以任務 archetype 呈現，例如：

1. `顧問問答型`
2. `表單評估型`
3. `推薦回覆型`
4. `摘要判讀型`

技術對應關係可放在卡片次說明裡，而非主標題。

#### 2. Input Design

用途：先定義這個 Agent 接受哪些輸入訊號，再往下決定 Perceive 變體。

使用者決策：

1. 純文字輸入
2. 文字 + 結構化欄位
3. 文字 + 圖片
4. 純結構化欄位

這一步對應到 Perceive 家族的真正選擇依據，而不是先背模組名。

視覺上，這一步應更像輸入方式選擇器，不像 schema editor。每個選項可用小圖示、範例句與簡短說明呈現。

這一步也會直接影響 Runner 是先讓人聊天、先填欄位，還是先看到結果。

對 MVP 而言，這一步應明確收斂出一個主輸入方式，而不是同時讓聊天、欄位、附件都成為同等主角。

#### 3. Perceive

用途：根據輸入型態決定用哪種感知模組。

Builder 應明白呈現四種標準路徑：

1. `PassThroughPerceive`: 直接吃文字
2. `TextPerceive`: 文字語意整理
3. `StructuredPerceive`: 欄位導向整理
4. `TextImagePerceive`: 圖文整理

使用者真正決策的是：

1. 我需不需要語意整理
2. 我的輸入是欄位主導還是文字主導
3. 我是否需要圖片一起參與理解

前台主文案應偏向：

1. `先幫我整理問題重點`
2. `依表單欄位理解需求`
3. `同時參考文字與圖片`

#### 4. Plan

用途：決定這個 Agent 是否需要先查資料再回答。

因目前標準模組主要是 `NextStepPlan`，所以 Builder 不該假裝這裡有很多花俏選項；真正要設計的是理解與說明：

1. 這個 Agent 會根據上下文決定直接回答或先檢索
2. 目前 workflow 是否需要 `Retrieve` 這條路

如果目前版本沒有真正多 variant，就應設計成輕量決策說明區，而不是做成假選單。

視覺上，這裡可以像一張「工作方式說明卡」，讓使用者知道系統會先判斷要不要補資料，而不是被迫在這步驟裡操作不存在的複雜控制。

#### 5. Retrieve

用途：定義資料補回策略。

Builder 應將選擇語義化成：

1. 關鍵字條目查找
2. 語意檢索
3. 混合檢索

使用者要理解的是：

1. 我有明確 keyword item list 嗎
2. 我需要語意相似度嗎
3. 我同時需要欄位條件與語意補證據嗎

這比單純展示 `KeywordRetrieve` / `SemanticRetrieve` / `HybridRetrieve` 類名更有意義。

這一步應像資料策略選擇器，而不是知識庫後台。可用「精準比對」、「語意尋找」、「混合判斷」這類較人話的主標。

這一步同時影響 Runner 是否能在回應下方提供可展開的依據與來源。

#### 6. Action

用途：定義最終交付型態。

這一步是 Builder 裡最重要的語義決策之一，因為它直接影響 Runner 如何呈現結果。

Builder 應把選擇表達成：

1. 直接回答
2. 生成式回答
3. 結構化輸出

使用者真正決策的是：

1. 我要單純回一段話
2. 我要用模型綜合前文生成
3. 我要產出可被 UI / 其他系統消費的結構化結果

這一步視覺上應最接近「你希望這個 Agent 最後交出什麼」，因為它直接對應實際使用者會看到的結果型態。

它也是決定 Runner 更像 chat-first、form-first 還是 result-first 的關鍵來源之一。

同樣地，這一步應明確收斂出一個主結果容器，而不是讓文字、卡片、摘要、表格全部同權重並列。

#### 7. Reflect

用途：定義交付前的檢查方式。

Builder 應讓使用者理解：

1. 我要檢查回應本身是否完整
2. 我要檢查證據是否足夠

而不是把 Reflect 做成看起來很高級、實際很難懂的最後一格。

前台可用文案例如：

1. `先確認回答有沒有答到重點`
2. `先確認理由和依據夠不夠`

#### 8. Run Readiness

用途：在進 Runner 前做語義化檢查，而不是只做表單必填檢查。

這裡應顯示：

1. 是否已有合法輸入契約
2. 是否已決定輸出型態
3. 是否缺少模型 client 相關設定前提
4. 是否可生成 Python source
5. 是否屬於可完整回朔子集

接下來建立者應直接進入 Runner 預覽實際效果，而不是在 Builder 裡再多一個正式交付關卡。

這一步應像發佈前檢查卡，而不是 lint console。畫面上要讓人感受到「差幾步就能試跑」，而不是「你有三個技術錯誤」。

### 表單原則

1. 顯示給使用者的是模組概念與用途，不先暴露內部 type string
2. 表單欄位優先對應 README 級別可理解參數
3. 若有進階設定，折疊在 advanced 區
4. 所有互動都應對應實際可回推的 Python source 結構，不加入只有展示效果的控制項
5. 若某一步目前只有單一標準做法，就不應強行做成複雜 selector，而應明確解釋其責任與前後依賴

### 最低支援模式

V2 第一版至少支援：

1. 最小三模組 Workflow
2. OpenAI client 注入型 Workflow
3. 自訂 Action 類別型 Workflow

## 右欄規格

### 內容

1. 即時 Workflow 摘要
2. 當前配置決策摘要
3. 關鍵初始化參數摘要
4. 輸入契約摘要
5. 輸出契約摘要
6. 是否可試跑
7. 是否可保存
8. 是否可完整回朔

### 右欄的真正角色

右欄不是第二份表單，也不是純展示欄。

它的角色是幫使用者隨時回答：

1. 我現在到底配置了一個什麼樣的 Agent
2. 這個 Agent 接收什麼、輸出什麼
3. 它目前還缺哪個決策才能試跑

在 Windows 設定精靈式的 Builder 裡，這個區域應視為輔助摘要區；若空間不足，應優先改為可收合 drawer，而不是硬保留三欄並列。

### 不應出現的內容

1. 完整 Python source code
2. 聊天試跑主介面
3. 保存到 AI Hub 主操作按鈕
4. 與目前配置無關的裝飾性分析視覺

## Builder 到 Runner 的轉換

### CTA 文案

建議使用：

1. `進入試跑`
2. `先試跑這份 Workflow`

### 轉換條件

至少滿足：

1. `workflow name` 合法
2. 最低必要模組存在
3. 目前 Python source 可生成
4. 已決定輸入契約與輸出契約

### 轉換前的有意義檢查

按下 CTA 前，Builder 應先做語義檢查，而不只是表單檢查。例如：

1. 若選了 `TextImagePerceive` 但沒有任何圖片輸入設計，應提示輸入契約不一致
2. 若選了 `StructuredAction` 但沒有任何輸出欄位結構說明，應提示輸出契約不完整
3. 若選了依賴模型的模組，但整份 workflow 沒有對應 client 注入前提，應標示為 run-blocking risk

## 視覺方向

1. 比入口頁更像設定精靈，但仍須避免工程後台感過重
2. 左欄步驟應有清楚完成/當前狀態
3. 中央步驟卡應有大標、短說明、明確下一步
4. 右欄摘要需穩定但低調，不可與主步驟爭奪焦點
5. 不用 graph 線框、節點拖曳陰影、連線動畫來暗示不存在的控制自由度
6. 每一個主要區塊都應對應明確的配置任務，而不是抽象的 AI 工作流意象
7. 每個主要區塊應更像 setup card / wizard step，而不是 admin form slab

### 建議美術細節

1. 左欄採較柔和的分段 progress rail，像 Windows 設定精靈的完成節奏
2. 中央每一步以單一大卡片為主，卡片內標題與說明清楚
3. 重要選擇題用大面積選項卡，不用全部都做成下拉選單
4. 少量 pictogram 可用於 Input Design、Output Design，但不能變成行銷插畫頁
5. 狀態 icon 應友善清楚，不像監控告警系統
6. 下一步按鈕應穩定出現在使用者視線終點，像安裝精靈的主要前進按鈕

## 與 Workflow / Modules 設計的一致性

Builder UI 必須服從 Agentic SDK 目前文件定義的組裝模型。

對使用者真正有意義的編輯單位是：

1. 輸入契約
2. 模組家族的選擇
3. 每個家族內的 module variant
4. module 初始化參數
5. 輸出契約
6. 可否生成 Python source
7. 可否由 Python source 回朔

若某個視覺效果不能提升以上七件事之一，則視為非必要效果。

### 第一版應保留的高價值互動

1. starter template chooser
2. input design selector
3. variant chooser
4. inline validation
5. advanced settings disclosure
6. input/output contract summary
7. run readiness checklist
8. 直接進 Runner 預覽

### 第一版應移除的低價值互動

1. 拖曳排序
2. 節點連線
3. 模擬資料流動畫
4. 裝飾性的 workflow graph 縮圖
5. 不能改變實際配置結果的 fake insight widgets
6. 沒有對應 module 決策的 progress gamification

## 狀態規格

### 空白建立

手動匿名或登入第一次進入時，預設載入最小可理解範例或清楚的 starter template。

### 已載入既有 Workflow

若為 AI Hub 可回編模式或登入後已有最近保存內容，建構頁必須清楚標示來源，而不是像新建狀態。

### 回朔失敗

若 Python source 超出 builder 可支援的回朔子集：

1. 顯示限制提示
2. 只允許保留為唯讀摘要，或要求回到試跑頁僅做試跑/保存

## 響應式規則

### Desktop

完整三欄。

### Tablet

左欄可收折，右欄可切 drawer。

### Mobile

Builder 第一版不建議完整支援手機深度編輯；若要顯示，應降級成單欄 step-by-step wizard。

## PM 驗收標準

1. 手動進站一律先進建構頁。
2. AI Hub 唯讀模式不能進建構頁。
3. AI Hub 可回編模式能從試跑頁返回建構頁。
4. 建構頁不出現獨立程式碼主頁。
5. 使用者能清楚知道自己是在新建還是在更新既有 Workflow。
6. 建構頁的主要互動都對應實際 workflow/module 組裝語義，而不是裝飾性的 graph 操作。
7. 使用者在不理解內部類名的情況下，也能完成輸入、檢索、輸出、驗收這四類關鍵決策。
8. 建立者可直接從 Builder 進入 Runner 預覽這份 Agent 的實際使用效果。