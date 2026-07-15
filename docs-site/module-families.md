# Module Families

這一頁提供五大功能的總覽，幫你先判斷自己要去哪一類模組頁。文件站的模組家族定義，對齊 README 已定稿的公開敘事，而不是直接照搬目前程式內部檔案分佈。

## 先判斷你要解什麼問題

- 要理解輸入：先看 [Perceive](modules/perceive-modules.md)。
- 要決定流程路徑：先看 [Plan](modules/plan-modules.md)。
- 要取回知識：先看 [Retrieve](modules/retrieve-modules.md)。
- 要產出回應：先看 [Action](modules/action-modules.md)。
- 要做自我檢查：先看 [Reflect](modules/reflect-modules.md)。

## 功能家族矩陣

| 家族 | 模組 | 主要讀取 key | 主要寫入 key | 模型接入規格 |
| --- | --- | --- | --- | --- |
| Perceive | InputPerceive、LLM Perceive | `input` | `perceived_input`、`query` | 模型型模組使用 OpenAI SDK form |
| Plan | Chain-of-Thought Planner、ReAct Planner、Plan-and-Solve Planner | `perceived_input`、`reflection` | `plan`、`query` | OpenAI SDK form |
| Retrieve | KeywordRetrieve、Semantic Search Retrieve | `query`、`plan` | `retrieved_items` | 模型型模組使用 OpenAI SDK form |
| Action | DirectAnswerAction、CompletionAction | `perceived_input`、`retrieved_items`、`plan` | `draft_answer`、`final_answer` | 模型型模組使用 OpenAI SDK form |
| Reflect | Reflexion Reflect | `draft_answer`、`retrieved_items` | `reflection`、`final_answer` | OpenAI SDK form |

## 建議閱讀順序

1. 先看 [Workflow Overview](workflow-overview.md)，確認五大功能的角色。
2. 再看 [Workflow 引擎選項](workflow-engines.md)，掌握預設 InContextMemory 與可替換引擎層。
3. 最後進入你要的功能頁，查模組參數與輸入輸出規格。

這頁是索引頁，不重複展開每個模組的細節。細節請進五個模組專頁。