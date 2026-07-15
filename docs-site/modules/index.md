# 模組家族

這一頁整理 Agentic SDK 的五個模組家族，目的是先把文件裡要用的標準名、家族責任與適用範圍定清楚。這份總覽處理的是家族層級分工；當你確認需求所屬的家族之後，再進對應頁面查模組標準名、標準輸入輸出格式與對應 use case。

## 概觀

一輪 workflow 會依序經過輸入整理、作業安排、資料補回、內容生成與輸出檢查。這五段工作分別由 `Perceive`、`Plan`、`Retrieve`、`Action` 與 `Reflect` 接手，形成一條能夠往前推進，也能回頭補資料與重寫內容的處理流程，如圖 1 所示。

![Framework](../assets/framework.png)

圖 1：五個模組家族在 workflow 中的接手順序。

目前這份定義處理的是單輪 request / response，節點之間以 JSON 物件交換資料，輸入來源只包含純文字、結構化欄位與圖片檔，圖片檔只接受 `image/png`、`image/jpeg`、`image/webp`。在這個範圍裡，使用者介面直接對接的是 `Perceive` 的輸入與 `Action` 的輸出；`Plan`、`Retrieve`、`Reflect` 三個家族之間交換的不是表單欄位，而是同一份 workflow 內部資料物件，這份物件在文件裡統一寫成 `Entities`。

| 家族 | 標準模組列表 | 接手時機 | 交付成果 | 主要工作 |
| --- | --- | --- | --- | --- |
| Perceive | PassThroughPerceive、TextPerceive、StructuredPerceive、TextImagePerceive | 收到新輸入時 | 感知摘要 | 把原始輸入整理成查詢、標籤與摘要。 |
| Plan | NextStepPlan | 收到感知摘要或查回資料時 | 下一節點決策 | 決定下一步交給 `Retrieve` 還是 `Action`。 |
| Retrieve | KeywordRetrieve、SemanticRetrieve、HybridRetrieve | 收到查找指示時 | 檢索結果 | 查回條目、歷史紀錄、知識內容或比對結果。 |
| Action | DirectAnswerAction、GenerativeAction、StructuredAction | 收到可用材料時 | 對外回應內容 | 組成自然語言回應或固定欄位輸出。 |
| Reflect | ResponseCheckReflect、EvidenceCheckReflect | 收到 Action 結果時 | 通過或退回判定 | 檢查回應完整性與證據是否足夠。 |

表 1：五個模組家族的標準模組名、接手時機、交付成果與主要工作對照表。

表 1 使用的是文件標準名。部分標準名已對應到現有程式類別，部分仍是文件先行定義的模組名；各頁會再列出它們與現有舊名的對應關係，以及標準輸入輸出格式。

## Entities

`Entities` 是 workflow 內部節點交換資料時使用的核心標準物件。`Plan`、`Retrieve`、`Reflect` 這三個家族都讀寫同一份物件；這裡只保留家族之間穩定共享的最小必要欄位，不把 UI 輸入欄位或 `Action` 的額外輸出配置一起塞進來。

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

### Entities 欄位群組

| 欄位群組 | 欄位 | 說明 |
| --- | --- | --- |
| 原始問題 | `user_message` | workflow 內部要持續保留的原始提問。 |
| 感知摘要 | `perceive_query`、`perceive_label`、`perceive_summary` | `Perceive` 整理後交給內部節點使用的核心摘要。 |
| 規劃結果 | `next_node`、`retrieve_query`、`plan_reason` | `Plan` 交出的下一步決策與查找意圖。 |
| 檢索結果 | `retrieved_items`、`retrieved_snippet`、`retrieved_hit_count`、`retrieved_source` | `Retrieve` 交出的命中內容與摘要。 |
| 回應結果 | `action_status`、`final_message`、`action_error` | `Action` 交出的核心對外結果。 |
| 驗收結果 | `reflect_verdict`、`reflect_reason` | `Reflect` 交出的驗收判定與退回原因。 |

不放進核心 `Entities` 的欄位，例如 `input_fields`、`input_images`、`response_schema`、`final_data`、`reflect_patch`，仍可留在各模組自己的輸入輸出定義中；只是它們不是五大家族之間都必須共享的最小共同欄位。

## 建議閱讀順序

1. 先看 [Workflow Overview](../workflow-overview.md)，確認五個模組家族各自接手哪一段工作。
2. 再看 [Workflow 引擎選項](../workflow-engines.md)，理解流程跑動時由哪一層保存中間資料。
3. 最後進入你要的功能頁，查標準名、標準輸入輸出格式與對應 use case。