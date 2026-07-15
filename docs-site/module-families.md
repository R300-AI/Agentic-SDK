# Module Families

這一頁提供五大功能的總覽，幫你先判斷自己要去哪一類模組頁。文件站的模組家族定義，對齊 README 已定稿的公開敘事，而不是直接照搬目前程式內部檔案分佈。

## 先判斷你要解什麼問題

- 要理解輸入：先看 [Perceive](modules/perceive-modules.md)。
- 要決定流程路徑：先看 [Plan](modules/plan-modules.md)。
- 要取回知識：先看 [Retrieve](modules/retrieve-modules.md)。
- 要產出回應：先看 [Action](modules/action-modules.md)。
- 要做自我檢查：先看 [Reflect](modules/reflect-modules.md)。

## 功能家族矩陣

| 家族 | 模組 | 流程角色 | 下一步 | 是否支援OpenAI SDK |
| --- | --- | --- | --- | --- |
| Perceive | InputPerceive、LLMBasedPerceive、RuleBasedPerceive | 理解目前輸入，整理成後續可用的理解結果 | 固定交給 `Plan` | 僅模型型模組支援 |
| Plan | ReActPlan | 根據目前上下文決定下一步流程 | 可導向 `Retrieve`、`Action` 或 `Reflect` | 是 |
| Retrieve | KeywordRetrieve、StubRetrieve、SemanticRetrieve | 取回條目、上下文或知識內容 | 固定交回 `Plan` | 僅模型型模組支援 |
| Action | DirectAnswerAction、CompletionAction | 產出回應內容 | 固定交回 `Perceive` | 僅模型型模組支援 |
| Reflect | RuleBasedReflect、ReflexionReflect | 檢查目前回應是否需要修正 | 可導向 `Retrieve` 或 `Action` | 僅模型型模組支援 |

## 建議閱讀順序

1. 先看 [Workflow Overview](workflow-overview.md)，確認五大功能的角色。
2. 再看 [Workflow 引擎選項](workflow-engines.md)，掌握預設 InContextMemory 與可替換引擎層。
3. 最後進入你要的功能頁，查模組的初始化參數與流程角色。

這頁是索引頁，不重複展開每個模組的細節。細節請進五個模組專頁。