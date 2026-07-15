# 模組家族

這一頁整理 Agentic SDK 的五個模組家族，幫你先判斷一個需求應該交給哪一類模組接手。這份總覽處理的是家族層級的分工；當你確認需求所屬的家族之後，再進對應頁面查模組清單、初始化參數與輸入輸出格式。不同 workflow 可以只用其中一部分家族，單次執行也不一定會走完整五段流程。

## 概觀

一輪 workflow 會依序經過輸入整理、作業安排、資料補回、內容生成與輸出檢查。這五段工作分別由 `Perceive`、`Plan`、`Retrieve`、`Action` 與 `Reflect` 接手，形成一條能夠往前推進，也能回頭補資料與重寫內容的處理流程，如圖 1 所示。

![Framework](../assets/framework.png)

圖 1：五個模組家族在 workflow 中的接手順序。

表 1 將五個家族放在同一張對照表裡，方便直接比較它們在 workflow 中各自接手的時點與交付的成果。閱讀這張表時，重點不是先記模組名稱，而是先看一個模組接手的是流程中的哪一段工作，再看它交出去的是結構化輸入摘要、下一節點決策、命中內容與檢索結果、對外回應內容，還是通過或退回的檢查判定。只要先抓住這條判讀順序，五個家族之間的責任邊界就會自然拉開。

| 家族 | 模組列表 | 接手時機 | 交付成果 | 主要工作 |
| --- | --- | --- | --- | --- |
| Perceive | InputPerceive、RuleBasedPerceive、LLMBasedPerceive、StructuredPerceive、MultimodalPerceive | 收到新輸入或上一輪補充資料時 | 結構化輸入摘要 | 整理提問、欄位、量測值與本輪要保留的重點。 |
| Plan | ReActPlan | 收到輸入摘要或查回資料時 | 下一節點決策 | 決定下一步交給 `Retrieve` 還是 `Action`。 |
| Retrieve | KeywordRetrieve、StubRetrieve、SemanticRetrieve、HybridRetrieve | 收到查找指示時 | 命中內容與檢索結果 | 查回商品內容、歷史紀錄、知識條目或檢索結果，供後續節點使用。 |
| Action | DirectAnswerAction、CompletionAction、StructuredOutputAction | 收到可用材料時 | 對外回應內容 | 組成推薦說明、訓練建議、評估摘要等對外內容。 |
| Reflect | RuleBasedReflect、ReflexionReflect、EvidenceCheckReflect | 收到 Action 結果或錯誤時 | 通過或退回判定 | 檢查漏答、資料引用與格式，決定送出或退回補強。 |

表 1：五個模組家族的接手時機、交付成果與主要工作對照表。

表 1 同時列出 SDK 內建類別，以及這份文件會反覆使用的模組型態名稱。若你要確認某個名稱的初始化方式、輸入輸出格式，或是否已有可直接使用的類別，請再進對應家族頁面查看。

## 建議閱讀順序

1. 先看 [Workflow Overview](../workflow-overview.md)，確認五個模組家族各自接手哪一段工作。
2. 再看 [Workflow 引擎選項](../workflow-engines.md)，理解流程跑動時由哪一層保存中間資料。
3. 最後進入你要的功能頁，查模組初始化參數、輸入與輸出格式。

這頁整理的是家族層級的分工。當你已經知道需求要放進哪一個家族之後，再進五個模組專頁查該家族底下有哪些模組、初始化需要哪些參數，以及輸入輸出格式怎麼定義。