# Use Case

這一區用案例文章的方式，示範 Agentic SDK 如何被導入到具體應用。每一篇都會從場景背景、導入挑戰、流程設計到可擴展性，完整說明 Agentic SDK 在真實系統裡扮演什麼角色，以及五個模組家族如何組成一條可落地的流程。

## 收錄案例

- [LaNew 售鞋顧問](lanew-footwear-advisor.md)：用門市購鞋與足型建議場景，說明 Agentic SDK 如何把商品知識、顧客需求與推薦話術串成可重複使用的顧問流程。
- [BCI 射箭教練](bci-archery-coach.md)：用腦機介面輔助訓練場景，說明 Agentic SDK 如何把多模態訊號整理成教練可採取的訓練建議。
- [ICOPE 六力評估助手](icope-six-capacity-assistant.md)：用高齡照護六力評估場景，說明 Agentic SDK 如何把六力結果、追蹤紀錄與照護建議串成可持續推進的評估流程。

如果你要復刻這些案例，可以直接看下面這張模組配置表。表的欄位是三個 use case，列則是五個模組家族；你可以把每一欄視為一套完整配置，依序選用對應的 `Perceive`、`Plan`、`Retrieve`、`Action`、`Reflect` 模組來重建同一條流程。

| 模組家族 | [LaNew 售鞋顧問](lanew-footwear-advisor.md) | [BCI 射箭教練](bci-archery-coach.md) | [ICOPE 六力評估助手](icope-six-capacity-assistant.md) |
| --- | --- | --- | --- |
| [Perceive](../modules/perceive-modules.md) | TextImagePerceive | TextPerceive | StructuredPerceive |
| [Plan](../modules/plan-modules.md) | NextStepPlan | NextStepPlan | NextStepPlan |
| [Retrieve](../modules/retrieve-modules.md) | HybridRetrieve | SemanticRetrieve | HybridRetrieve |
| [Action](../modules/action-modules.md) | StructuredAction | GenerativeAction | StructuredAction |
| [Reflect](../modules/reflect-modules.md) | EvidenceCheckReflect | ResponseCheckReflect | EvidenceCheckReflect |

表 1：三個 use case 的五大模組家族配置表，可依欄位重現對應流程。

## 閱讀方式

1. 先看案例文章，理解商業背景、導入問題與系統責任。
2. 再對照 [Workflow Overview](../workflow-overview.md) 看這些場景是如何映射到 `Perceive`、`Plan`、`Retrieve`、`Action`、`Reflect`。
3. 最後回到各功能頁，細化你要採用的模組與初始化參數。
