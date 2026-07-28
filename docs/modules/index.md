# 模組家族

這一頁整理 Agentic SDK 的五個模組家族，先定義各家族的分工，再交代資料交換方式與閱讀順序。先看清楚需求落在哪一個家族，再進對應頁面查模組參數與輸入輸出格式，會比較容易掌握整條流程的接手關係。

## 概觀

一輪流程會依序經過輸入整理、作業安排、資料補回、內容生成與輸出檢查。這五段工作分別由 `Perceive`、`Plan`、`Retrieve`、`Action` 與 `Reflect` 接手，形成一條可推進、可補資料、可修正內容的處理流程，如圖 1 所示。

![Framework](../assets/framework.png)

圖 1：五個模組家族在流程中的接手順序。

目前這份定義處理多輪對話流程。節點之間以 JSON 物件交換結構化資料；需要模型的模組共用 `MemoryStore` 這個記憶抽象，實際型別可以是 `InContextMemory` 或 `PersistentMemory`。輸入來源包含純文字、結構化欄位與圖片檔，圖片格式支援 `image/png`、`image/jpeg`、`image/webp`。使用者介面對接 `Perceive` 的輸入與 `Action` 的輸出；`Plan`、`Retrieve`、`Reflect` 共用 `WorkflowState` 裡的 `Entities` 與 `ContextEntry`。先看下面這張表，可以快速掌握五個家族各自的模組與主要工作。

| 家族 | 標準模組列表 | 主要工作 |
| --- | --- | --- |
| Perceive | PassThroughPerceive、TextPerceive、TextImagePerceive | 把原始輸入整理成查詢、標籤與摘要。 |
| Plan | NextStepPlan | 決定下一步交給 `Retrieve` 還是 `Action`。 |
| Retrieve | KeywordRetrieve、SemanticRetrieve | 查回條目、歷史紀錄或知識內容。 |
| Action | DirectAnswerAction、GenerativeAction、ToolCallAction | 組成自然語言回應、固定格式文字輸出或 OpenAI 標準工具呼叫。 |
| Reflect | ResponseCheckReflect、EvidenceCheckReflect | 檢查回應完整性與證據是否足夠。 |

表 1：五個模組家族的模組名與主要工作對照表。

讀完這張表之後，接著看家族之間共用哪些資料。下一節會整理共用的 `Entities` 物件；各家族頁則列出模組參數與輸入輸出格式，方便把家族分工對回實際程式。

需要模型的模組會各自持有 OpenAI-compatible 連線設定。`TextPerceive`、`NextStepPlan`、`GenerativeAction`、`ToolCallAction`、`ResponseCheckReflect` 等模組都要明確提供 `api_key`、`base_url` 與 `model`，模型選擇由建立模組時的設定決定。

## Entities

`Entities` 是流程內部節點交換資料時使用的核心物件。`Plan`、`Retrieve`、`Reflect` 這三個家族會讀寫同一份物件；`Perceive` 的輸入參數與 `Action` 的輸出參數則放在各自模組頁定義。閱讀時先掌握一件事：`Plan`、`Retrieve`、`Reflect` 透過同一份 `Entities` 交換資料，完整對話歷史由目前的 `MemoryStore` 實作承接。

## 建議閱讀順序

這一頁聚焦整理的是五大家族之間穩定共享的核心欄位。確認完共用資料物件之後，就可以依照下面的閱讀順序，往各家族頁面展開。

1. 先看 [Workflow Overview](../workflow-overview.md)，確認五個模組家族各自接手哪一段工作。
2. 再看 [Workflow 記憶體類型](../workflow-engines.md)，理解流程跑動時由哪一層保存中間資料。
3. 最後進入你要的功能頁，查標準名與標準輸入輸出格式。