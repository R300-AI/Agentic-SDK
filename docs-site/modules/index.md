# Module Family

這一頁提供五大功能的總覽，幫你先判斷自己要去哪一類模組頁。文件站的模組家族定義，對齊 README 已定稿的公開敘事，而不是直接照搬目前程式內部檔案分佈。

## 流程示意

下圖先把五大家族的銜接關係畫成一個循環。若你先想理解整體流向，再進各模組頁，這張圖會比逐列讀表更快。

![Framework](../assets/framework.png)

從文件定義來看，`Perceive` 是每一輪的入口，先把輸入整理成後續可消費的理解結果。`Plan` 接著判斷這一輪應該先取資料、直接回答，或先進入反思判斷。`Retrieve` 不直接結束流程，而是把取回的內容交還給 `Plan`，讓 `Plan` 依新上下文再做一次決策。

`Reflect` 的角色則是回頭檢查目前回應是否可接受；若不夠好，就引導流程回到 `Retrieve` 或 `Action`。`Action` 負責把本輪整理出的內容轉成對外回應，完成後再回到下一輪的 `Perceive`。因此這套文件不是把 workflow 寫成單向直線，而是寫成一個持續循環的會話流。

## 功能家族矩陣

| 家族 | 模組列表 | 流程角色 |
| --- | --- | --- |
| Perceive | InputPerceive、LLMBasedPerceive、RuleBasedPerceive | 理解目前輸入，整理成後續可用的理解結果。 |
| Plan | ReActPlan | 根據目前上下文決定下一步流程。 |
| Retrieve | KeywordRetrieve、StubRetrieve、SemanticRetrieve | 取回條目、上下文或知識內容。 |
| Action | DirectAnswerAction、CompletionAction | 產出回應內容。 |
| Reflect | RuleBasedReflect、ReflexionReflect | 檢查目前回應是否需要修正。 |

## 建議閱讀順序

1. 先看 [Workflow Overview](../workflow-overview.md)，確認五大功能的角色。
2. 再看 [Workflow 引擎選項](../workflow-engines.md)，掌握預設 InContextMemory 與可替換引擎層。
3. 最後進入你要的功能頁，查模組的初始化參數與行為定位。

這頁是索引頁，不重複展開每個模組的細節。細節請進五個模組專頁。