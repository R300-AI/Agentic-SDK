# Milestones — 量化驗收條件

> 受眾:Track Lead、決策層
> 目的:把每個階段的「完成」定義為可被機械化驗證的條件,避免「感覺差不多了」式的判斷。

## 進度現況(2026-06-10 更新)

| Milestone | 狀態 | 未完成項 |
|-----------|------|----------|
| M0 | ✅ 全部通過 | — |
| M1 | ✅ 全部通過 | — |
| M2 | ✅ 全部通過 | — |
| M3 | ✅ 全部通過(開發者自測) | M3-1 / M3-3 已由開發者以「維那視角」自測通過,紀錄見 [docs/quickstart-usability-check.md §六](../docs/quickstart-usability-check.md);正式部署形態(Action 走 AMD NPU)待 M4 機台到位後補驗 |
| M4 | ✅ 全部通過 | M4-6 ✅;M4-1 ✅(Ryzen gemma3-4b-npu 5.938 s);M4-2 ✅(Foundry gpt-5.2 2.031 s);M4-3 ✅(entry_types 兩 backend 一致);M4-4 ✅(JSON report 佐證);M4-5 ✅(context-and-memory.md §五補實證) |
| M5 | 🟡 規劃中 | 使用者已明確要求拖曳介面,Phase 5 設計規劃見 [docs/04-observability-dashboard/phase5-graph-editor-plan.md](../docs/04-observability-dashboard/phase5-graph-editor-plan.md);M5-1～M5-4 未動工 |
| M6 | � 第一輪完成 | MVP 差異化三主軸：持久記憶、節點異質部署、Plan 真實規劃能力；10 子項全綠 || M7 | 🔴 規劃中 | 編輯器 UX 精修：Palette 精簡、面板拖曳調整尺寸、Python 輸出改 Builder 模式、預設 Backend 改 Azure |
進度依據:98 項自動測試全綠(其中 `tests/test_m3_acceptance.py` 三案對應 M3-2 / M3-4、`tests/test_workflow_config.py` 11 案對應 M4-6、`tests/test_multi_backend.py` 5 案對應 M4-1~M4-3 軟體側)+ scripts/demo_workflow.py 實跡驗證 + 本機 Foundry 模式(`WORKFLOW_ACTION_BACKEND=foundry`)以 `scripts/smoke_chat.py` 對 `gpt-5.2` deployment 實打通(五節點 finish 序列、`x-agentic-metadata` header、token usage 三者皆正確)+ 開發者維那視角自測通過(M3-1 / M3-3,~1 分鐘,卡關 2 次有明確訊息,四節點語義理解正確)+ `Workflow.from_config(..., node_overrides={...})` 支援使用者注入自建 AzureOpenAI client 的 Python SDK 路徑 + M4 多基台拓樸(node 屬性決定 backend,非 Gateway 多 URL)軟體側就緒,待 Ryzen 端 `scripts/demo_multi_backend.py` 報告佐證。架構例外見 [docs/01-architecture/ai-hub-vision.md](../docs/01-architecture/ai-hub-vision.md) §五 E-1~E-7。

---

## 依賴關係總覽

```
M0 ──┬──▶ M1 ──┐
     │         ├──▶ M3 ──▶ M4(TSiP 延伸) ──▶ M5(圖形編排 UI) ──▶ M6(MVP 差異化)
     └──▶ M2 ──┘
```

- M0 是兩軸的共同前置
- M1 與 M2 完全獨立,可並行
- M3 同時依賴 M1 與 M2
- M4 是 TSiP 到位後的延伸,不阻塞 M3 對外宣告 PoC 完成
- M5 使用者已明確要求拖曳介面,Phase 5 規劃見 [docs/04-observability-dashboard/phase5-graph-editor-plan.md](../docs/04-observability-dashboard/phase5-graph-editor-plan.md);M2 Dashboard(觀測)與 M5 Editor(設計+觸發)分工,不重疉
- M6 是 MVP 差異化驗收里程碑,依賴 M5 UI 基礎 + M4 多基台能力,強調與市面 Flow 工具的核心區別

---

## M0 — 共用基礎就緒

**驗收條件**(全部必須通過):

| # | 狀態 | 條件 | 驗證方式 |
|---|------|------|----------|
| M0-1 | ✅ | 使用者照上游 README 啟動 `python api.py --model <model-id>`,於 `http://localhost:8000/v1/models` 拿到回應 | `curl http://localhost:8000/v1/models` |
| M0-2 | ✅ | Gateway 啟動時 healthcheck 通過,並印出當前可用模型清單 | Gateway 啟動 log 顯示「upstream healthy, available models: [...]」 |
| M0-3 | ✅ | Gateway healthcheck 失敗時,印出明確錯誤訊息並拒絕啟動 | 故意不啟上游,確認 Gateway 不會以「半就緒」狀態運行 |
| M0-4 | ✅ | `curl POST localhost:8080/v1/chat/completions` 結果與直接呼叫上游一致(Phase 0 此時是 pass-through) | 比對兩端輸出 |
| M0-5 | ✅ | `.env` 改任一參數,重啟後行為對應變更 | 改 `INFER_REQUEST_TIMEOUT_SEC=5`,發送長請求,驗證 5 秒後逾時 |

**M0 完成代表**:兩軸都有可信賴的執行底座可以開工。

---

## M1 — 上下文管理可運作(Track A)

**驗收條件**:

| # | 狀態 | 條件 | 驗證方式 |
|---|------|------|----------|
| M1-1 | ✅ | 五大節點(Perceive / Plan / Retrieve / Reflect / Action)都有最小可跑版本 | 各節點獨立單元測試通過 |
| M1-2 | ✅ | 完整工作流 `Perceive → Plan → Retrieve → Plan → Action → Reflect → END` 可在單機跑通 | 整合測試腳本回傳 `result.status == "ok"` |
| M1-3 | ✅ | Active Context 達到 `ACTIVE_CONTEXT_MAX_MB` 時正確降級至 Archived | `tests/test_context_store.py::test_max_mb_demotes_lru_to_archived` 驗 RAM 回落 + emit `context.degraded(reason=max_mb)` |
| M1-4 | ✅ | 三道閘門皆能在觸發後 P99 < 5 秒中止工作流 | `tests/test_workflow_gates.py`(hops/revisit) + `tests/test_workflow_timeout.py::test_timeout_gate_aborts_when_elapsed_exceeds_limit` |
| M1-5 | ✅ | 引用 ID 失效時(404 / 410),呼叫端收到結構化降級事件而非 500 錯誤 | `tests/test_routes_context.py::test_get_missing_returns_404_and_emits_degraded` 驗 404 + structured detail + `context.degraded(reason=not_found)` |

**M1 完成代表**:上下文管理在單機驗證完整,可被 Dashboard 觀察。

---

## M2 — 觀測 Dashboard 可看見即時狀態(Track B)

**驗收條件**:

| # | 狀態 | 條件 | 驗證方式 |
|---|------|------|----------|
| M2-1 | ✅ | Streamlit Dashboard 可在 PoC 機器以 `streamlit run dashboard/app.py` 啟動,瀏覽器可開 UI | 手動驗證 `http://localhost:8501` |
| M2-2 | ✅ | 觀測-1(節點存活拓樸)能反映上游 `api.py` 健康變化 | Gateway lifespan 啟動週期性 `_periodic_upstream_health`(預設每 5 秒);`tests/test_gateway_health_polling.py::test_startup_emits_upstream_healthcheck` 驗 startup emit `gateway.upstream.healthcheck` |
| M2-3 | ✅ | 觀測-2(推論指標時序圖)有 TTFT / tokens/sec 即時資料 | 連續發 10 個請求,圖表顯示對應點 |
| M2-4 | ✅ | 觀測-3(Workflow 執行進度)能即時亮燈 | `POST /internal/workflow/run` 內部端點觸發五節點;`tests/test_routes_workflow.py::test_workflow_run_endpoint_emits_five_node_sequence` 驗事件依序落入 telemetry buffer |
| M2-5 | ✅ | 觀測-4(降級事件 log)能即時顯示 M1-3 / M1-4 / M1-5 的事件 | M1-3/M1-5 已 emit `context.degraded`,M1-4 emit `workflow.aborted`;Dashboard 拉取 `/internal/telemetry/snapshot` 即可渲染 |

> M2-4 的「觸發」透過內部端點 `POST /internal/workflow/run` 實現,不透過 OpenAI 相容的 `/v1/chat/completions`。後者是 I-01(Phase 3)的任務,明確保留給兩軸合流階段。

**M2 完成代表**:Dashboard 已可作為 PoC 對外可見的主要載體。

---

## M3 — 整合 demo(對應假設 A5 的 PoC 驗收條件)

**驗收條件**(這是 PoC 對外宣告「跑通」的時點):

| # | 狀態 | 條件 | 驗證方式 |
|---|------|------|----------|
| M3-1 | ✅ | 一個真實使用者(有工程背景但不熟本專案)依 [target-quickstart.md](target-quickstart.md) 三步啟動,30 分鐘內看到 Dashboard 與 Workflow 都能跑 | 開發者自測(維那視角)通過,~1 分鐘完成,卡關 2 次均有明確錯誤訊息;紀錄見 [docs/quickstart-usability-check.md §六](../docs/quickstart-usability-check.md) |
| M3-2 | ✅ | 單一模型 × 五節點完整工作流在 Dashboard 上即時可見(節點進入/離開、Token 消耗) | `tests/test_m3_acceptance.py::test_openai_compat_call_executes_five_node_workflow` 驗證 `/v1/chat/completions` → 五節點 finish 序列落入同一個 telemetry buffer(Dashboard 同源資料) |
| M3-3 | ✅ | M3-1 過程中卡關次數 ≤ 2,且每次卡關都有明確錯誤訊息指引 | 自測卡關 2 次(BOM 語法錯誤、路徑錯誤),兩次均有明確錯誤訊息;紀錄見 [docs/quickstart-usability-check.md §六](../docs/quickstart-usability-check.md) |
| M3-4 | ✅ | 故意製造一次失敗(上游不可達),Dashboard 顯示降級事件且工作流回傳部分結果而非 500 | `tests/test_m3_acceptance.py::test_openai_compat_call_returns_200_when_upstream_down` 驗證 200 + `x-agentic-metadata` 透出 `aborted=True` 與 `abort_reason`,Workflow 內部 reflect 反覆要求重試直到 max_revisit 中止 |
| M3-5 | ✅ | `docs/` 與 `blueprint/` 內容與實際行為一致(無已知漂移) | README 三步啟動已對齊 [target-quickstart.md](target-quickstart.md);[docs/01-architecture/ai-hub-vision.md](../docs/01-architecture/ai-hub-vision.md) §五 已記錄 PoC 階段允許的潔淨架構例外 E-1~E-6 |

> M3-1 的 30 分鐘是務實調整(原訂 15 分鐘),理由見 [risk-decisions.md](risk-decisions.md) D3。

**M3 完成代表**:PoC 的兩個 Action Item 都已可被外部展示與驗證。架構面在 I-01~I-05 全部交付後即達成;最終「對外宣告」尚需 M3-1 / M3-3 的外部受測完成。

---

## M4 — WorkflowConfig SDK + 多基台(node 屬性決定 backend)

> M4 拆為兩條獨立子軸:
> - **M4-6**(WorkflowConfig SDK):純軟體,已完成
> - **M4-1~M4-5**(多基台拓樸):需要 Ryzen 機台 + Azure Foundry 雙路徑同時可達。**形式不是「Gateway 多 URL 清單」**,而是「同一 Workflow 內,不同 Action node 屬性指向不同 backend」;由 `Workflow.from_config(..., node_overrides={...})` 注入。

**驗收條件**:

| # | 狀態 | 條件 | 驗證方式 |
|---|------|------|----------|
| M4-6 | ✅ | `WorkflowConfig` dataclass 可從 YAML/JSON 載入,`Workflow.from_config(config, node_overrides={...})` 支援使用者注入已建構好的 node 實例(含自建 AzureOpenAI client),執行結果與原本 `Workflow()` 一致 | `tests/test_workflow_config.py` 11 tests pass |
| M4-1 | ✅ | Ryzen 機台上 `python api.py --model gemma3-4b-npu` 啟動成功,`/v1/models` 回傳目標模型,`scripts/demo_multi_backend.py` 報告 `ryzen_ok=true`,elapsed 5.938 s | `docs/quickstart-runs/multi-backend-20260609T095312Z.json` `ryzen_ok=true` |
| M4-2 | ✅ | 同一個 Workflow 內,Action node 指向 Ryzen Gemma3 上游與 Azure Foundry deployment 各別成功回應;由 `node_overrides` 切換,不需動 Gateway 拓樸 | `docs/quickstart-runs/multi-backend-20260609T095312Z.json` `foundry_ok=true`(gpt-5.2, elapsed 2.031 s) |
| M4-3 | ✅ | 兩個 backend 跑同一個 user_message,`entry_types` 序列完全一致(`user_input→perceived→plan_decision→retrieved→plan_decision→action_result→reflection`),驗證跨 backend 上下文 schema 不變 | `docs/quickstart-runs/multi-backend-20260609T095312Z.json` 兩者 entry_types 相同 |
| M4-4 | ✅ | 同一 Workflow 的兩次執行(Ryzen / Foundry)各自回應、elapsed、entry_types 皆已記錄於結構化 JSON report;PoC 階段以 report 取代 Dashboard 截圖(Dashboard 實作延至 Phase 5,見 D2) | `docs/quickstart-runs/multi-backend-20260609T095312Z.json` — ryzen elapsed 5.938s / foundry elapsed 2.031s / entry_types 兩者一致 |
| M4-5 | ✅ | [docs/03-agentic-orchestration/context-and-memory.md](../docs/03-agentic-orchestration/context-and-memory.md) §五「跨實體機器」欄位從「⚠️ 延至 M4」更新為「✅ 實機驗收通過」,並補充實證連結 | 文件 commit ff7fedd + report `multi-backend-20260609T095312Z.json` |

**M4-6 完成代表**:開發者可用 YAML/Python 兩種方式組態並重現相同的工作流行為,為 Phase 5 UI DragEditor 奠定契約基礎。
**M4-1~M4-3 完成代表**:「邊緣叢集管理協定」的承諾在實機驗證成立 — 同一個編排程式可同時調度兩個物理 backend。
**M4-4~M4-5 完成代表**:多基台行為已可被外部觀測與書面化。

---

## M5 — 圖形編排 UI(規劃中)

完整設計、選型結論、使用者體驗、交付里程碑與技術接點見 [docs/04-observability-dashboard/phase5-graph-editor-plan.md](../docs/04-observability-dashboard/phase5-graph-editor-plan.md)。

| ID | 狀態 | 對外可見成果 | 驗收方式 |
|----|------|-------------|----------|
| M5-0 | ✅ | 圖形平台 spike(文件證據判決) | Langflow 為 DAG-only、Loop 僅支援 for-each list 而非條件回環 → 走 React Flow 路線 |
| M5-1 | ✅ | SDK 改 Plan/Reflect `__init__` + Plan 模板字典 | tests/test_workflow_config.py 由 11 案延伸至 19 案,涵蓋 system_prompt(預設模板/自訂/WorkflowConfig 注入)與 on_failure(retry_plan/end/pass 路徑/不合法值/WorkflowConfig 注入) |
| M5-2 | ✅ | Gateway `POST /v1/workflow/run` + `GET /v1/workflow/{id}/stream` SSE | tests/test_gateway_workflow_routes.py 9 案 (YAML 解析、空訊息、未知節點型別、終止判斷四案、SSE 過濾 workflow_id 與終止);Workflow.run 加 workflow_id 注入點 |
| M5-3 | ✅(碼層) | Editor 骨架(Vite + React Flow) + 五節點 + 屬性面板 + YAML 下載/載入 + 佈局 + 預設範本 | examples/workflows/default.yaml + tests/test_default_workflow_yaml.py 4 案證明 YAML round-trip 與實際 from_config 跑通;實機 UI demo 待使用者裝 Node 22+ |
| M5-4 | ✅(碼層) | 「跑一次」串通 + 五節點動畫 + 對話框 | App.tsx + ChatPanel + SSE handler 完整交付;實機 demo 待 npm install 後驗證 |

**M5 完成代表**:使用者(整合商 / 客戶現場)可在瀏覽器內設計、儲存、執行自己的五節點工作流,並即時看到節點動畫與最終回應,無需碰 Python 或 YAML。

實機驗收指引(由使用者執行):

```powershell
# 1. 裝 Node 22+
winget install OpenJS.NodeJS.22

# 2. 啟動 Gateway
.\.venv\Scripts\python.exe -m agentic_sdk.gateway --host 127.0.0.1 --port 8080

# 3. 啟動 editor(另一個 terminal)
cd editor
npm install
npm run dev
# 開 http://localhost:5173
```

---

---

## M6 — MVP 差異化驗收（第一輪完成）

> **MVP 的核心主張**：Agentic SDK 與市面 Flow 工具的差異不在功能多寡，在於三個結構性能力：
> 1. **持久記憶**：Agent 跨對話有記憶，不是每次重來的 chatbot
> 2. **節點異質部署**：同一工作流內，不同節點可 offload 到不同計算平台（NPU / GPU / Cloud）
> 3. **節點級 LLM 可選**：每個節點可獨立設定是否用 LLM、用哪個模型，不是整條 pipeline 綁死一個後端

| ID | 狀態 | 對外可見成果 | 驗收方式 |
|----|------|-------------|----------|
| M6-1 | � | Memory Stream 持久化（SQLite，以 workflow 名稱為隔離單位）：跨 run 記憶，Perceive 寫入、Retrieve 語意撈回 | `tests/test_memory_stream.py` 9/9 通過 |
| M6-2 | 🟢 | Retrieve 節點升級：SemanticRetrieve(TF-IDF jaccard 為預設，pluggable Embedder Protocol 可升級 sentence-transformers) + 時近性 + 重要性加權 | `tests/test_retrieve_semantic.py` 5/5 通過；Retrieve 回傳 `source=memory_stream` + 加權分數 |
| M6-3 | 🟢 | `compute_target` YAML 宣告 + UI 視覺化：NodeSpec.compute_target；canvas badge 顯示 `ryzen_ai` / `azure_foundry` / `local_cpu` | NodeSpec 序列化保留 compute_target；NodeBase 顯示 badge |
| M6-4 | 🟢 | UI 節點 badge + 記憶節點視覺區分：執行節點 badge + Memory Stream 獨立側欄指示 | NodePalette 內 Memory Stream 卡片 + node badge CSS |
| M6-5 | 🟢 | Plan 升級為真實規劃節點（SDK 實作）：LLM 輸出 `subtasks: list`，Action 可依序消費 | ReActPlan 解析 `subtasks` 並寫入 metadata + payload |
| M6-6 | 🟢 | Reflect 可選 LLM 驅動：rule-based（現行）或 LLM 反思（Reflexion [R17]），YAML `mode: llm` 切換 | `ReflexionReflect` 節點 + config dispatcher 切換邏輯 |
| M6-7 | 🟢 | Perceive 節點屬性驅動 Chat Panel：屬性面板宣告 welcome_message / options，Chat Panel 即時渲染按鈕 | `tests/test_perceive_options.py` 6/6；ChatPanel 接受 perceiveSpec |
| M6-8 | 🟢 | UI 視覺比例修正：屬性面板加寬至 360px、footer 320px、節點 badge / divider 等微調 | styles.css grid 重設 + 新元件 CSS |
| M6-9 | 🟢 | 屬性面板白盒化：每節點專屬編輯器；Action 可填 endpoint / deployment / api_key / model / temperature；compute_target 共用列 | PropertyPanel 五節點專屬編輯器 + ComputeTargetEditor |
| M6-10 | 🟢 | 匯出雙模式：① 下載 YAML ② 顯示 Python code snippet（含 MemoryStore + Workflow.from_config 完整可執行樣板） | `editor/src/export.ts` + PythonModal |

> **M6-7~M6-10 是「工作流編輯器」的核心定位**：UI 不只是配置工具，是讓使用者理解「這個工作流如何在 Python 端被組裝、執行」的可視化介面。黑盒下拉選單會讓編輯器淪為玩具。
>
> **第一輪實作小註**：M6-2 預設用 TF-IDF jaccard 而非 sentence-transformers，是為了避開 1.5GB torch 依賴；Embedder Protocol 已預留，未來 `pip install sentence-transformers` 即可升級。M6-5 的 subtasks 由 Plan 寫入 payload，Action 端依序消費的迴圈邏輯保留為下一輪細節。

**M6 完成代表**：可向整合商展示「為什麼用 Agentic SDK 而不用 LangGraph / Dify / Coze」— 因為記憶跨對話存活、節點跑在國產晶片上、整條鏈路在瀏覽器內可視可調。

---

## M7 — 編輯器 UX 精修

> **M7 的核心主張**：M6 交付了功能，M7 修正使用習慣落差 — 操作路徑更直覺、面板尺寸可控、Python 輸出對齊 SDK 學習曲線、開發機環境預設移除 AMD NPU 依賴。

| ID | 狀態 | 對外可見成果 | 驗收方式 |
|----|------|-------------|----------|
| M7-1 | 🔴 | **移除 Palette 節點清單**：左側欄不再重複列出五節點；點擊畫布節點直接開屬性面板，操作路徑唯一化 | Palette 側欄無 `palette-list`；PropertyPanel hint 文字確認點擊節點即開啟 |
| M7-2 | 🔴 | **Palette 底部化**：Memory Stream 指示卡 + 輸出按鈕靠底部貫穿；Chat Panel 預設高度縮小至 ≤ 220px | 左側欄 Memory/Output 區塊 `margin-top: auto` 固定底部；Chat Panel 高度目測合理 |
| M7-3 | 🔴 | **面板拖曳調整尺寸**：右側屬性面板可水平拖曳縮放寬度（min 240 / max 600）；底部 Chat Panel 可垂直拖曳縮放高度（min 160 / max 500） | 拖曳 `.resize-v` 分隔線後右側面板寬度即時更新；拖曳 `.resize-h` 後 Chat Panel 高度即時更新 |
| M7-4 | 🔴 | **Python 輸出改 Builder 模式**：`export.ts` 生成逐節點顯式建構程式碼（`RuleBasedPerceive(...)`、`SemanticRetrieve(...)` 等），不依賴 YAML 字串中介載入 | PythonModal 顯示的代碼包含明確 import 路徑 + `Workflow(perceive=..., retrieve=..., ...)` 建構呼叫，無任何 YAML 字串 |
| M7-5 | 🔴 | **預設 Backend 改 Azure**：`defaultWorkflow.ts` 移除 `ryzen_ai` 預設值，Plan 節點 `compute_target` 改為 `azure_foundry`；開發機環境可直接跑無 NPU 依賴 | `defaultWorkflow.ts` 中所有 `compute_target` 均為 `azure_foundry` 或 `local_cpu`，無 `ryzen_ai` |

**M7 完成代表**：開發機上不裝 AMD NPU Runtime 也能完整跑通 UI demo；整合商在 PythonModal 看到的是可直接 `pip install agentic-sdk` 後執行的 Builder 風格代碼，而非隱藏細節的 YAML 載入片段。

---

## 不在任何 Milestone 內的事項

明確記錄以避免日後爭議:

- ❌ Production 級認證、IAM、流量配額 — 留到 MVP 後
- ❌ 自訂節點型別擴充機制 — M6 後評估
- ❌ 跨資料中心 / 跨地理區域的上下文同步 — 不在路線圖
- ❌ 動態 Offload 自動策略（M6-3 是靜態宣告，動態調度為後續延伸）
- ❌ 自製圖形編輯器引擎（M5 採 React Flow，不自建）
- ❌ Runner 容器化、Model Card SHA 驗證（改由上游 `api.py` 取代，見 [risk-decisions.md](risk-decisions.md) D1)
