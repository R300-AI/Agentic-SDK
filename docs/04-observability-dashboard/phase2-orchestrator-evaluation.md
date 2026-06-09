# M5 Phase 2 圖形編排框架啟動條件評估 [R25]

> 受眾:Phase 2 啟動時的決策者(工程負責人 / 產品負責人 / 整合商窗口)
> 目的:提供 Langflow / React Flow / 自製三種候選的客觀評估骨架,以及 Phase 1 期間應蒐集的證據清單。本文**不做選型結論**——選型發生在 Phase 2 啟動條件成立、且證據蒐集完成後。
> 上游連結:[visualization-ui.md §四](visualization-ui.md) 的決策骨架在此展開為可填空的評估格

---

## 一、為什麼需要這份評估

[visualization-ui.md §四](visualization-ui.md) 已說明:

> 編排框架選型本身需要 spike。做錯選擇會拖累整個 Phase 2。

「做錯選擇」具體指三種失敗模式:

1. **抽象失配**:框架的節點/邊抽象無法乾淨對應 Perceive / Plan / Retrieve / Reflect / Action,被迫長期維護一個與上游漸行漸遠的 fork
2. **格式失配**:UI 序列化格式與 [`WorkflowConfig`](../../agentic_sdk/workflow/config.py) 的 YAML/JSON 不能雙向轉換,導致 UI 編出來的圖無法被 SDK 執行,或 SDK 跑出來的圖無法回到 UI 修改
3. **回環失配**:本專案的工作流不是靜態 DAG——Reflect 可決定回到 Plan,Plan 可重新 Retrieve。多數圖形編排框架假設「trigger → action」線性流(典型如 n8n),這是結構性錯誤,事後無法修復

這份文件存在的價值,是讓決策者在動手前先把上述風險點具體化、可比較。

---

## 二、本專案對編排 UI 的硬性要求

任何候選框架若無法滿足以下五點,直接淘汰,不進入評分:

| 編號 | 硬性要求 | 對應理由 |
|------|----------|----------|
| H1 | 必須支援**回環邊**(cycle):Plan ⇄ Retrieve、Reflect → Plan / Action | 五節點不是 DAG;[context-and-memory.md](../03-agentic-orchestration/context-and-memory.md) 已明示節點訪問計數與 `max_revisit` 閘門 |
| H2 | 節點型別必須能掛載**自訂屬性面板**(對應 `NodeSpec.params`) | Action 節點要選 upstream/foundry backend、Retrieve 要選 store backend |
| H3 | 必須能**雙向轉換** [`WorkflowConfig`](../../agentic_sdk/workflow/config.py) 的 YAML/JSON | 不接受「只能匯出無法匯入」 |
| H4 | 授權必須是 **MIT / Apache 2.0 / BSD**(可商用、無 copyleft) | 對齊 CLAUDE.md 第六條「魔改既有開源、可商用授權的專案」 |
| H5 | 維護活躍度:過去 90 天有 commit、issue 有回覆 | 避免引入棄維護的依賴 |

未通過硬性要求時,該候選**移至附錄,不參與第三節評分**。

---

## 三、候選評估格(待 Phase 2 啟動時填寫)

下表每格填入「分數(1–5) + 一句證據」。**禁止無證據打分**。

### 評分維度

| 維度 | 說明 | 權重 |
|------|------|------|
| **D1 抽象對齊** | 框架原生抽象與五節點 + Gates 的契合度;需 fork 多深? | 30% |
| **D2 格式契合** | UI 序列化格式轉換到 `WorkflowConfig` 的損失程度(零損 / 可逆 / 單向) | 20% |
| **D3 工程量** | 從 fork/採用到能跑通最小工作流的人天估計 | 20% |
| **D4 上游脫鉤成本** | 每次跟上游 rebase 的痛苦度(衝突頻率、修改面) | 15% |
| **D5 對外觀感** | 客戶/評審看到 demo 時的接受度(主觀,但需附對比依據) | 15% |

### 候選矩陣(空白,待 spike 後填入)

| 候選 | 授權 | D1 抽象 | D2 格式 | D3 工程 | D4 脫鉤 | D5 觀感 | 加權總分 | spike 結論 |
|------|------|---------|---------|---------|---------|---------|----------|------------|
| **Langflow** | MIT | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| **React Flow** | MIT | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |
| **自製(基於 React Flow / Svelte Flow)** | MIT | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ | ⬜ |

### 候選預判(僅供 spike 前的暖身,不可作為結論)

| 候選 | 預判優勢 | 預判風險 |
|------|----------|----------|
| **Langflow** | 完整 Agent 編排平台,節點面板/連線/序列化全套現成 | 抽象偏 LangChain,五節點映射可能需深 fork;節點型別系統與 `NodeSpec.type` 是否相容未知 |
| **React Flow** | 純 UI 元件,我們完全控制節點抽象;與 Streamlit / FastAPI 整合自由度高 | 工程量大(需自製屬性面板、序列化、撤銷重做);沒有現成 Agent 概念 |
| **自製** | 完全契合五節點 + Gates;與 SDK 同步演化無 rebase 痛苦 | 工程量最大;造輪子需強理由(僅在前兩者皆 fail 時才該走) |

**n8n 已預先排除**:trigger→action 線性流不符合 H1(無回環)。即使能設定 webhook 重入,也是繞道而非原生支援,證據面板會直接淘汰。

---

## 四、Phase 1 期間應蒐集的證據清單

Phase 2 不在當下啟動,但**現在不收集證據,Phase 2 啟動時就只能憑感覺決策**。以下證據在 M3 / M4 階段順手收集即可,**不需要為此另開 sprint**。

### 證據-A:使用者真有需求嗎(觸發條件)

對應 [visualization-ui.md §四](visualization-ui.md) Phase 2 啟動條件:

- [ ] 收集「使用者要求自訂工作流」的具體案例(Issue / 訪談記錄 / 客戶郵件),至少 3 筆
- [ ] 紀錄每一筆要求的場景:是想「改節點連線」?「換 Action 後端」?還是「加新節點」?
  - 若 90% 都是「換後端」——`WORKFLOW_ACTION_BACKEND` env 已解決,**不需要圖形 UI**
  - 若大多是「加新節點」——應優先擴充節點型別,Phase 2 仍可延後
  - 只有「改節點連線/回環邏輯」這一類需求,才真正觸發 Phase 2

### 證據-B:`WorkflowConfig` 的實戰彈性

- [ ] M4 多基台場景下,觀察 `WorkflowConfig` 的 YAML/JSON 是否需要新增欄位
- [ ] 若新增欄位頻繁,代表 schema 還不穩——**Phase 2 應再延後,避免在不穩 schema 上做 UI**

### 證據-C:候選框架的活躍度監測

每月一次,記錄三個候選的近 30 天 commit 數、closed issue 數、release 頻率:

| 月份 | Langflow | React Flow | Svelte Flow(備選) |
|------|----------|------------|---------------------|
| 2026-XX | ⬜ | ⬜ | ⬜ |

若任一候選在 Phase 2 啟動前已停滯 90 天以上,評估時直接淘汰,降低 D5(脫鉤成本)風險。

---

## 五、Phase 2 啟動條件(摘自 visualization-ui.md §四 + 本文 §四)

**全部滿足**才啟動 Phase 2:

1. ✅ M3 對外驗收已通過(PoC 對外可見成果已交付)
2. ✅ [visualization-ui.md §四](visualization-ui.md) 的三個觸發條件之一成立
3. ✅ 本文 §四 證據-B 顯示 `WorkflowConfig` schema 連續 60 天未新增欄位
4. ✅ 本文 §三 候選矩陣已由至少一名工程師完成 spike 並填入分數

未滿足時,工程資源繼續優先用於:擴充節點型別、優化 Active Context、補強 Multi-Model Dashboard 觀測能力。

---

## 六、不在範圍內

- ❌ 在啟動條件未成立前,先選定某框架(避免錨定效應污染後續評估)
- ❌ 評估閉源 / 商用授權編排平台(已由 H4 排除)
- ❌ 自製 DSL 設計(若選自製,DSL 設計屬 Phase 2 啟動後的第一個任務,不在本評估)
