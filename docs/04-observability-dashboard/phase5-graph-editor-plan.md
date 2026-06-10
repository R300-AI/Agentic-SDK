# M5(Phase 5)圖形編排 UI 設計與實作計畫 [R26][R27]

> 受眾:Phase 5 開發者
> 目的:把「使用者能拖曳節點、設計屬性、儲存載入、即時跑一次」的視覺化編排 UI 從零交付。本文是**實作計畫**,所有設計決策已封閉,不是評估骨架。
> 觸發背景:內部使用者已明確要求拖曳介面;[`WorkflowConfig`](../../agentic_sdk/workflow/config.py) (M4-6) 已交付,UI 與 SDK 的契約面已穩定。
> 上游連結:[visualization-ui.md §四](visualization-ui.md) Phase 5 對外承諾在此展開。

---

## 一、第一版對外承諾(最小能玩)

完成時,使用者應能在瀏覽器內做到下列**全部**:

1. 看到預設五節點工作流畫布(Perceive → Plan → Retrieve/Action → Reflect → Plan/END)
2. **拖曳節點、改連線、刪邊**;畫布即時擋掉非法連線(例:Perceive 不可直接連 Action)
3. 點選節點打開**屬性面板**,改三件事:Plan system_prompt(下拉模板 + 自訂)、Reflect on_failure、Action backend
4. **下載 YAML** / **載入 YAML**;檔案完全存使用者本機,Gateway 不存
5. 填一句話按「跑一次」→ **五節點即時亮燈動畫**(SSE 推送) + **ChatGPT 樣對話框輸出最終回應**

對外觀感:Agent 平台級。

### 第一版**不做**(留 MVP)

- ❌ 工具調用(function calling / MCP)
- ❌ 多輪對話與 session 狀態
- ❌ 自訂節點 Python import(RCE 風險,只允許內建五節點)
- ❌ 工作流版本控制、團隊共享、雲端儲存
- ❌ Action backend 自動推薦、Plan 多輪 Thought→Action 迴圈

---

## 二、選型結論:React Flow(M5-0 spike 已判決)

候選來自 [docs/README §2.8](../README.md):

| 候選 | 性質 | 結論 |
|------|------|------|
| **Langflow** [R26] | 完整 Agent 編排平台(MIT) | **淘汰**(M5-0 以文件證據 fail) |
| **React Flow** [R27] | 純畫布元件(MIT) | **主選** |
| **LangGraph** [R24] | 圖狀態機框架(MIT) | 不適用為 UI(它是執行引擎,與 [`Workflow`](../../agentic_sdk/workflow/config.py) 同層) |
| n8n | trigger→action 線性流 | 結構性不符(無原生回環),不列入候選 |

### M5-0 判決依據

[Langflow 官方文件](https://docs.langflow.org/concepts-flows) 明訂:

> When a flow runs, Langflow builds a **Directed Acyclic Graph (DAG)** object from the nodes (components) and edges (connections).

另見 [Loop component 文件](https://docs.langflow.org/loop):

> **The If-Else component isn't compatible with the Loop component.** If you need conditional loop events, redesign your flow to process conditions before the loop.

兩點合組代表:Langflow 本質是 DAG,唯一的 `Loop` 組件是「for-each list item」迭代器(需要輸入是一個列表),**不是「條件決定回不回去」的控制流回環**。我們的 Reflect → Plan 隸屬後者:Reflect 看 `state.last_action_error` 是否為空 → 決定回 Plan 重試或 END。

Langflow 的 Agent 組件雖有內建 ReAct loop,但那是 Agent **節點內部**的黑盒回環,**不是畫布層級可見的邊**。這與我們「五節點各自獨立、回環在畫布上可見並由使用者調整」的抽象根本不同。即使 fork Langflow,要把 DAG 核心改為支援 cyclic graph 屬於「深改架構」,遠超出「窗面 fork」的成本上限。

**結論:不裝 Langflow、不進行手動 spike(文件證據已足夠),直接走 React Flow 路線。**

### React Flow 路線架構

```
browser
  ├─ React + Vite 單頁應用
  ├─ React Flow:畫布、節點、邊、拖曳及連線驗證
  ├─ shadcn/ui(MIT):屬性面板、對話框、表單元件
  ├─ js-yaml(MIT):YAML 雙向序列化
  ├─ EventSource(瀏覽器內建):SSE 接動畫事件
  └─ 由 Vite dev server 或靜態打包使用
```

**布局位置**:`editor/` (與現有 `dashboard/` 同層的前端專用目錄)。同一套 SDK 兩個前端共存。

**五節點型別**直接在 [`editor/src/nodes/`](../../editor/src/nodes/) 以 React component 實作,與 SDK 端 [`agentic_sdk/workflow/nodes/`](../../agentic_sdk/workflow/nodes/) 一一對應。UI 屬性 ⇄ `NodeSpec.params` 的轉換在 [`editor/src/adapter.ts`](../../editor/src/adapter.ts) 中心化。

---

## 三、節點 × 屬性 × SDK 配套(最小可實施對應表)

### 3.1 邊的合法性(畫布拖曳規則)

```
Perceive ─► Plan            (固定;Perceive 唯一出口)
Plan     ─► Retrieve | Action  (使用者可選但實際 next_node 由 LLM 決定)
Retrieve ─► Plan            (固定)
Action   ─► Reflect         (固定)
Reflect  ─► Plan | END      (使用者可調 on_failure 屬性)
```

UI 拖曳時即時擋下不在白名單的連線,並 tooltip 解釋原因。

### 3.2 節點屬性面板與 SDK 改動

| 節點 | UI 屬性 | SDK 現況 | M5-1 配套改動 |
|------|---------|----------|---------------|
| **Perceive** | 唯讀標示「rule_based(無 LLM)」 | [`RuleBasedPerceive`](../../agentic_sdk/workflow/nodes/perceive/rule_based.py) 無 `__init__` 參數 | — |
| **Plan** | `system_prompt`:下拉模板(`react` / `cot` / `plan_and_solve`)+ 自訂多行 | [`ReActPlan(foundry_client=None)`](../../agentic_sdk/workflow/nodes/plan/react.py) `_SYSTEM_PROMPT` 寫死 | `ReActPlan.__init__(system_prompt: str \| None = None)`;新增 `_SYSTEM_PROMPT_TEMPLATES: dict[str, str]` |
| **Retrieve** | `backend` 下拉(僅 `stub`)、`corpus` 多行 JSON | [`StubRetrieve(corpus=None)`](../../agentic_sdk/workflow/nodes/retrieve/stub.py) 已支援 corpus | — |
| **Reflect** | `on_failure` 下拉(`retry_plan` / `end`) | [`RuleBasedReflect`](../../agentic_sdk/workflow/nodes/reflect/rule_based.py) 無 `__init__`,行為寫死 | `RuleBasedReflect.__init__(on_failure: str = "retry_plan")` |
| **Action** | `backend` 下拉(`upstream` / `foundry`)+ 對應屬性(model、base_url / deployment) | [`UpstreamCompletionAction`](../../agentic_sdk/workflow/nodes/action/upstream_completion.py) 與 [`FoundryCompletionAction`](../../agentic_sdk/workflow/nodes/action/foundry_completion.py) 是不同 class | 不改 SDK。UI adapter 在 [`editor/src/adapter.ts`](../../editor/src/adapter.ts) 把 backend 下拉值映射到 [`NodeSpec.type`](../../agentic_sdk/workflow/config.py)(`upstream_completion` / `foundry_completion`),不動 [`_build_node_from_spec`](../../agentic_sdk/workflow/config.py) |
| **全域 Gates** | `max_node_hops` / `max_revisit` / `timeout_sec` 數字框 | [`GateConfig`](../../agentic_sdk/workflow/config.py) 已支援 | — |

### 3.3 Plan system_prompt 模板(M5-1 新增到 SDK)

```python
_SYSTEM_PROMPT_TEMPLATES = {
    "react":   "...(目前 _SYSTEM_PROMPT 內容,作為預設)",
    "cot":     "PLAN. 採用 Chain-of-Thought 推理...",
    "plan_and_solve": "PLAN. 先列出子任務,再決定下一節點...",
}
```

UI 下拉顯示三選一,選後填入文字框讓使用者再改。儲存 YAML 時只存最終文字到 `NodeSpec.params["system_prompt"]`,不存模板名(避免日後改模板使舊 YAML 行為飄移)。

---

## 四、儲存與傳輸(stateless 設計)

### 4.1 為什麼是 stateless

對應 Phase 5 範圍「本機開發者工具」:工作流檔案在使用者本機,Gateway 不存任何使用者 workflow。理由:

- 本機工具就該由本機儲存負責
- 無 multi-user / auth / 同步問題
- Gateway 重啟、換機器,不影響使用者工作流

### 4.2 儲存 / 載入動作

| 動作 | 行為 |
|------|------|
| **下載(Ctrl+S)** | `WorkflowConfigAdapter` 轉成 YAML → 瀏覽器 `Blob` + `<a download>` |
| **載入(Ctrl+O)** | 拖入 YAML 或選擇 → Adapter 反向轉成畫布;schema 不合時跳對話框指出行號 |
| **匯出 JSON** | 同 YAML,給程式化使用者 |

### 4.3 「跑一次」傳輸:`POST /v1/workflow/run`

Body schema(M5-3 在 [`agentic_sdk/gateway/routes_chat.py`](../../agentic_sdk/gateway/routes_chat.py) 同層新增 `routes_workflow.py`):

```json
{
  "workflow_yaml": "<整包 YAML 字串>",
  "user_message": "幫我查 2024Q4 銷售報表",
  "model": "gemma3-4b-npu"
}
```

回應:
```json
{
  "workflow_id": "wf-abc123",
  "stream_url": "/v1/workflow/wf-abc123/stream"
}
```

**為什麼不複用 `/v1/chat/completions`**:
- OpenAI 端點要保持規格相容(LangChain / AutoGen 不會懂 workflow_yaml)
- workflow YAML 可能上 KB,HTTP header 塞不下
- 端點分離才能讓動畫 SSE 自然掛在 `/v1/workflow/{id}/stream`

### 4.4 動畫資料來源:SSE

**`GET /v1/workflow/{workflow_id}/stream`**(M5-3 新增):

- 內部讀 telemetry ring buffer,過濾 `workflow_id == path 參數` 的事件
- 推送格式對齊現有 [`EVENT_NODE_START`](../../agentic_sdk/observability/events.py) / `EVENT_NODE_FINISH`
- 收到 `workflow.aborted` / `workflow.finish`(最後一個 node finish 且 `next_node = None`)後關閉連線

**為什麼選 SSE 而非 polling**:
- 連線中斷 → `EventSource.onerror` 立刻觸發 → 前端不會「轉圈而後端已死」
- 後端主動推送,不會錯過事件
- 比 WebSocket 簡單(單向就夠)

---

## 五、互動體驗(對話框 + 動畫)

### 5.1 畫面布局

```
┌─────────────────────────────────────────────────────────────┐
│  左:節點調色盤(5 種,固定)                                  │
├─────────────────────┬───────────────────────────────────────┤
│                     │                                       │
│  畫布(節點亮燈動畫) │  右:屬性面板(點選節點時開啟)        │
│                     │                                       │
├─────────────────────┴───────────────────────────────────────┤
│  下:對話框(類 OpenWebUI),輸入框 + 訊息流                  │
└─────────────────────────────────────────────────────────────┘
```

### 5.2 節點動畫狀態機

每個節點四種視覺狀態,由 SSE 事件驅動:

| 狀態 | 觸發事件 | 視覺 |
|------|----------|------|
| `idle` | 預設 | 灰色描邊 |
| `running` | `workflow.node.start` 對應節點 | 描邊呼吸燈動畫(CSS keyframe) |
| `ok` | `workflow.node.finish` 且 `workflow_status="ok"` | 綠色實心 |
| `fail` | `workflow.node.finish` 且 `workflow_status="fallback"/"aborted"` | 紅色實心 + 抖動動畫 |

每次新「跑一次」開始,所有節點重置為 `idle`。

### 5.3 對話框(類 OpenWebUI)

- 輸入框置於畫布下方,送出 = 觸發「跑一次」
- 訊息流:user message → 「執行中...」placeholder → 替換為 assistant 最終回應
- 訊息旁 metadata badge:模型名 / token 用量 / elapsed
- **不做**:歷史訊息保留(每次跑一次都是新 session;多輪對話留 MVP)

### 5.4 與 Dashboard(M2)的分工

| 能力 | 由誰 |
|------|------|
| 設計 + 觸發 + 對話框 + 動畫 | **Editor**(Phase 5) |
| 觀測(歷史節點、降級事件、推論指標) | Dashboard(M2 已交付) |

Editor 內附「在 Dashboard 觀看完整 trace」按鈕,跳到 `http://localhost:8501?workflow_id=<id>`(Dashboard M2 需新增 URL query 過濾,**列為 M5-4 配套小改動**)。

---

## 六、交付里程碑

| 里程 | 內容 | 完成判準 | 上限 |
|------|------|----------|------|
| **M5-0** | 圖形平台 spike(文件證據判決) | ✅ 已完成:Langflow 為 DAG-only,不符需求 → 走 React Flow | 已完成 |
| **M5-1** | SDK 改 Plan/Reflect 兩節點 `__init__` + Plan 模板字典 | `tests/test_workflow_config.py` 延伸到 19 案,覆蓋 system_prompt(預設模板 / 自訂 / WorkflowConfig 注入)與 on_failure(retry_plan / end / pass 路徑 / 不合法值 / WorkflowConfig 注入) | 1 天 |
| **M5-2** | Gateway 新 `POST /v1/workflow/run` + `GET /v1/workflow/{id}/stream` SSE | `curl` 灌 YAML 跑通;改 Plan prompt 真的影響回應;SSE 收到完整事件序列 | 1.5 天 |
| **M5-3** | Editor 骨架(Vite + React Flow + shadcn/ui)+ 五節點 + 屬性面板 + YAML 下載/載入 | 同一份 YAML 經「載入→下載」與 pytest load 結果一致 | 5 天 |
| **M5-4** | 「跑一次」串通 + 五節點動畫 + 對話框 + Dashboard 跳轉 | 端到端:改 Action backend → 送訊息 → 動畫 → 看到回應;Dashboard 跳轉 URL 正確 | 1.5 天 |

每個里程結束輸出:1 份對應的 YAML 範例 + 1 份簡短 demo 紀錄,放 `docs/quickstart-runs/`。

---

## 七、技術接點清單

| 接點 | 既有檔案 | 需新增 |
|------|----------|--------|
| Plan 模板字典 + system_prompt 參數 | [`agentic_sdk/workflow/nodes/plan/react.py`](../../agentic_sdk/workflow/nodes/plan/react.py) | 同檔擴充 |
| Reflect on_failure 參數 | [`agentic_sdk/workflow/nodes/reflect/rule_based.py`](../../agentic_sdk/workflow/nodes/reflect/rule_based.py) | 同檔擴充 |
| Action backend 下拉 ⇄ NodeSpec.type 映射 | — | 在 `editor/src/adapter.ts` 集中化,SDK 不動 |
| `POST /v1/workflow/run` + SSE | [`agentic_sdk/gateway/app.py`](../../agentic_sdk/gateway/app.py) router 註冊 | 新增 `agentic_sdk/gateway/routes_workflow.py` |
| Editor 前端專案(Vite + React + React Flow + shadcn/ui) | — | 新增 `editor/` 目錄作為前端 monorepo 兩口 |
| `WorkflowConfig` ⇄ React Flow 畫布 JSON adapter | — | 新增 `editor/src/adapter.ts` |
| Editor 啟動腳本 | [`scripts/start.ps1`](../../scripts/start.ps1) | 新增 `scripts/start_editor.ps1`(跑 `npm run dev`) |
| 預設五節點模板 YAML | — | 新增 `examples/workflows/default.yaml` |
| Dashboard 接 `?workflow_id=` URL 過濾 | [`dashboard/app.py`](../../dashboard/app.py) | 同檔擴充 |
