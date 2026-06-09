# Agentic SDK — 專案脈絡 (CLAUDE.md)

## 一、本專案的位置

本儲存庫是工研 AI 生態系 TSiP 國產晶片落地藍圖中的其中一塊拼圖：**Agentic SDK**。

完整藍圖由兩個獨立、可分別演進的子系統組成：

| 子系統 | 儲存庫 | 角色 |
|--------|--------|------|
| **A. SLA 效能強制認證閘道（Model Card）** | [`R300-AI/amd-ryzen-ai-benchmark`](https://github.com/R300-AI/amd-ryzen-ai-benchmark) | 為「模型 × 晶片」組合產出可驗證的 SLA 履歷（TTFT、Peak Memory、Soak Test 等）。是 **上游依賴**，不在本專案實作。 |
| **B. 跨節點 Agent 資源編排總控台（Agentic SDK）** | 本專案 | 消費通過認證的模型，提供跨節點 Agent 工作流的上下文管理、動態 Offload 與可視化觀測。 |

兩者之間的契約：**Model Card 是 Agentic SDK 載入任何模型前的必要前置條件。** 沒有通過認證的模型不會被 SDK 信任，也不會出現在可調度資源池中。

---

## 二、本專案的核心目標

Agentic SDK 的本質定位是 **「邊緣叢集管理協定」**,不是「又一個 OpenAI Proxy」。OpenAI 相容 API 只是對外的相容介面,讓全球 Agent 生態系能零成本接入;真正的核心價值在於後端的叢集編排能力。

本階段聚焦兩個 Action Item,直接對齊上層使命:

### 目標一(現階段重點之一):跨節點 Agent 上下文管理

針對製造(T500)與醫療(R300)領域的多 Agent 工作流,提供:

- **跨節點上下文傳遞**:對話狀態在 Perceive / Plan / Retrieve / Reflect / Action 五大節點間的引用式傳遞
- **Token 過期處理**:分層記憶模型(Working Set / Active / Archived)避免邊緣端 OOM
- **五大節點為基本框架**:Perceive / Plan / Retrieve / Reflect / Action 是 SDK 必須遵從的編排典範,與各節點對應的學理基準及可接入的 SDK 模組見 [docs/README.md §3](docs/README.md)

### 目標二(現階段重點之二):部署資源可視化(Multi-Model Dashboard)

本階段最重要的對外可見成果。提供:

- **多模型橫向視角**:多個模型同時部署於邊緣叢集時的資源競爭、調度與健康度視圖
- **圖形拖曳介面**:**延後至 Phase 5 評估**(見 [blueprint/risk-decisions.md D2](blueprint/risk-decisions.md)),Phase 1–2 只實作執行觀測(Streamlit MIT)。未來若需圖形編排,候選為 Langflow(MIT)/ React Flow(MIT)/ 自製,不自建編輯器引擎
- **遙測底座**:token/sec、記憶體峰值、節點耗時的 OpenTelemetry 標準輸出

### 延伸方向(本階段不做,但設計需預留接口)

- **動態異質 Offload**:在 NPU / GPU / CPU 間動態調度推論負載。是必然趨勢,但 PoC 階段先採靜態硬體綁定。設計文件先寫好契約,實作延後。

### 對外介面層(支撐目標一、二的相容性外殼)

- **標準 REST API**
- **OpenAI SDK 相容端點**

開發者只需修改 `base_url`,LangChain / AutoGen / 任何 OpenAI SDK 使用者就能直接調度 TSiP 國產晶片,不改一行業務程式碼。

### 明確不做的範圍

- ❌ SLA 自動化基準測試 Pipeline(由 `amd-ryzen-ai-benchmark` 負責)
- ❌ 晶片驅動、編譯器、底層 Runtime(由各晶片廠商提供)
- ❌ 終端應用程式 UI(由整合商或客戶自行打造)
- ❌ 自建圖形編輯器引擎(必須魔改既有開源、可商用授權的專案)

---

## 三、依賴方向（Clean Architecture）

```
LangChain / AutoGen / OpenAI SDK 使用者
            ↓ 對外相容介面:OpenAI API
┌─────────────────────────────────────────┐
│  Agentic SDK = 邊緣叢集管理協定          │
│  ├─ 編排層:五節點(P/P/R/R/A)路由(必遵守) │
│  ├─ 上下文層:跨節點上下文管理(重點)    │
│  ├─ 觀測層:Multi-Model Dashboard(重點) │
│  └─ 資源層:動態 Offload(延伸,先預留)  │
└─────────────────────────────────────────┘
            ↓ 只信任通過 Model Card 認證的模型
[上游] amd-ryzen-ai-benchmark
            ↓ 產出 SLA 履歷
TSiP 國產晶片 × 模型組合
```

**依賴方向必須由外向內。** 編排層不可直接呼叫晶片驅動;資源層不可依賴特定 Agent 框架;觀測層不可耦合特定 UI 工具。任何違反此方向的設計都是技術債的起點。

---

## 四、PoC 階段的關鍵抉擇

本專案目前在 PoC / 研究導向階段,遵循 YAGNI 原則:

- **最小可驗證路徑優先**:先打通「一個通過認證的模型 → 五節點在叢集內正確路由 → Multi-Model Dashboard 能即時看見叢集狀態」這條最窤路徑
- **抽象只在第二個使用者出現後引入**:不為「未來可能的 N 種晶片 / N 種框架」預先建立通用層
- **動態 Offload 後補**:先採「模型 × 硬體」靜態綁定,但介面留好延伸接口
- **PoC 允許的例外**:可暫時鬆綁潔淨架構,但必須在 `docs/01-architecture/` 中標注「此處違反潔淨架構,待 MVP 後補強」

---

## 五、協作預設規則

完整的設計思維與規範繼承自 `.claude/` submodule（[Connect-AI-TW/.claude](https://github.com/MarkovChenITRI/.claude)）,核心摘要如下,**子專案僅複述邊界,不重新定義**：

1. **依賴方向永遠向內**（Clean Architecture）
2. **變動透過配置傳播**（反硬編碼,所有業務參數命名後納入統一配置）
3. **發行級別代碼**:嚴禁開發日誌式註解;註解只說明邏輯本身,不說「為了 X 而改」
4. **變更管理**:發現錯誤先 Revert 至穩定狀態,再重新修正,不在錯誤邏輯上疊加補丁
5. **負責任驗證**:宣稱完成前必須實際執行驗證,不憑感覺回報
6. **語系**:繁體中文（台灣）,台灣業界慣用語
7. **檔案編輯規範**:所有檔案修改必須透過編輯工具,禁止用 PowerShell / bash 指令直接寫入（會造成中文亂碼）

---

## 六、文件結構約定

本專案的設計文件統一放在 `docs/`,採「原子化文檔」模式:每個 Markdown 檔案邏輯完整且可獨立閱讀。`README.md` 是專案門戶,必須引導讀者於三步內完成啟動;深層細節透過導航連結轉導至 `docs/`。

設計參數的描述必須附量化依據（例:不是 `max-size-buffers=6`,而是「根據推論延遲 200ms 與來源幀率 33ms/幀,計算緩衝深度為 6」）。
