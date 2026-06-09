# M5(Phase 5)圖形編排 UI 設計與實作計畫 [R26][R27]

> 受眾:Phase 5 開發者、整合商窗口、客戶現場
> 目的:把「使用者能拖曳節點、設計屬性、儲存載入、即時跑一次」的視覺化編排 UI 從零交付。本文是**設計與實作計畫**,不是評估;選型結論在 §二已給定。
> 觸發背景:內部使用者已明確要求拖曳介面;[`WorkflowConfig`](../../agentic_sdk/workflow/config.py) (M4-6) 已交付,UI 與 SDK 的契約面已穩定到可動手做的程度。
> 上游連結:[visualization-ui.md §四](visualization-ui.md) Phase 5 對外承諾在此展開。

---

## 一、Phase 5 的對外承諾

完成時,使用者(整合商 / 客戶現場 / 內部進階使用者)應能做到下列**全部**:

1. 在瀏覽器打開 UI,看到一張預設的五節點工作流畫布(Perceive → Plan → Retrieve → Plan → Action → Reflect)
2. **拖曳節點、連線、刪除邊**,即時看到回環是否合法(Reflect → Plan / Action / END)
3. 點選節點打開**屬性面板**,改 Action backend(upstream/foundry)、模型、Retrieve store、三道閘門參數
4. **儲存** → 取得對應的 [`WorkflowConfig`](../../agentic_sdk/workflow/config.py) YAML 檔
5. **載入**任何符合 schema 的 YAML 還原畫布
6. **跑一次**:把當前畫布直接送進 Gateway `/v1/chat/completions`,結果在 UI 內顯示,並可一鍵跳到 Dashboard 觀看五節點亮燈

對外觀感:Agent 平台級,不再是工程風的 Streamlit。

---

## 二、選型結論:Langflow 為主、React Flow 為備案

候選來自 [docs/README §2.8](../README.md):

| 候選 | 性質 | 對 Phase 5 的適配 | 結論 |
|------|------|-------------------|------|
| **Langflow** [R26] | 完整 Agent 編排平台(MIT) | 畫布 / 節點調色盤 / 屬性面板 / 序列化 / 內建執行 全套現成 | **主選** |
| **React Flow** [R27] | 純畫布元件(MIT) | 完全自由,但屬性面板 / 序列化 / 執行整合都要自寫 | **備案**(主選失敗時 fallback) |
| **LangGraph** [R24] | 圖狀態機框架(MIT) | 不是 UI,是 graph 執行引擎,與 [`Workflow.from_config`](../../agentic_sdk/workflow/config.py) 同層 | **不適用為 UI 候選**;可作為內部執行引擎對齊參考 |

n8n 雖知名,但 trigger→action 線性流不支援 Plan ⇄ Retrieve 回環,結構性不符,不列入候選。

### 為什麼選 Langflow

PoC 階段的目的不是造輪子,是讓使用者**最快看到**可拖曳的工作流 UI。Langflow 已提供:

- React Flow 為底層,畫布交互完整
- 節點 / 邊 / 屬性面板的 React 組件可直接重用
- 內建 Python 後端可載入自訂節點類別
- MIT 授權、活躍維護(2025 年 GitHub 30k+ stars)

我們需要做的不是「重寫整個編輯器」,是「對 Langflow 做窄面 fork,把五節點與 [`WorkflowConfig`](../../agentic_sdk/workflow/config.py) 接進去」。

### fork 邊界(關鍵)

為避免上游 rebase 痛苦,fork 限定在以下三個面:

| 面 | Langflow 原物 | 我方覆蓋 |
|----|---------------|----------|
| 節點型別註冊 | `langflow/components/` 通用組件 | 新增 `agentic_sdk/editor/components/` 只註冊五節點 + Action 變體;不改 Langflow 內建組件 |
| 序列化適配 | Langflow 原生 `.flow.json` | 新增 `WorkflowConfigAdapter`,做 `.flow.json` ⇄ `WorkflowConfig` YAML 雙向轉換;不改 Langflow 序列化 |
| 執行整合 | Langflow 內建 runtime | 新增「跑一次」按鈕,不走 Langflow runtime,直接 POST Gateway `/v1/chat/completions`(我方 SDK 已實作完整工作流) |

**上游 Langflow 不修改任何檔案**,只在 monorepo 內以 plugin 形式擴充。Rebase 衝突面收斂到 0。

### 風險與止損

| 風險 | 觸發條件 | 止損動作 |
|------|----------|----------|
| Langflow 節點抽象與五節點難對齊 | M5-1 spike 結束時連預設模板都跑不起來 | 立刻轉 React Flow + 自製屬性面板;沉沒成本 ≤ 5 人天 |
| Langflow 上游大改 API(2.x → 3.x) | 接到上游 breaking change 公告 | 凍結在當前 Langflow 版本,M6 再決定升或自製 |

---

## 三、使用者體驗設計

### 3.1 主畫布

預設載入「五節點預設模板」,使用者一打開就能看到工作流長什麼樣,不需從零拼:

```
[Perceive] ──► [Plan] ──► [Retrieve] ──► [Plan'] ──► [Action] ──► [Reflect] ──► END
                  ▲                                                     │
                  └──────────────── 回環邊(reflect → plan)────────────┘
```

- 節點顏色對應五節點類別:Perceive 紫 / Plan 藍 / Retrieve 橙 / Action 綠 / Reflect 紅
- 回環邊以虛線標示,與正向邊區分
- 邊上可加文字標籤(`retry` / `done` / `escalate`),對應 Reflect 的決定依據

### 3.2 節點調色盤(左側欄)

固定列出 SDK 支援的所有節點型別,使用者拖到畫布即可:

- 五節點基本款:Perceive / Plan / Retrieve / Reflect / Action
- Action 變體:`upstream_completion` / `foundry_completion`
- 自訂節點:「+」按鈕填 Python import path,加入後出現在自訂區

### 3.3 屬性面板(右側欄)

對應 [`NodeSpec.params`](../../agentic_sdk/workflow/config.py),點選節點時打開:

| 節點 | 可調屬性 | UI 元件 |
|------|----------|---------|
| **Action(upstream)** | base_url、model | 文字框 + 下拉(從 Gateway `/v1/models` 動態拉) |
| **Action(foundry)** | deployment、endpoint、api_key | 文字框 + 密碼框(從 `.env` 預填) |
| **Retrieve** | backend(none/active/archived) | radio |
| **Plan** | 推理範式(CoT/ToT/Plan-and-Solve) | 下拉(留延伸,先實作 CoT) |
| **Reflect** | max_retry、reflection_prompt | 數字 + 多行文字 |

**閘門參數(`max_node_hops` / `max_revisit` / `timeout_sec`)** 屬整體工作流,放畫布外的「工作流設定」面板,不掛在單一節點。

### 3.4 儲存 / 載入

| 動作 | 行為 |
|------|------|
| **儲存(Ctrl+S)** | 透過 `WorkflowConfigAdapter` 轉成 [`WorkflowConfig`](../../agentic_sdk/workflow/config.py) YAML,瀏覽器下載 |
| **另存(Ctrl+Shift+S)** | 同上,可改檔名 |
| **載入(Ctrl+O)** | 拖入 YAML 檔或選擇,Adapter 反向轉成畫布節點;schema 不合時跳錯誤對話框並指出哪一行 |
| **匯出 JSON** | 同 YAML,給程式化使用者 |

### 3.5 「跑一次」按鈕(畫布右上角)

這是 Phase 5 與單純編輯器的關鍵分野:

1. 使用者在「測試輸入」面板填一句話
2. 按「跑一次」→ Editor 把當前畫布序列化為 [`WorkflowConfig`](../../agentic_sdk/workflow/config.py),呼叫 Gateway `/v1/chat/completions`(帶 `x-agentic-workflow-config` header)
3. Gateway 用 `Workflow.from_config()` 跑該次工作流,回傳結果與 `x-agentic-metadata`
4. Editor 顯示結果、token 用量、`workflow_id`
5. 旁邊按鈕「在 Dashboard 觀看」→ 開新分頁到 `http://localhost:8501?workflow_id=<id>`,Dashboard 篩出該次工作流的五節點亮燈

**Gateway 需新增的能力**:接受 `x-agentic-workflow-config` header 內含 YAML,以該 config 覆寫預設 workflow。這是 M5-3 的 SDK 端工作。

### 3.6 與 Dashboard 的分工

不重做觀測——Dashboard(M2)已有四個面板。Editor 只負責「設計 + 觸發」,Dashboard 負責「觀看」:

- 同一個 origin、不同路由(`/editor` / `/dashboard`)
- 共用 Gateway 為唯一後端
- `workflow_id` 在兩邊一致,可透過 URL query 跳轉聚焦

---

## 四、交付里程碑

| 里程 | 對外可見成果 | 完成判準 |
|------|--------------|----------|
| **M5-1** Editor 骨架 | Langflow fork 起來,預設五節點模板可顯示、可拖曳;不可儲存、不可跑 | 開啟瀏覽器看到畫布,能改連線 |
| **M5-2** 屬性面板 + 序列化 | 屬性面板對接 [`NodeSpec.params`](../../agentic_sdk/workflow/config.py);儲存/載入 YAML 雙向通 | 同一份 YAML 經「載入 → 儲存」與 pytest 直接 load 結果一致 |
| **M5-3** 跑一次整合 | Gateway 接受 `x-agentic-workflow-config` header;Editor「跑一次」按鈕串通 | 在 Editor 改一個節點屬性,按跑一次,Dashboard 出現對應的五節點亮燈 |
| **M5-4** 使用者體驗驗收 | 整合商客戶不看 README,自己改一個工作流並跑通 | 訪談 ≥ 1 位客戶,完成「拖曳 → 改屬性 → 儲存 → 跑一次」全流程,無口頭協助 |

每個里程結束輸出:15 秒 demo 影片 + 一份對應的 [`WorkflowConfig`](../../agentic_sdk/workflow/config.py) YAML 範例,存到 `docs/quickstart-runs/`。

---

## 五、技術接點清單(給開發者)

開工時最先碰到的接點,集中列在這:

| 接點 | 既有檔案 | 需新增 |
|------|----------|--------|
| WorkflowConfig 雙向轉 Langflow `.flow.json` | [`agentic_sdk/workflow/config.py`](../../agentic_sdk/workflow/config.py) | `agentic_sdk/editor/adapter.py` |
| Langflow 五節點 component 註冊 | — | `agentic_sdk/editor/components/{perceive,plan,retrieve,reflect,action}.py` |
| Gateway 接 workflow config header | [`agentic_sdk/gateway/routes_chat.py`](../../agentic_sdk/gateway/routes_chat.py) | 新增 header 解析 + `Workflow.from_config(...)` 分支 |
| Editor 啟動腳本 | [`scripts/start.ps1`](../../scripts/start.ps1) | 新增 `scripts/start_editor.ps1`,與 Dashboard 同模式 |
| 預設五節點模板 YAML | — | `examples/workflows/default.yaml` |

---

## 六、不在 Phase 5 範圍

- ❌ 工作流版本控制(Git-like 分支、diff)— 留 MVP
- ❌ 多使用者協作即時編輯 — 留 MVP
- ❌ 行動裝置適配 — 留 MVP(Editor 桌面優先)
- ❌ 自製節點型別的程式碼編輯器(改用 Python 檔案外掛)— 留 MVP
- ❌ Action backend 自動推薦(看模型大小選 NPU/Foundry)— 留 Phase 6 動態 Offload
