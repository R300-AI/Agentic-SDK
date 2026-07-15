# Workflow Overview

`Workflow` 是 Agentic SDK 的公開組裝入口。它的責任不是定義單一模型能力，而是把感知、規劃、檢索、執行與反思等模組串成一條可執行流程，並決定執行過程中要搭配哪一層引擎來承接中繼狀態與上下文。

這一頁先給你看 workflow 的組裝模型、五大功能的角色，以及閱讀這套文件站時應如何在各模組頁與 workflow 引擎頁之間切換。

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

在這套文件站的概念裡，`Workflow` 不只串接節點，也決定本輪執行用哪個引擎保存狀態。預設情況下，會以 `InContextMemory` 作為 workflow 的引擎，承接輸入、中繼結果與本輪推進所需的暫時資料。

## 五大功能的角色

### Perceive

把使用者輸入整理成後續節點可用的理解結果，例如最小輸入整理或 LLM 型輸入理解。

### Plan

決定下一步要進入哪個功能節點，並以 reasoning strategy 將問題拆解成可執行的工作流路徑。

### Retrieve

根據查詢條件取回條目、上下文或知識內容。這一版文件聚焦在最小條目命中與語意檢索。

### Action

產出最終回應。最小模組可直接組裝答案，模型型模組則透過 completion client 生成輸出。

### Reflect

檢查 action 結果是否可接受，並在需要時提供下一輪改進方向或重試信號。

## 最小流程與進階流程

### README 最小流程

`InputPerceive` → `KeywordRetrieve` → `DirectAnswerAction`。這條路徑用來說明如何用最少節點建立第一條 workflow。

### 模型型輸出流程

沿用最小流程的前段，將 action 換成 `CompletionAction`，並透過 OpenAI SDK client 接入模型能力。

### 進階規劃流程

以 planner 決定後續節點，結合 `Semantic Search Retrieve` 與 `Reflexion Reflect` 建立可迭代的 workflow。

## 文件站閱讀路徑

| 你現在要做的事 | 先看哪一頁 | 再看哪一頁 |
| --- | --- | --- |
| 理解 workflow 怎麼組 | Workflow Overview | [Module Families](module-families.md) |
| 理解 workflow 預設使用哪個引擎 | [Workflow 引擎選項](workflow-engines.md) | 對應的功能模組頁 |
| 直接找某一類模組規格 | [Module Families](module-families.md) | 3.1 到 3.5 對應頁面 |

下一步建議先看 [Workflow 引擎選項](workflow-engines.md)，再進各功能模組頁查參數與輸入輸出定義。