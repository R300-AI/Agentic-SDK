# Page Spec: Runner

## 頁面目標

試跑頁是 Playground V2 的互動中心。所有主要流程最終都會進入試跑頁：

1. 手動匿名建立完成後
2. 手動登入建立完成後
3. AI Hub 導流既有 Workflow

這一頁同時承擔：

1. Workflow 互動驗證
2. Python code preview 的輔助展示
3. 保存到 AI Hub 的主操作入口
4. 返回建構頁更新配置

本頁在產品定位上，首先是一個 generic agent runtime shell；但它不能只是一張固定聊天頁。它必須支援 agent-agnostic 的場景化組裝，讓不同 Agent 都能在同一產品語言下呈現不同程度的 sceneable runtime。

同時，這個 shell 不應先讓人感受到「runtime」或「workflow 測試台」，而應先讓真實使用者感受到：

1. 這是一個可以直接使用的 Agent 頁面
2. 我知道現在可以做什麼
3. 我看得懂結果，不需要理解內部模組

## 子模式

試跑頁必須支援四種顯示模式：

1. 匿名試跑模式
2. 手動登入完整模式
3. AI Hub 導流唯讀體驗模式
4. AI Hub 導流可回編模式

Runner 只有一個頁面；系統可依角色自動調整資訊密度，讓建立者看到較完整的預覽資訊，直接使用者看到較精簡的任務頁。

## Layout

### 整體結構

1. 中央主區：聊天互動、附件、執行結果
2. 右側側欄：Workflow 資訊、狀態、操作
3. 浮動小視窗：程式碼 preview

## 產品分層

### Layer A: Generic Runner Shell

這一層是所有 Agent 共用的最小通用殼層，負責：

1. 啟動 workflow 試跑
2. 顯示對話或執行結果
3. 顯示 workflow 身分與來源狀態
4. 保存、回編、匯出、看 code preview

但對前台使用者而言，這一層應更像產品外殼，而不是 runtime console。

### Layer B: Agent Scene Surface

當不同 Agent 需要不同互動面貌時，應在 generic shell 之上增加 sceneable runtime surface，而不是要求單一聊天頁承接所有業務互動。

這些場景化 UI 可能包含：

1. 結構化輸入表單
2. domain-specific summary cards
3. evidence / trace panels
4. 歷史記錄與比較視圖
5. 角色專用操作區

這些區塊的目的不是讓畫面更完整，而是讓不同角色都能用更自然的方式與 Agent 互動，例如銷售員、顧客、操作員、內部審查者。

### 重要限制

這一層的設計目標不是替既有案例做特規，而是讓任何 Agent 都可以透過 capability 與 slot 組合，得到一定程度的場景化呈現。

## 核心設計模型

Runner 應從「固定聊天頁」改為「固定外殼 + 可變 slot 組合」。

但前台視覺上，不應讓使用者意識到自己正在看 slot-based 系統。呈現效果應該像一個自然完整的產品頁。

`chat_first`、`form_first`、`result_first` 等分類，是平台與設計內部用來推定版型的語言，不應直接作為前台頁面的模式名稱暴露給使用者。

### 固定外殼

永遠存在的部分：

1. shell header
2. mode / source context
3. primary interaction frame
4. context side panel
5. code preview entry
6. save / export / back-to-builder actions

### 前台閱讀順序

Runner 頁面應優先讓使用者先看懂：

1. 這個 Agent 是做什麼的
2. 我要從哪裡開始輸入或操作
3. 結果會出現在什麼地方
4. 如果我是登入使用者，我還可以保存或調整

理想上，首屏應讓使用者很快理解：

1. 這個頁面現在能幫你完成什麼
2. 你要先做什麼
3. 你會得到什麼結果

而不是先看到 workflow 身分、技術來源或 code preview 入口。

若目前使用者是直接使用者，頁面應更進一步隱去建立者才關心的訊息，只保留任務完成所需內容。

### 可變 slot

依 agent 能力啟用的部分：

1. `conversation`
2. `structured_input`
3. `result_summary`
4. `artifacts`
5. `evidence`
6. `history`
7. `quick_actions`

這些 slot 在前台應優先被包裝成更自然的體驗區塊，例如：

1. `conversation` 可表現為對話區
2. `structured_input` 可表現為任務表單或需求卡
3. `result_summary` 可表現為結論卡、推薦卡、摘要板
4. `artifacts` 可表現為附件、清單、表格或報告
5. `evidence` 可表現為參考依據或為什麼這樣建議

### 主輸入方式原則

每個 Agent 在 Runner 中都必須有一個主輸入方式。

也就是說：

1. 聊天
2. 結構化欄位
3. 圖片 / 附件輔助

這三類能力可以共存，但不應同時作為同權重入口。

系統應根據既有 Workflow / Modules 配置，自動推定哪一種是主輸入方式。

### 主結果容器原則

每個 Agent 在 Runner 中也必須有一個主結果容器。

例如：

1. 對話回覆
2. 推薦卡
3. 摘要板
4. 表格 / 清單

其他結果形態可作為補充，但不應與主結果同權重並列。

## MVP 任務 archetype 對應

在目前 PoC 階段，Runner 至少應能清楚對應以下幾類直接使用任務：

### 顧問 / 問答型

1. 主輸入：聊天或簡單自由文字
2. 主結果：對話回覆或摘要回覆
3. 補充層：查看依據、下一步

### 表單評估型

1. 主輸入：結構化欄位
2. 主結果：摘要卡或結論板
3. 補充層：查看依據、補充說明

### 推薦型

1. 主輸入：聊天或簡短需求欄位
2. 主結果：推薦卡
3. 補充層：理由、依據、可選話術或下一步

### 回覆助手型

1. 主輸入：聊天
2. 主結果：可直接採用的回覆區或回覆卡
3. 補充層：理由、依據、下一步動作

### 摘要 / 判讀型

1. 主輸入：聊天、欄位或附件三者其一為主
2. 主結果：摘要板或判讀結論卡
3. 補充層：依據與可採用等級（若任務風險較高）

### Capability-Driven Rendering

Runner 不應問「這是不是某個固定案例」，而應問：

1. 這個 Agent 需要什麼輸入方式
2. 這個 Agent 產出什麼型態的結果
3. 這個 Agent 是否需要 evidence / history / artifacts
4. 這個 Agent 是否需要角色專用快捷操作

這些判斷的目的，是幫系統推定一個合理的主輸入方式與主結果容器，而不是把所有可能都同時塞進頁面。

## Runner Scene Profile

### 定義

Runner 應支援一份非持久化 `scene_profile`，用來描述當前 Agent 的 runner 組裝方式。

### 最低欄位

1. `layout_variant`
2. `input_mode`
3. `result_mode`
4. `enabled_slots`
5. `capabilities`

### 來源

`scene_profile` 可由以下資訊推導：

1. 當前 `python_source`
2. host-side agent metadata
3. server runtime introspection

它不能成為正式保存主來源。

## 中央主區

### 必備內容

1. Agent/Workflow 標題
2. 至少一種 primary input region
3. 至少一種 result region
4. 執行中狀態
5. 回應結果或輸出物件

中央主區應更像主要體驗舞台，而不是聊天測試框。對真實場域使用者來說，這裡是整頁最重要的產品內容。

### 可擴充區塊

主區應預留可插入場景化區塊的位置，例如：

1. conversation stream
2. structured input form
3. summary cards
4. evidence cards
5. structured result panels
6. session history comparison
7. artifact viewers

### 前台呈現原則

1. 不要求所有 Agent 都用聊天泡泡當主呈現
2. 若結果本質上更像卡片、清單、摘要或報告，就應用那種形式呈現
3. 若 evidence 對使用者有價值，應做成可理解的「依據」區，而不是 trace log
4. 若 history 對使用者有價值，應做成比較或時間軸，而不是事件流 debug 檢視
5. 首屏不可要求使用者先理解系統背景或 Agent 結構，必須先讓使用者知道如何開始任務
6. 無論有多少輔助能力，頁面都應先讓人一眼看出主輸入與主結果各是哪一塊

### 結果可採用等級

若 Agent 的任務性質需要，Runner 可在結果附近以輕量狀態表達：

1. `可直接使用`
2. `建議人工確認`
3. `先補資料再判斷`

這個狀態不應蓋過主結果，但在需要時可幫助第一線判斷風險。

### AI Hub 體驗模式額外要求

必須讓主區視覺更像公開互動頁，而不是 Builder 的延伸介面。

若面向外部角色，例如顧客或前線使用者，主區應更接近完整的任務頁或顧問頁，而不是把內部工作台直接拿來外露。

### 最低退化模式

若某個 Agent 沒有額外 capability，Runner 必須能退化成最小聊天/輸入/結果頁，而不是報廢整個 sceneable 架構。

## 右側側欄

### Layer 1: 共通資訊

所有模式都可見：

1. Workflow 名稱
2. 來源狀態
3. Powered by Agentic SDK

這些資訊應視覺上退後，不可壓過主任務區。對大部分真實使用者而言，這些屬於次要資訊。

若目前使用者是直接使用者，這些資訊可進一步收斂成更輕量的資訊條或次層抽屜。

### Layer 2: 進階操作

只對下列模式可見：

1. 匿名試跑
2. 手動登入完整模式
3. AI Hub 導流可回編模式

內容：

1. 查看程式碼
2. 匯出 `.py`
3. 返回建構頁
4. 依 capability 顯示 quick actions entry

其中 `查看程式碼`、`匯出 .py` 等能力，在前台應視權限退到次要層，不應讓一般使用者覺得這是一個工程工具。

### Layer 3: 保存操作

只對下列模式可見：

1. 手動登入完整模式
2. AI Hub 導流可回編模式

內容：

1. 保存到 AI Hub
2. 最近保存時間
3. 保存成功/失敗狀態

## 程式碼 Preview 小視窗

### 角色定位

程式碼不是獨立頁面，而是試跑頁上的輔助視圖。

### 內容

1. 目前 Python source 預覽
2. 複製按鈕
3. 匯出 `.py`

### 不可見模式

Mode C: AI Hub 導流唯讀體驗模式不可見。

對直接使用者來說，即使模式允許，code preview 也應預設退到更次層，而不是視覺上與主任務並列。

## 返回建構頁規則

### 可返回模式

1. 匿名試跑模式
2. 手動登入完整模式
3. AI Hub 導流可回編模式

### 不可返回模式

AI Hub 導流唯讀體驗模式不可返回建構頁。

### 文案建議

對 AI Hub 可回編模式，建議按鈕文案為：

`回到建構頁更新配置`

## AI Hub 體驗模式規格

### 唯讀體驗

1. 不顯示 code preview
2. 不顯示返回建構頁
3. 不顯示保存到 AI Hub
4. 不顯示內部模組細節

### 可回編體驗

1. 預設仍先落在試跑頁
2. 顯示「這是從 AI Hub 載入的既有 Workflow」
3. 允許返回建構頁與保存

## 頁面上下文提示

頁面頂部或側欄必須有輕量模式提示：

1. 匿名試跑模式
2. 已登入，可保存到 AI Hub
3. AI Hub 體驗模式（唯讀）
4. AI Hub 既有 Workflow，可更新配置

## 視覺方向

1. 匿名與登入模式偏工作台
2. AI Hub 唯讀模式偏產品互動頁
3. 程式碼 preview 要像輔助抽屜，不應壓過聊天主區
4. 場景化模組仍應服從 generic runner shell 的表面與版面語言
5. 不因 Agent 不同而讓整頁長成完全不同產品
6. 整頁第一眼應先像可直接使用的 Agent 頁面，而不是 runtime 測試頁

### 建立者預覽與直接使用的差異

1. 建立者在 Runner 中可看到較完整的上下文、保存與回 Builder 能力。
2. 直接使用者在 Runner 中只應優先看到任務、輸入、結果、依據與下一步。
3. 這是同一個頁面的資訊密度差異，不是兩張不同頁面或前台要理解的模式名稱。

## Mobile-Safe 原則

Runner 不一定需要 mobile-first，但必須 mobile-safe。

至少要保證：

1. 首屏任務說明在手機上仍清楚可見
2. 主 CTA 與主要輸入區不會被摺疊到第二屏才看見
3. 結果摘要與 `查看依據` 展開區可在手機上順利閱讀
4. 側欄資訊自動退到次層，不可壓縮主任務區

### 建議美術細節

1. 中央主區留白要比 Builder 更大，讓操作與結果呼吸
2. 結果區可用卡片、摘要板、表格、清單等更產品化的輸出容器
3. 側欄應更薄、更安靜，像輔助資訊抽屜
4. 對外模式下，Powered by 與來源資訊保留但弱化
5. 使用者主要 CTA 應聚焦在開始、送出、重試、下一步，而不是工程操作

### 文案原則

前台文案應優先用使用者語言，例如：

1. `請告訴我你的需求`
2. `上傳相關圖片或資料`
3. `這是目前的建議`
4. `為什麼會這樣建議`

而不是優先顯示：

1. runtime
2. workflow execution
3. trace
4. artifacts
5. capability

## 最小可用性判準

### 可視為最小通用 Agent 頁面的條件

若只談平台層，Runner 在具備下列條件時可成立為最小通用 Agent 頁：

1. 可送出輸入並得到 workflow 回應
2. 可理解目前使用的是哪個 workflow
3. 可看見執行狀態與錯誤
4. 可視權限保存、回編、匯出
5. 可依 scene profile 啟用或停用不同 runner slots

### 不可直接推論為場域可用的情況

即使符合上述條件，也不能直接推論任何特定 Agent 已可直接落地。若某個 Agent 需要額外的輸入結構、歷史比較、專業摘要、artifact viewer 或 evidence 視圖，應以 capability 啟用相應 slot，而不是臨時硬改整頁。

## 錯誤狀態

### 試跑失敗

應在聊天區與狀態區同步呈現，不可只把錯誤塞成單純的 assistant 內容。

### 保存失敗

應在側欄以明確狀態顯示保存失敗原因，並保留重試入口。

### deep link 不完整

應顯示專用錯誤頁或狀態卡，不導向 builder。

## PM 驗收標準

1. 所有流程都能落在試跑頁。
2. AI Hub 唯讀模式看不到編輯與程式碼細節。
3. AI Hub 可回編模式可以先體驗再回建構頁。
4. 保存與 code preview 權限符合模式矩陣。
5. 新 Agent 的場景化需求可透過 slot 與 capability 擴充，而不是新做一張 runner 頁。
6. Runner 不依賴特定 use case 命名或固定案例邏輯。
7. 第一線直接使用者不需要理解 Builder 或 workflow，也能完成主要任務。