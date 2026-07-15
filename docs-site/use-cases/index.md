# Use Case

這一區不是 API reference，而是用較接近官方案例文章的方式，示範 Agentic SDK 如何被導入到具體應用。每一篇都不是單純列模組，而是從場景背景、導入挑戰、流程設計到可擴展性，完整說明 Agentic SDK 在真實系統裡扮演什麼角色。

## 收錄案例

- [LaNew 售鞋顧問](lanew-footwear-advisor.md)：用門市購鞋與足型建議場景，說明 Agentic SDK 如何把商品知識、顧客需求與推薦話術串成可重複使用的顧問流程。
- [BCI 射箭教練](bci-archery-coach.md)：用腦機介面輔助訓練場景，說明 Agentic SDK 如何把多模態訊號整理成教練可採取的訓練建議。
- [ICOPE 六力評估助手](icope-six-capacity-assistant.md)：用高齡照護六力評估場景，說明 Agentic SDK 如何把六力結果、追蹤紀錄與照護建議串成可持續推進的評估流程。

## 閱讀方式

1. 先看案例文章，理解商業背景、導入問題與系統責任。
2. 再對照 [Workflow Overview](../workflow-overview.md) 看這些場景是如何映射到 `Perceive`、`Plan`、`Retrieve`、`Action`、`Reflect`。
3. 最後回到各功能頁，細化你要採用的模組與初始化參數。
