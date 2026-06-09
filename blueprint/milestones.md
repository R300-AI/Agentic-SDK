# Milestones — 量化驗收條件

> 受眾:Track Lead、決策層
> 目的:把每個階段的「完成」定義為可被機械化驗證的條件,避免「感覺差不多了」式的判斷。

## 進度現況(2026-06-09 更新)

| Milestone | 狀態 | 未完成項 |
|-----------|------|----------|
| M0 | ✅ 全部通過 | — |
| M1 | ✅ 全部通過 | — |
| M2 | ✅ 全部通過 | — |
| M3 | ✅ 全部通過(開發者自測) | M3-1 / M3-3 已由開發者以「維那視角」自測通過,紀錄見 [docs/quickstart-usability-check.md §六](../docs/quickstart-usability-check.md);正式部署形態(Action 走 AMD NPU)待 M4 機台到位後補驗 |
| M4 | ✅ 全部通過 | M4-6 ✅;M4-1 ✅(Ryzen gemma3-4b-npu 5.938 s);M4-2 ✅(Foundry gpt-5.2 2.031 s);M4-3 ✅(entry_types 兩 backend 一致);M4-4 ✅(JSON report 佐證);M4-5 ✅(context-and-memory.md §五補實證) |
| M5 | 🟡 規劃中 | 使用者已明確要求拖曳介面,Phase 5 設計規劃見 [docs/04-observability-dashboard/phase5-graph-editor-plan.md](../docs/04-observability-dashboard/phase5-graph-editor-plan.md);M5-1～M5-4 未動工 |

進度依據:98 項自動測試全綠(其中 `tests/test_m3_acceptance.py` 三案對應 M3-2 / M3-4、`tests/test_workflow_config.py` 11 案對應 M4-6、`tests/test_multi_backend.py` 5 案對應 M4-1~M4-3 軟體側)+ scripts/demo_workflow.py 實跡驗證 + 本機 Foundry 模式(`WORKFLOW_ACTION_BACKEND=foundry`)以 `scripts/smoke_chat.py` 對 `gpt-5.2` deployment 實打通(五節點 finish 序列、`x-agentic-metadata` header、token usage 三者皆正確)+ 開發者維那視角自測通過(M3-1 / M3-3,~1 分鐘,卡關 2 次有明確訊息,四節點語義理解正確)+ `Workflow.from_config(..., node_overrides={...})` 支援使用者注入自建 AzureOpenAI client 的 Python SDK 路徑 + M4 多基台拓樸(node 屬性決定 backend,非 Gateway 多 URL)軟體側就緒,待 Ryzen 端 `scripts/demo_multi_backend.py` 報告佐證。架構例外見 [docs/01-architecture/ai-hub-vision.md](../docs/01-architecture/ai-hub-vision.md) §五 E-1~E-7。

---

## 依賴關係總覽

```
M0 ──┬──▶ M1 ──┐
     │         ├──▶ M3 ──▶ M4(TSiP 延伸) ──▶ M5(圖形編排 UI,規劃中)
     └──▶ M2 ──┘
```

- M0 是兩軸的共同前置
- M1 與 M2 完全獨立,可並行
- M3 同時依賴 M1 與 M2
- M4 是 TSiP 到位後的延伸,不阻塞 M3 對外宣告 PoC 完成
- M5 使用者已明確要求拖曳介面,Phase 5 規劃見 [docs/04-observability-dashboard/phase5-graph-editor-plan.md](../docs/04-observability-dashboard/phase5-graph-editor-plan.md);M2 Dashboard(觀測)與 M5 Editor(設計+觸發)分工,不重疉

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
| M5-1 | ⬜ | SDK 改 Plan/Reflect `__init__` + Plan 模板字典 + WorkflowConfig Action backend dispatch | tests/test_workflow_config.py 延伸覆蓋 system_prompt / on_failure / Action backend 切換 |
| M5-2 | ⬜ | Gateway `POST /v1/workflow/run` + `GET /v1/workflow/{id}/stream` SSE | curl 灌 YAML 跑通;改 Plan prompt 影響回應;SSE 收完整事件序列 |
| M5-3 | ⬜ | Editor 骨架(Vite + React Flow + shadcn/ui) + 五節點 + 屬性面板 + YAML 下載/載入 | 同一份 YAML 經「載入→下載」與 pytest load 結果一致 |
| M5-4 | ⬜ | 「跑一次」串通 + 五節點動畫 + 對話框 + Dashboard 跳轉 | 改 Action backend → 送訊息 → 動畫 → 看到回應;Dashboard ?workflow_id 跳轉正確 |

**M5 完成代表**:使用者(整合商 / 客戶現場)可在瀏覽器內設計、儲存、執行自己的五節點工作流,並即時看到節點動畫與最終回應,無需碰 Python 或 YAML。

---

## 不在任何 Milestone 內的事項

明確記錄以避免日後爭議:

- ❌ Production 級認證、IAM、流量配額 — 留到 MVP
- ❌ 自訂節點型別擴充機制 — 留到 MVP
- ❌ 跨資料中心 / 跨地理區域的上下文同步 — 不在路線圖
- ❌ 動態 Offload(Phase 4 之後評估)
- ❌ 自製圖形編排 UI(M5 採 fork Langflow,見 [phase5-graph-editor-plan.md §二](../docs/04-observability-dashboard/phase5-graph-editor-plan.md))
- ❌ Runner 容器化、Model Card SHA 驗證(改由上游 `api.py` 取代,見 [risk-decisions.md](risk-decisions.md) D1)
