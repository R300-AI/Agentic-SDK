# Multi-Model Dashboard — 部署資源可視化策略 [R25]

> 受眾:UI 整合者、產品決策、PoC 展示窗口
> 目的:定義 Multi-Model Dashboard 的核心需求,以及「觀測能力(Phase 1)」與「圖形編排能力(Phase 2)」的拆分理由。

## 一、為何 Dashboard 是現階段重點

Action Item 明示:

> **Agentic SDK — 從「API 介面」升級為「邊緣叢集管理協定」**
> **2. 上下文管理與部署資源可視化 (Multi-Model Dashboard)**

對外要證明「Agentic SDK 是叢集管理協定」而非「OpenAI Proxy」,**Dashboard 是唯一能讓非技術層決策者直觀理解此差異的載體**。API 只能證明「能跳」,Dashboard 才能證明「可調度」。

「Multi-Model」三個字的關鍵語意:
- **不是單一模型的 SLA 監控**(那是 Model Card 的事)
- **不是單一 Agent 的 trace 視覺化**(那是 Phoenix / LangSmith 已解決的事)
- **是多個模型同時部署於同一邊緣叢集時的橫向視角**——資源競爭、調度決策、跨模型工作流分配

## 二、能力拆分:觀測 vs 編排

Dashboard 包含兩種根本不同的能力,工程複雜度落差極大,本專案明確將其拆為兩個階段:

| 能力 | 性質 | 階段 | 工程複雜度 |
|------|------|------|------------|
| **執行觀測**(被動讀取) | 即時資料視覺化、節點亮燈、Token 消耗時序圖 | Phase 1(M2 / M3 必需) | 低,Streamlit 100 行內可完成 |
| **圖形編排**(主動產生) | 拖曳連線、節點屬性面板、序列化格式、撤銷重做 | Phase 2(M3 後評估) | 高,需 fork 既有框架或自製 |

PoC 的對外可見成果只需「觀測」即可達成——使用者透過 OpenAI SDK 觸發工作流,Dashboard 即時顯示節點動向。**圖形編排是「讓使用者自製工作流」的延伸能力,不在 M3 驗收範圍內**。

## 三、Phase 1 範圍:執行觀測 Dashboard

### 需求清單(M3 對外可見成果)

| 需求 | 內容 |
|------|------|
| **觀測-1:節點存活拓樸** | 列出上游推論伺服器是否健康、目前載入哪些模型(`GET /v1/models` 結果) |
| **觀測-2:即時推論指標** | 最近 N 次推論的 TTFT / tokens/sec / 輸出長度時序圖 |
| **觀測-3:Workflow 執行進度** | 當前正在執行的工作流,五節點 Perceive / Plan / Retrieve / Reflect / Action 哪一個亮燈、累計 Token 消耗 |
| **觀測-4:降級事件清單** | 三道閘門觸發、Token 過期、上下文降級事件的即時 log |

### 技術選擇:Streamlit(MIT)

選 Streamlit 而非 Langflow / Grafana 的理由:

| 維度 | Streamlit | Grafana | Langflow |
|------|-----------|---------|----------|
| 語言一致性 | ✅ Python,與 SDK 同棧 | ❌ 需另起 Prometheus + 查詢語法 | ✅ Python |
| Fork 必要性 | ❌ 不需 fork,直接使用 | ❌ 不需 fork | ⚠️ 需深 fork 才能對齊五節點型別 |
| 即時更新 | ✅ 原生支援 `st.rerun()` | ✅ 但需設定 dashboard JSON | ✅ |
| Phase 1 工程量 | 1–2 天 | 3–5 天(含 Prometheus 設定) | 不確定(取決於 fork 深度) |
| 對外觀感 | 工程風,接受度中等 | 專業監控,接受度高 | Agent 平台風,接受度高 |

PoC 階段選 Streamlit,**接受「工程風」的視覺代價,換取最快上線**。對外展示時 demo 路徑為「OpenAI SDK 呼叫 → Streamlit 即時顯示五節點動向」,符合 M3-1 的 15 分鐘上手條件。

MVP 後若需要更高的視覺品質,可平行接 Grafana(無需替換 Streamlit,兩者讀同一份遙測資料即可)。

### Phase 1 不包含的內容

- ❌ 任何使用者輸入(只有「觀看」,沒有「操作」)
- ❌ 工作流的儲存與重放(由 SDK 內部處理,Dashboard 不負責持久化)
- ❌ 跨工作流的歷史聚合(只看「現在」,歷史趨勢留給 Grafana)

## 四、Phase 2 範圍:圖形編排能力(規劃中)

[blueprint/milestones.md](../../blueprint/milestones.md) M3 對外驗收已通過,內部使用者亦明確要求拖曳介面;Phase 2 啟動條件成立,**已進入規劃**。

完整的選型結論、使用者體驗設計、交付里程碑、技術接點清單,見 [phase5-graph-editor-plan.md](phase5-graph-editor-plan.md)。本節僅保留與 Phase 1 的分工原則;細節以該文件為準。

### 與 Phase 1 Dashboard 的分工(不重複觀測)

| 能力 | 由誰提供 |
|------|----------|
| 拖曳節點、設計工作流、儲存載入 YAML、跑一次 | **Phase 2 Editor**([phase5-graph-editor-plan.md](phase5-graph-editor-plan.md)) |
| 五節點亮燈、推論指標、降級事件、節點存活 | Phase 1 Dashboard(M2 已交付) |

Editor 與 Dashboard 透過 `workflow_id` 在 URL 上交接,**Editor 不重做觀測,Dashboard 不負責編輯**。

### 為什麼不在 Phase 1 直接做圖形編排

當初延後的三個理由,在 Phase 2 啟動時的處理方式:

1. **M3 驗收不需要** → M3 已通過,Phase 2 是「使用者體驗加值」,不在原 PoC 對外可見成果內
2. **編排框架選型需要 spike** → 在 [phase5-graph-editor-plan.md §二](phase5-graph-editor-plan.md) 已決選 Langflow 為主、React Flow 為備案,fork 邊界已界定
3. **Phase 1 已有替代入口** → 仍保留;Editor 不取代 OpenAI SDK 呼叫路徑,只新增第二條入口


## 五、與 Phoenix / Grafana 等工具的關係

本 Dashboard **不取代** 既有 Observability 工具,而是補位它們未覆蓋的視角:

| 工具 | 視角 | 與本 Dashboard 的關係 |
|------|------|----------------------|
| Arize Phoenix [R25] | 單一 Agent 對話與工具呼叫鏈 | 互補,可從本 Dashboard 連結跳轉 |
| Grafana + Prometheus | 節點層資源長期趨勢 | 互補,本 Dashboard 取即時快照,Grafana 看歷史 |
| LangSmith [R25] | LangChain 工作流 trace | 互補,使用者已有 LangSmith 可直接接 |
| Open WebUI [R01] | 對話內容互動式檢視 | 互補,使用者驗證對話品質用(上游 README 已示範整合) |

本 Dashboard 提供的獨特視角:**「多模型 × 五節點」的叢集級工作流即時視圖**,這是上述工具皆未直接提供的。

## 六、不在範圍內

- ❌ 客製化 Dashboard 開發服務(由整合商於 Streamlit/Langflow 之上自行擴充)
- ❌ Dashboard 使用者權限管理(由部署環境的 IAM 處理)
- ❌ 告警通知通道整合(由整合商於後端接入 Prometheus AlertManager)
- ❌ 行動裝置適配(Streamlit 桌面優先,Phase 2 再評估)
