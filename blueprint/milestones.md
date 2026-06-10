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
| M6 | 🟢 第一輪完成 | MVP 差異化三主軸：持久記憶、節點異質部署、Plan 真實規劃能力；10 子項全綠 |
| M7 | 🟢 第二輪完成 | 編輯器 UX 精修：Palette 精簡、面板拖曳調整尺寸、Python 輸出改 Builder 模式、預設 Backend 改 Azure |
| M8 | 🟢 第三輪完成 | 編輯器 UX 收斂：LEFT 主面板貫穿到底、節點 Class 概念與選擇器、Chat 引導按鈕改 BingChat 風格、Gateway 啟動前清埠避免 stale 500 |
| M9 | 🟢 完成 | 多模態使用者輸入：WorkflowState 帶 attachments、兩個 Action backend 生成 OpenAI 標準多模態 content、Gateway /v1/workflow/run 接 attachments、ChatPanel 加附件按鈕 |
| M10 | 🟢 完成 | 圖像 → 檢索查詢橋接：SemanticRetrieve 增 `vision_query` hook、預設 `FoundryVisionQuery` 用 Foundry 圖文模型把附件摘成檢索關鍵字、Retrieve metadata 標註 vision_augmented |
| M11 | 🟢 完成 | 即時串流輸出與 idle-timeout：FoundryClient/Action 走 stream=True + httpx read timeout 取代 wall-clock；新增 `workflow.node.delta` 事件；編輯器逐字渲染 |
| M12 | 🟡 規劃中 | 編輯器上架 GitHub Pages：Vite `base` 子路徑化、Runtime Gateway URL、CORS 白名單、GitHub Actions 部署、無 Gateway 降級提示 |
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

# 3. 啟動 demo(另一個 terminal)
cd demo
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
| M6-1 | 🟢 | Memory Stream 持久化（SQLite，以 workflow 名稱為隔離單位）：跨 run 記憶，Perceive 寫入、Retrieve 語意撈回 | `tests/test_memory_stream.py` 9/9 通過 |
| M6-2 | 🟢 | Retrieve 節點升級：SemanticRetrieve(TF-IDF jaccard 為預設，pluggable Embedder Protocol 可升級 sentence-transformers) + 時近性 + 重要性加權 | `tests/test_retrieve_semantic.py` 5/5 通過；Retrieve 回傳 `source=memory_stream` + 加權分數 |
| M6-3 | 🟢 | `compute_target` YAML 宣告 + UI 視覺化：NodeSpec.compute_target；canvas badge 顯示 `ryzen_ai` / `azure_foundry` / `local_cpu` | NodeSpec 序列化保留 compute_target；NodeBase 顯示 badge |
| M6-4 | 🟢 | UI 節點 badge + 記憶節點視覺區分：執行節點 badge + Memory Stream 獨立側欄指示 | NodePalette 內 Memory Stream 卡片 + node badge CSS |
| M6-5 | 🟢 | Plan 升級為真實規劃節點（SDK 實作）：LLM 輸出 `subtasks: list`，Action 可依序消費 | ReActPlan 解析 `subtasks` 並寫入 metadata + payload |
| M6-6 | 🟢 | Reflect 可選 LLM 驅動：rule-based（現行）或 LLM 反思（Reflexion [R17]），YAML `mode: llm` 切換 | `ReflexionReflect` 節點 + config dispatcher 切換邏輯 |
| M6-7 | 🟢 | Perceive 節點屬性驅動 Chat Panel：屬性面板宣告 welcome_message / options，Chat Panel 即時渲染按鈕 | `tests/test_perceive_options.py` 6/6；ChatPanel 接受 perceiveSpec |
| M6-8 | 🟢 | UI 視覺比例修正：屬性面板加寬至 360px、footer 320px、節點 badge / divider 等微調 | styles.css grid 重設 + 新元件 CSS |
| M6-9 | 🟢 | 屬性面板白盒化：每節點專屬編輯器；Action 可填 endpoint / deployment / api_key / model / temperature；compute_target 共用列 | PropertyPanel 五節點專屬編輯器 + ComputeTargetEditor |
| M6-10 | 🟢 | 匯出雙模式：① 下載 YAML ② 顯示 Python code snippet（含 MemoryStore + Workflow.from_config 完整可執行樣板） | `demo/src/export.ts` + PythonModal |

> **M6-7~M6-10 是「工作流編輯器」的核心定位**：UI 不只是配置工具，是讓使用者理解「這個工作流如何在 Python 端被組裝、執行」的可視化介面。黑盒下拉選單會讓編輯器淪為玩具。
>
> **第一輪實作小註**：M6-2 預設用 TF-IDF jaccard 而非 sentence-transformers，是為了避開 1.5GB torch 依賴；Embedder Protocol 已預留，未來 `pip install sentence-transformers` 即可升級。M6-5 的 subtasks 由 Plan 寫入 payload，Action 端依序消費的迴圈邏輯保留為下一輪細節。

**M6 完成代表**：可向整合商展示「為什麼用 Agentic SDK 而不用 LangGraph / Dify / Coze」— 因為記憶跨對話存活、節點跑在國產晶片上、整條鏈路在瀏覽器內可視可調。

---

## M7 — 編輯器 UX 精修

> **M7 的核心主張**：M6 交付了功能，M7 修正使用習慣落差 — 操作路徑更直覺、面板尺寸可控、Python 輸出對齊 SDK 學習曲線、開發機環境預設移除 AMD NPU 依賴。

| ID | 狀態 | 對外可見成果 | 驗收方式 |
|----|------|-------------|----------|
| M7-1 | 🟢 | **移除 Palette 節點清單**：左側欄不再重複列出五節點；點擊畫布節點直接開屬性面板，操作路徑唯一化 | Palette 側欄無 `palette-list`；PropertyPanel hint 文字確認點擊節點即開啟 |
| M7-2 | 🟢 | **Palette 底部化**：Memory Stream 指示卡 + 輸出按鈕靠底部貫穿；Chat Panel 預設高度縮小至 ≤ 220px | 左側欄 Memory/Output 區塊 `margin-top: auto` 固定底部；Chat Panel 高度目測合理 |
| M7-3 | 🟢 | **面板拖曳調整尺寸**：屬性面板可水平拖曳縮放寬度；底部 Chat Panel 可垂直拖曳縮放高度 | 拖曳 `.resize-v` 分隔線後面板寬度即時更新；拖曳 `.resize-h` 後 Chat Panel 高度即時更新 |
| M7-4 | 🟢 | **Python 輸出改 Builder 模式**：`export.ts` 生成逐節點顯式建構程式碼（`RuleBasedPerceive(...)`、`SemanticRetrieve(...)` 等），不依賴 YAML 字串中介載入 | PythonModal 顯示的代碼包含明確 import 路徑 + `Workflow(perceive=..., retrieve=..., ...)` 建構呼叫，無任何 YAML 字串 |
| M7-5 | 🟢 | **預設 Backend 改 Azure**：`defaultWorkflow.ts` 移除 `ryzen_ai` 預設值，Plan 節點 `compute_target` 改為 `azure_foundry`；開發機環境可直接跑無 NPU 依賴 | `defaultWorkflow.ts` 中所有 `compute_target` 均為 `azure_foundry` 或 `local_cpu`，無 `ryzen_ai` |

**M7 完成代表**：開發機上不裝 AMD NPU Runtime 也能完整跑通 UI demo；整合商在 PythonModal 看到的是可直接 `pip install agentic-sdk` 後執行的 Builder 風格代碼，而非隱藏細節的 YAML 載入片段。

---

## M8 — 編輯器 UX 第三輪收斂

> **M8 的核心主張**：M7 改動有條，但使用者實際體驗仍有四道落差 — 左右版型未真正貫穿、節點看不出語意差異、引導按鈕直接送出剝奪確認權、開發機重啟 npm start 時偶發 Gateway 500。M8 把四件事一次補齊，讓 demo 路徑乾淨可重現。

| ID | 狀態 | 對外可見成果 | 驗收方式 |
|----|------|-------------|----------|
| M8-1 | 🟢 | **LEFT 主面板貫穿到底**：屬性編輯器 + Memory/輸出整併為單一左欄，從頂部到底部不被 Chat 切斷；RIGHT 欄改放 Canvas + Chat | App.tsx 使用 `.left-column / .right-column`；屬性面板上方、Memory/輸出在底部 `border-top` 分隔 |
| M8-2 | 🟢 | **節點 Class 概念**：每節點上方新增 Class 下拉（Plan 三種、Reflect 二種、Action 二種、Perceive/Retrieve 各一種）；節點標題顯示 Class 名稱；切換 Class 自動寫入對應 type + enforceParams | `demo/src/types.ts::NODE_CLASSES`、`detectNodeClass`、`applyNodeClass`；PropertyPanel `ClassEditor`；五節點 `*.tsx` 以 `detectNodeClass(...).label` 渲染 title |
| M8-3 | 🟢 | **Chat 引導按鈕改 BingChat 風格**：點 Perceive options 不再直接送出，改為「填入輸入框」並聚焦；使用者按 Enter 才啟動工作流 | ChatPanel `handleOption` 由 `onSend(opt.value)` 改為 `setInput(opt.label) + inputRef.focus()`；引導列獨立 `.chat-suggestions` 顯示於輸入框上方 |
| M8-4 | 🟢 | **npm start 預清埠**：新增 `prestart` hook，啟動前以 PowerShell 殺掉佔用 8080 的殘留行程，避免 stale Gateway 回 500 | `demo/package.json::scripts.prestart` 使用 `Get-NetTCPConnection -LocalPort 8080 ... Stop-Process` |
| M8-5 | 🟢 | **冗餘下拉統一收斂**：移除 PropertyPanel 內 Plan template、Reflect mode、Action backend 三個下拉（已被 M8-2 的 Class 取代），避免雙頭操作造成狀態不一致 | PropertyPanel `PlanEditor / ReflectEditor / ActionEditor` 不再 import `PLAN_PROMPT_TEMPLATES / REFLECT_MODE_OPTIONS / ACTION_BACKEND_OPTIONS` |

**M8 完成代表**：demo 開場「啟動 → 看見左欄屬性貫穿到底 → 點節點看到 Class → 點引導按鈕看到文字填入 → 自己按 Enter 跑通工作流」全程一氣呵成，無 stale 500、無重複下拉、無視覺切斷。

---

## M9 — 多模態使用者輸入

> **M9 的核心主張**：M8 之前 user 端只能丟純文字，但 Foundry GPT-5.2 與 AMD Gemma3 都原生支援 OpenAI 多模態 `content` 陣列。M9 把這條被 SDK 自己關起來的通道打開，讓 Perceive 提示的「我有足測報告」「拍鞋現況」等選項在 demo 上真的能上傳圖片給 Action 看。

| ID | 狀態 | 對外可見成果 | 驗收方式 |
|----|------|-------------|----------|
| M9-1 | 🟢 | **`Attachment` dataclass + `WorkflowState.attachments`**：新增 `agentic_sdk/workflow/attachments.py`，attachment 帶 `kind`（image/file）、`mime`、`data_url`、可選 `name` | `tests/test_workflow_attachments.py::test_state_carries_attachments` |
| M9-2 | 🟢 | **`Workflow.run` 與 Gateway `/v1/workflow/run` 透 attachments**：API 介面接受 `attachments: list[AttachmentSpec]`，向下傳到 `WorkflowState` | `tests/test_routes_workflow.py::test_run_accepts_attachments` |
| M9-3 | 🟢 | **Foundry / Upstream Action 生成多模態 messages**：偵測 `state.attachments` 非空時，user content 從 `str` 切換為 OpenAI multimodal list `[{type:"text"...},{type:"image_url"...}]`；Gemma3 為單 user message 模板 + 多 image_url part | `tests/test_action_multimodal.py`（兩 backend 各一） |
| M9-4 | 🟢 | **ChatPanel 附件按鈕**：輸入框旁加迴紋針按鈕，可選圖檔；選擇後顯示縮圖預覽，送出時連同 `attachments` 一併 POST 至 `/v1/workflow/run` | UI 手動驗：上傳 PNG 後輸入框出現縮圖；DevTools 觀察 POST body 含 `attachments[0].data_url` |
| M9-5 | 🟢 | **`PerceiveOption.expects_attachment`**：option 可宣告 `"image" \| "file" \| undefined`；ChatPanel 點該 option 時自動聚焦附件按鈕（視覺暗示）；預設鞋店場景的「📏 我有足測報告」與「📷 拍鞋現況比對」標 `expects_attachment: "image"` | `demo/src/types.ts` 含 `expects_attachment`；`defaultParamsFor("perceive")` 兩 option 帶該欄位 |

**M9 完成代表**：使用者可在編輯器點「我有足測報告」→ 上傳 PNG → Action 真的看到那張圖回應，整條鏈不再受限於 string-only user input。

---

## M10 — 圖像 → 檢索查詢橋接

> **M10 的核心主張**：M9 讓 Action 看得到圖，但 Retrieve 依然只用 `state.user_message` 做查詢——客人傳鞋款照卻搜不到對應品項，落差明顯。M10 在 Retrieve 前面插一個可選的 vision 摘要步驟，讓圖片先被 Foundry 圖文模型轉成檢索關鍵字，再餵給 KB / MemoryStore，閉合 Perceive → Retrieve → Action 多模態鏈。

| ID | 狀態 | 對外可見成果 | 驗收方式 |
|----|------|-------------|----------|
| M10-1 | 🟢 | **`VisionQueryBuilder` Protocol**：定義 `__call__(text: str, attachments: list[Attachment]) -> str`；任何能把（文字+圖）摘成查詢字串的元件都符合此契約 | `agentic_sdk/workflow/nodes/retrieve/vision_query.py::VisionQueryBuilder` |
| M10-2 | 🟢 | **預設 `FoundryVisionQuery` 實作**：呼叫 Azure Foundry 圖文 deployment（共用 Settings），以「請用 30 字內描述圖片重點，輸出可直接拿去檢索的關鍵字」的 system prompt 取得 query；失敗時 fallback 回原 `user_message` 不阻斷流程 | `tests/test_vision_query.py::test_foundry_vision_query_returns_keywords`（mock client） |
| M10-3 | 🟢 | **`SemanticRetrieve` 接 `vision_query`**：建構子加 `vision_query: VisionQueryBuilder \| None = None`；當 `state.attachments` 與 `vision_query` 同時存在，用其改寫 query 後再走 KB/Memory 檢索；`metadata` 新增 `vision_augmented: bool` 與 `vision_query_text` | `tests/test_retrieve_semantic.py::test_vision_query_overrides_search_text`（mock VisionQueryBuilder） |
| M10-4 | 🟢 | **編輯器與 export.ts 預留旗標**：Retrieve 編輯器加「啟用圖像摘要」開關（`enable_vision_query: boolean`），export.ts 在開關開啟時於生成 Python 程式碼插入 `vision_query=FoundryVisionQuery()` | `demo/src/panels/AccordionPanel.tsx` RetrieveEditor 新欄位；`demo/src/export.ts` 條件 import 與注入 |

**M10 完成代表**：使用者上傳鞋款照→Retrieve 摘要成「氣墊跑鞋 寬楦 緩衝」→ KB 命中 AirFlex／ComfortWalk → Action 用圖+文一起回應；整條多模態鏈閉合且每一段都有對應 metadata 可被 Dashboard 觀察。

---

## M11 — 即時串流輸出與 idle-timeout（完成）

> **M11 的核心主張**：M10 之前 Action 走 `stream=False` 並以 wall-clock 30 秒砍掉長回覆，使得「需要深度展開的回答」永遠跑不完；同時前端只能等整段回完才顯示，視覺上像當機。M11 把整條 LLM 路徑換成 stream + httpx idle-timeout，並在遙測層新增 `workflow.node.delta` 事件，讓編輯器逐 token 渲染。

| ID | 狀態 | 對外可見成果 | 驗收方式 |
|----|------|-------------|----------|
| M11-1 | 🟢 | **`workflow.node.delta` 事件常數 + TypedDict 欄位**：`EVENT_NODE_DELTA`、`delta_text`、`delta_index` | `agentic_sdk/observability/events.py` 已 export |
| M11-2 | 🟢 | **`FoundryClient.chat_stream()`**：以 `httpx.Timeout(read=idle_timeout_sec)` 控制 chunk 之間的空轉上限；無新 token 達上限才 raise `TimeoutError`，吐 token 期間不受限 | `tests/test_workflow_llm.py` 全綠 |
| M11-3 | 🟢 | **`FoundryCompletionAction` 改 stream**：每收到一片 chunk 即 emit `workflow.node.delta`，並計算 idle gap；錯誤路徑改寫 `state.last_action_error` 回 reflect | `tests/test_action_multimodal.py` 與 `tests/test_multi_backend.py` 5 案在 stream mock 下通過 |
| M11-4 | 🟢 | **Gateway SSE 不把 delta 當 terminal**：`_TERMINAL_EVENTS` 只列 `workflow.fallback`；`workflow.node.delta` 與 `workflow.node.start/finish(with next)` 自由穿過；SSE 硬上限提升為 600 秒 | `agentic_sdk/gateway/routes_workflow.py::_TERMINAL_EVENTS` |
| M11-5 | 🟢 | **編輯器訂閱 delta + 逐字渲染**：`App.tsx` 對 `EVENT_NODE_DELTA` 累加進當前 assistant 訊息；`fetchWorkflowResult` 取得最終 message 後以串流內容優先 | `demo/src/App.tsx` |
| M11-6 | 🟢 | **Gates timeout 改為 hard ceiling 300s**：`GateConfig.timeout_sec` 預設 300，僅作整條工作流的最後保險；不再用來砍 LLM 單次回覆 | `agentic_sdk/workflow/gates.py` + `agentic_sdk/workflow/config.py` 預設 300.0 |

**M11 完成代表**：長回覆只在「真的沒有新 token」時才中止，前端體驗對齊 ChatGPT；測試 154 → 158 案全綠。

---

## M12 — 編輯器上架 GitHub Pages（規劃中）

> **M12 的核心主張**：M11 之前 repo 沒有任何 CI 保護，也沒有零安裝的 demo 入口。M12 分兩條線：(1) 先建立 GitHub Actions CI（pytest + TypeScript 型別檢查），讓每次 push/PR 都自動驗綠；(2) 將 `demo/` 上架到 GitHub Pages（或等效靜態站），讓潛在使用者不需 clone 就能體驗編輯器。完整設計見 [docs/04-observability-dashboard/phase12-github-pages-plan.md](../docs/04-observability-dashboard/phase12-github-pages-plan.md)。

| ID | 狀態 | 對外可見成果 | 驗收方式 |
|----|------|-------------|----------|
| M12-0 | 🟡 規劃中 | **CI 自動化測試**：`.github/workflows/ci.yml` 於 push / PR 觸發；Python 端跑 `uv sync --extra dev + pytest`（全程 mock，不需 Foundry 金鑰）；前端跑 `tsc --noEmit` 驗 TypeScript 無型別錯誤 | Actions 綠燈；repo 首頁顯示 CI badge |
| M12-1 | 🟡 規劃中 | **Vite `base` 子路徑化**：`vite.config.ts` 讀環境變數 `VITE_BASE`，預設 `/`，CI 部署時設為 `/Agentic-SDK/` | 本機 `vite build` 與 CI build 兩者皆能正確產出資源路徑 |
| M12-2 | 🟡 規劃中 | **Runtime Gateway URL 設定**：編輯器 header 加「Gateway URL」欄位（預設 `http://localhost:8080`，存 localStorage）；`runtime/api.ts` 改讀此 URL 拼接 `/v1/workflow/*`；注意預設必須用 `localhost` 而非 `127.0.0.1`（Mixed Content 政策） | UI 改完後 fetch 與 EventSource 都打到指定 URL |
| M12-3 | 🟡 規劃中 | **Gateway CORS 白名單可設定**：`Settings` 新增 `gateway_cors_origins`，FastAPI `CORSMiddleware` 讀此清單；預設只開 `http://localhost:5173`，GH Pages domain 由使用者依需求 append | curl preflight 對 `https://R300-AI.github.io` 回 `Access-Control-Allow-Origin` |
| M12-4 | 🟡 規劃中 | **GitHub Pages 部署 workflow**：`.github/workflows/deploy-pages.yml` 於 main push 時 build `demo/` 並 publish；repo 位於 `R300-AI` org（GitHub Team），private repo Pages 已支援 | Actions 綠燈、`https://R300-AI.github.io/Agentic-SDK/` 可開啟編輯器 |
| M12-5 | 🟡 規劃中 | **「無 Gateway 也能瀏覽」降級提示**：fetch 失敗時顯示引導訊息「請啟動 Gateway 並於上方填入 `http://localhost:8080`」；不阻斷畫布拖曳與 YAML 編輯 | UI 手動驗：未起 Gateway 時點「跑一次」出現引導訊息而非整片紅字 |

**M12-0 完成代表**：每次 commit push 後 Actions 自動跑 158 項 Python 測試 + TypeScript 型別檢查，main branch 有 CI badge 保護，不需手動跑 pytest。
**M12 完整完成代表**：任何人打開 `https://R300-AI.github.io/Agentic-SDK/` 就能體驗編輯器、設計並下載 workflow YAML；若同時在本機啟 Gateway（並在 `.env` 填入自己的 Foundry API Key），亦能直接觸發跑一次與 SSE 動畫。

---


## 不在任何 Milestone 內的事項

明確記錄以避免日後爭議:

- ❌ Production 級認證、IAM、流量配額 — 留到 MVP 後
- ❌ 自訂節點型別擴充機制 — M6 後評估
- ❌ 跨資料中心 / 跨地理區域的上下文同步 — 不在路線圖
- ❌ 動態 Offload 自動策略（M6-3 是靜態宣告，動態調度為後續延伸）
- ❌ 自製圖形編輯器引擎（M5 採 React Flow，不自建）
- ❌ Runner 容器化、Model Card SHA 驗證（改由上游 `api.py` 取代，見 [risk-decisions.md](risk-decisions.md) D1)
