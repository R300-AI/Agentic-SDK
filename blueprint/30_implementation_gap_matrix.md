# Implementation Gap Matrix

## 目的

這份文件將現有藍圖要求，對照到目前 repo 中已存在的 SDK、Gateway 與 Playground 實作，明確標示：

1. 已具備
2. Host / Frontend 可實作
3. Gateway 需補
4. SDK 需補

它的用途不是重新設計產品，而是避免後續 implementation 時，設計、前端、後端各自猜測「這功能現在是不是已經有」。

## 判定標準

### 已具備

目前 repo 中已有可直接支撐藍圖要求的能力或契約。

### Host / Frontend 可實作

現有 SDK / Gateway 不阻擋，但需要在 Playground Host、Flask route、模板或前端層完成。

### Gateway 需補

目前 Gateway 對前端暴露的契約不足，需新增 API 或 response payload。

### SDK 需補

目前 `agentic_sdk` 模組本身的行為或資料結構還不足以支撐藍圖能力。

## Gap Matrix

| 藍圖能力 | 目前狀態 | 主要依據 | 差距說明 | 建議處理 |
| --- | --- | --- | --- | --- |
| 建立者走 Entry / Builder / Runner，直接使用者只看 Runner | Host / Frontend 可實作 | `blueprint/01_product_charter.md`, `blueprint/02_roles_modes_permissions.md`, `agentic_sdk/gateway/app.py` | 這是產品路由與模板責任，不是 SDK 限制 | 在新 Host / Flask App 落實 route、session 與 template 分流 |
| Builder 採 Windows OOBE 式單一步驟主卡 | Host / Frontend 可實作 | `blueprint/07_page_builder.md`, `playground/src/App.tsx` | 現有 React Flow playground 仍是圖形編排器，與新 Builder 相反 | 新建 Builder 頁，不在既有 React Flow 編輯器上硬改 |
| Builder 以任務 archetype 切入，而非直接暴露模組術語 | Host / Frontend 可實作 | `blueprint/07_page_builder.md`, `blueprint/24_builder_persona_modes.md`, `agentic_sdk/workflow/config.py` | 模組與參數已存在，但前台語言需要重做 | 在 Builder UI 層做人話映射與模板卡 |
| Builder 單一步驟聚焦、右側摘要退為輔助層 | Host / Frontend 可實作 | `blueprint/07_page_builder.md`, `blueprint/29_visual_art_consistency_spec.md` | 現有 UI 沒有此版面 | 直接做新 wireframe 與模板頁 |
| Runner 為唯一落地任務頁 | Host / Frontend 可實作 | `blueprint/08_page_runner.md` | 現有 `ChatPanel` 仍偏 playground / debug 視角 | 新建 direct-use Runner 模板與 preview 視角 |
| 每個 Agent 必須有單一主輸入方式 | Host / Frontend 可實作 | `blueprint/08_page_runner.md`, `blueprint/10_component_system.md`, `agentic_sdk/workflow/modules/perceive/*` | SDK 不阻擋，但目前沒有自動推定與前台容器規則 | Host 依 input contract 推定 `primary_input_kind` |
| 每個 Agent 必須有單一主結果容器 | Host / Frontend 可實作 | `blueprint/08_page_runner.md`, `blueprint/10_component_system.md`, `agentic_sdk/workflow/modules/action/*` | 現有 Gateway 只穩定回 `final_message`，不保證豐富結果容器 | 先在前端依 Action 類型推定；高階情況需補 Gateway/SDK 契約 |
| `chat_first / form_first / result_first` 內部模板推定 | Host / Frontend 可實作 | `blueprint/25_runner_layout_variants.md`, `blueprint/17_frontend_js_architecture.md` | 模板邏輯可由 host/前端推定，但目前沒有現成推定模組 | 新增 host-side scene inference 或 frontend mapper |
| 推薦型 Agent 的 Recommendation Card | Host / Frontend 可實作 | `blueprint/10_component_system.md`, `blueprint/25_runner_layout_variants.md` | 需前端做結果卡，但不一定要 SDK 改動 | 以現有結果與額外 metadata 先做 MVP 版卡片 |
| 回覆助手型 Agent 的 Reply Draft Card | Host / Frontend 可實作 | `blueprint/10_component_system.md`, `blueprint/25_runner_layout_variants.md` | 主要是結果容器設計 | 用 `final_message` 先承載，後續再加更細 response schema |
| `查看依據` 微互動 | Gateway 需補 | `blueprint/26_trust_adoption_layer.md`, `agentic_sdk/gateway/routes_chat.py`, `agentic_sdk/gateway/routes_workflow.py` | 目前 chat endpoint 主要回 `final_message`; evidence schema 不穩定 | 為 Runner 提供一致 evidence payload 或以 workflow result endpoint 補充 |
| 高風險任務的可採用等級 | Host / Frontend 可實作 | `blueprint/26_trust_adoption_layer.md`, `blueprint/08_page_runner.md` | 藍圖已降成可選；不需 SDK 必須支援 | 先做前端可選提示；若未來需要自動判定再補契約 |
| `StructuredAction` 真正結構化輸出 | SDK 需補 | `agentic_sdk/workflow/modules/action/structured.py` | 目前只是 `GenerativeAction` 子類，沒有實際 structure contract | 補 `final_data` 與 response schema 的穩定輸出路徑 |
| `TextImagePerceive` 真正多模態理解 | SDK 需補 | `agentic_sdk/workflow/modules/perceive/text_image.py` | 目前只是 `TextPerceive` 子類，沒有專屬圖像理解行為 | 補多模態輸入處理與感知輸出邏輯 |
| Gateway 對前端提供一致的 structured result payload | Gateway 需補 | `agentic_sdk/gateway/routes_chat.py`, `agentic_sdk/gateway/routes_workflow.py` | 目前前端很難穩定拿到 `final_data` / result kind | 補 Runner 專用 endpoint 或擴充 workflow result payload |
| Gateway 對前端提供 result adoption state / trust hints | Gateway 需補 | `blueprint/26_trust_adoption_layer.md`, `agentic_sdk/gateway/routes_chat.py` | 現有後端沒有這類欄位 | PoC 可先在前端依 archetype 顯示；若要自動判定再補 API |
| `scene_profile` / `primary_input_kind` / `primary_result_kind` 推定 | Host / Frontend 可實作 | `blueprint/17_frontend_js_architecture.md`, `blueprint/13_python_source_of_truth_spec.md` | 現有 repo 沒有獨立推定器 | 在 Host service 或 frontend mapper 實作 |
| Python source 為唯一正式保存物 | 已具備 | `blueprint/13_python_source_of_truth_spec.md`, `agentic_sdk/workflow/config.py`, repo architectural direction | SDK 仍可處理 YAML/JSON config，但平台可以選 code-first | 產品層維持只保存 `python_source` |
| Builder / Runner mobile-safe | Host / Frontend 可實作 | `blueprint/20_accessibility_responsive_spec.md` | 現有前端未依新藍圖重做 | 在新頁面中做 mobile-safe constraints |
| 第一分鐘上手驗收 | Host / Process 可實作 | `blueprint/21_testing_acceptance_matrix.md` | 這是驗收流程，不是 SDK 功能 | 以可用性腳本測試，不阻塞基礎功能實作 |

## 當前最重要的待解問題

### 1. 現有 Playground 前端與新藍圖嚴重不一致

目前 `playground/src/App.tsx` 仍以 React Flow 為核心，代表：

1. Builder 仍是圖形編排器
2. PropertyPanel 仍是工程參數面板
3. ChatPanel 仍偏 playground / debug 視角

這不是小修能解決的，而是需要新的 Builder / Runner 前端骨架。

### 2. Gateway 對 Runner 不夠「產品化」

`/v1/chat/completions` 目前主要輸出 `final_message`；對 Runner 想要的：

1. recommendation card
2. reply draft card
3. structured result
4. trust disclosure source payload

都還沒有穩定契約。

### 3. SDK 的 StructuredAction / TextImagePerceive 仍是 placeholder 等級

這兩個是最明確的 library gap：

1. `StructuredAction` 還沒有正式 structured result contract
2. `TextImagePerceive` 還沒有正式多模態語義路徑

## 建議優先順序

### P0

1. 重新實作 Builder / Runner 前端骨架
2. 定義 Runner 結果與依據的 Gateway 契約

### P1

1. 補 `StructuredAction` 真正結構化輸出
2. 補 `TextImagePerceive` 多模態邏輯

### P2

1. 將可採用等級做成更可推定的系統能力
2. 補更細的 analytics / observability

## PM / Engineering 驗收標準

1. 每條藍圖能力都能被標成已具備、Host/Frontend 可實作、Gateway 需補、SDK 需補之一。
2. 團隊不再誤以為「藍圖已定義」等於「repo 已支援」。
3. 前端、Gateway、SDK 的下一步工作能依這份矩陣切分清楚。