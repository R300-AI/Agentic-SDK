# Workflow Overview

`Workflow` 是 Agentic SDK 的公開組裝入口。它負責把五類模組接成一條可執行流程，讓輸入整理、流程判斷、資料查找、結果生成與結果檢查可以照順序接手。它同時也決定執行過程中由哪一層引擎保存中間資料。

這一頁先說明 workflow 的組裝模型、五個模組家族的基本定義，以及閱讀這套文件站時應如何在各模組頁與 workflow 引擎頁之間切換。

## 公開組裝模型

!!! info "公開契約"
    所有需要模型的模組，一律以 `OpenAI SDK form` 接入。這條規格適用於 `LLM Perceive`、各類 planner、`Semantic Search Retrieve`、`CompletionAction` 與 `Reflexion Reflect`。

```python
Workflow(
    perceive=...,
    plan=...,
    retrieve=...,
    action=...,
    reflect=...,
    engine=InContextMemory(...),
)
```

在這套文件站的定義裡，`Workflow` 不只負責串接模組，也決定本輪執行用哪個引擎保存中間資料。預設情況下，會以 `InContextMemory` 作為 workflow 引擎，用來保留輸入內容、查回來的資料、輸出草稿與本輪推進所需的暫存結果。

下圖示意這套文件定義中的流程循環：

![Framework](assets/framework.png)

## 五大功能的角色

### Perceive

`Perceive` 模組負責接收原始輸入，像是使用者提問、表單欄位、量測數值或上一輪留下來的資料，並把它們整理成一份輸入摘要。這份摘要至少要讓後面的模組看得出來：這一輪在問什麼、有哪些重要欄位、哪些資料需要保留。

### Plan

`Plan` 模組負責讀取輸入摘要與前一步留下的結果，決定下一步要做哪件事。它交出去的不是最終答案，而是一份處理指示，例如先補欄位、先查資料，或把現有材料交給 `Action` 起草。`Plan` 的責任只到安排下一個作業動作為止，不負責判定草稿能不能交付。這套文件中的 `Plan` 可以把流程導向 `Retrieve`、`Action` 或 `Reflect`。

### Retrieve

`Retrieve` 模組負責依照 `Plan` 的指示，把本輪需要的外部資料取回來。這些資料可以是商品內容、歷史紀錄、知識條目、語意檢索結果或其他證據。`Retrieve` 本身不產生最後回應，它的工作是把資料補齊，讓後面的模組有內容可用。這套文件中的 `Retrieve` 完成後會把查回來的資料交回流程，再由 `Plan` 或 `Action` 接手。

### Action

`Action` 模組負責把輸入摘要與查回來的資料整理成可交付的輸出。這份輸出可以是推薦說明、訓練建議、評估摘要或其他對外結果。依這套文件的流程定義，`Action` 完成後會把輸出草稿交給 `Reflect` 檢查，或在最小流程中直接交回下一輪 `Perceive`。

### Reflect

`Reflect` 模組負責檢查 `Action` 交出的內容是否已經可以交付。它處理的是驗收問題，不處理排程問題。也就是說，`Reflect` 不負責決定流程先走哪一步，而是檢查草稿有沒有漏答、資料引用夠不夠、格式能不能直接送出；若仍有缺口，就指出要回頭補資料還是重寫輸出。在這套文件定義中，`Reflect` 可以把流程導向 `Retrieve` 或 `Action`。

## 最小流程與進階流程

### README 最小流程

`InputPerceive` → `Plan` → `KeywordRetrieve` → `Plan` → `DirectAnswerAction` → `Perceive`。這條路徑用來說明如何用最少模組建立第一條 workflow：先整理輸入，再決定查詢方向，補齊資料後組出答案，最後回到下一輪輸入整理。

### 模型型輸出流程

沿用最小流程的前段，將最後的 `Action` 換成 `CompletionAction`，並透過 OpenAI SDK client 接入模型能力，再回到下一輪 `Perceive`。這條路徑適合需要模型潤飾文字、統整資料或生成較完整輸出的情境。

### 進階規劃流程

以 `Plan` 模組決定後續步驟，結合 `Semantic Search Retrieve` 與 `Reflexion Reflect` 建立可反覆修正的 workflow。這條路徑適合需要多次查證、補強資料與重寫結果的情境。

## 文件站閱讀路徑

| 你現在要做的事 | 先看哪一頁 | 再看哪一頁 |
| --- | --- | --- |
| 理解 workflow 怎麼組 | Workflow Overview | [Module Family](modules/index.md) |
| 理解 workflow 預設使用哪個引擎 | [Workflow 引擎選項](workflow-engines.md) | 對應的功能模組頁 |
| 直接找某一類模組規格 | [Module Family](modules/index.md) | 3.1 到 3.5 對應頁面 |

下一步建議先看 [Workflow 引擎選項](workflow-engines.md)，再進各功能模組頁查參數與輸入輸出定義。