# Workflow Overview

`Workflow` 是 Agentic SDK 的公開組裝入口。它負責把可用模組接成一條可執行流程，讓輸入整理、流程判斷、資料查找、內容生成與輸出檢查可以按需求接手。同一個 workflow 可以只用其中幾類模組，單次執行實際會走到哪些節點，取決於各節點回傳的 `next_node`。

這一頁先說明 `Workflow` 的公開組裝方式、執行時如何保存中間資料，以及五個模組家族在文件標準名下的責任位置。

## 公開組裝模型

!!! info "公開契約"
    所有需要模型的模組，一律以 OpenAI SDK 相容介面接入。以文件標準名來看，這條規格適用於 `TextPerceive`、`TextImagePerceive`、`NextStepPlan`、`SemanticRetrieve`、`GenerativeAction`、`StructuredAction`、`ResponseCheckReflect` 與 `EvidenceCheckReflect`。

```python
Workflow(
    perceive=...,
    plan=...,
    retrieve=...,
    action=...,
    reflect=...,
)
```

`Workflow` 建立完成後，未顯式指定的模組會由內建預設實作補上；但某個節點會不會真的在這次執行中被走到，仍取決於前一節點回傳的 `next_node`。執行期間，`Workflow` 會在內部建立一份 `WorkflowState`，公開別名為 `InContextMemory`，用來保留輸入內容、查回來的資料、Action 結果與節點中繼資料。

在這套文件定義裡，使用者介面直接對接的是 `Perceive` 的輸入與 `Action` 的輸出。`Plan`、`Retrieve`、`Reflect` 三個家族之間交換的不是表單欄位，而是同一份 workflow 內部資料物件；這份物件在文件裡統一寫成 `Entities`。

下圖整理目前文件站採用的五家族循環模型：

![Framework](assets/framework.png)

圖 1：五個模組家族在 workflow 中的接手順序。

## 五大功能的角色

### Perceive

`Perceive` 模組負責接收原始輸入，像是使用者提問、表單欄位或圖片資料，並把它們整理成一份輸入摘要。這份摘要至少要讓後面的模組看得出來：這一輪在問什麼、有哪些重要欄位、哪些資料需要保留。對使用者介面而言，這一層就是 workflow 的輸入邊界。

### Plan

`Plan` 模組負責讀取輸入摘要與前一步留下的結果，決定下一步要做哪件事。文件標準名 `NextStepPlan` 交出的核心結果是下一節點決策，也就是把流程導向 `Retrieve` 或 `Action`。它的責任只到決定下一步為止，不負責檢查本輪輸出是否可交付。

### Retrieve

`Retrieve` 模組負責依照前一步的指示，把本輪需要的外部資料取回來。這些資料可以是商品內容、歷史紀錄、知識條目、語意檢索結果或其他證據。這一層與 `Plan`、`Reflect` 一樣，都透過 `Entities` 物件讀寫中間資料。

### Action

`Action` 模組負責把輸入摘要與查回來的資料整理成可交付的輸出。這份輸出可以是推薦說明、訓練建議、評估摘要或其他對外結果。文件標準名包含 `DirectAnswerAction`、`GenerativeAction` 與 `StructuredAction`。對使用者介面而言，這一層就是 workflow 的輸出邊界。

### Reflect

`Reflect` 模組負責檢查 `Action` 交出的內容是否已經可以交付。它處理的是驗收問題，不處理排程問題。文件標準名 `ResponseCheckReflect` 與 `EvidenceCheckReflect` 會交出通過或退回判定，以及需要補強的原因與方向。當判定為失敗時，`Reflect` 會把流程導回 `Plan`，或直接結束本次執行。

## Entities

`Entities` 是 workflow 內部節點交換資料時使用的核心標準物件。`Plan`、`Retrieve`、`Reflect` 都讀寫同一份物件；這裡只保留家族之間穩定共享的最小必要欄位：

```json
{
    "user_message": "",
    "perceive_query": "",
    "perceive_label": "",
    "perceive_summary": "",
    "next_node": "",
    "retrieve_query": "",
    "plan_reason": "",
    "retrieved_items": [],
    "retrieved_snippet": "",
    "retrieved_hit_count": 0,
    "retrieved_source": "",
    "action_status": "",
    "final_message": "",
    "action_error": "",
    "reflect_verdict": "",
    "reflect_reason": ""
}
```

像是 `input_fields`、`input_images`、`response_schema`、`final_data`、`reflect_patch` 這類欄位，仍可以存在各模組自己的輸入輸出規格裡；只是它們不屬於所有家族都必須共享的核心 `Entities`。

## 最小流程與進階流程

### README 最小流程

`PassThroughPerceive` → `KeywordRetrieve` → `DirectAnswerAction`。這條路徑對應 README 第一個範例：先整理輸入，再命中條目內容，最後直接組成回應。雖然 `Workflow` 仍可補上預設 `Plan` 與 `Reflect`，但這組節點的 `next_node` 已經直接形成三段路徑，因此本次執行不會走到 `Plan` 或 `Reflect`。

### 模型型輸出流程

`PassThroughPerceive` → `KeywordRetrieve` → `GenerativeAction`。這條路徑對應 README 第二個範例：保留原本的輸入整理與條目命中，僅將最後的輸出步驟改成透過 OpenAI SDK 相容 client 呼叫模型端點。

### 自訂 Action 流程

`PassThroughPerceive` → `KeywordRetrieve` → `SummaryAction`。這條路徑對應 README 第三個範例：前段仍由內建節點整理輸入與命中條目，最後的 `Action` 則改成使用者自訂物件，直接讀取 `InContextMemory` 中已留下的內容來組成回應。

### 規劃式檢索流程

`TextPerceive` → `NextStepPlan` → `SemanticRetrieve` → `NextStepPlan` → `GenerativeAction`。這條路徑對應使用規劃節點與語意檢索的進階流程：先理解輸入，再由 `Plan` 決定是否需要檢索，帶回檢索結果後再由 `Plan` 做一次下一節點決策，最後才交給 `Action` 產生回應。

若你要把 `Reflect` 接進 workflow，則需要讓 `Action` 的結果明確進入 `Reflect`，再由 `Reflect` 交出通過或退回判定。`Reflect` 家族適合用在你需要額外檢查輸出品質或失敗原因的流程。

## 文件站閱讀路徑

| 你現在要做的事 | 先看哪一頁 | 再看哪一頁 |
| --- | --- | --- |
| 理解 workflow 怎麼組 | Workflow Overview | [Module Family](modules/index.md) |
| 理解 workflow 預設使用哪個引擎 | [Workflow 引擎選項](workflow-engines.md) | 對應的功能模組頁 |
| 直接找某一類模組規格 | [Module Family](modules/index.md) | 3.1 到 3.5 對應頁面 |

下一步建議先看 [Workflow 引擎選項](workflow-engines.md)，再進各功能模組頁查參數與輸入輸出定義。