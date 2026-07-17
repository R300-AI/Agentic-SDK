# Playground V2 Blueprint Master Index

## 目的

這個目錄承載 Agentic SDK Playground V2 的正式規格文件。目標不是記錄靈感，而是提供之後實作、驗收、交付時可直接依循的藍圖。

V2 的核心定義如下：

1. Playground V2 是 Agentic SDK Python Workflow 程式碼生成器與試跑器。
2. Python `source code string` 是唯一真實來源。
3. UI 只負責引導建立、回朔還原、試跑與保存，不以 YAML/JSON 作為主要配置真實來源。
4. 手動進站的使用者預設進入建構頁。
5. AI Hub deep link 使用者預設直接進入試跑頁，再依權限決定是否可回到建構頁更新。

## 閱讀順序

1. `01_product_charter.md`
2. `02_roles_modes_permissions.md`
3. `04_user_journeys.md`
4. `05_route_state_map.md`
5. `09_visual_north_star_and_references.md`
6. `11_visual_design_tokens_motion.md`
7. `13_python_source_of_truth_spec.md`
8. `15_aihub_integration_contract.md`
9. `06_page_entry.md`
10. `07_page_builder.md`
11. `08_page_runner.md`

## 文件清單

| 檔案 | 狀態 | 目的 |
| --- | --- | --- |
| `01_product_charter.md` | 已建立 | 定義產品定位、目標、非目標與 V2 成功條件 |
| `02_roles_modes_permissions.md` | 已建立 | 定義四種模式的權限矩陣與 UI 可見範圍 |
| `04_user_journeys.md` | 已建立 | 定義主要使用者旅程與每條旅程的 UX 任務 |
| `05_route_state_map.md` | 已建立 | 定義 Flask route、頁面跳轉、狀態流與 deep link 行為 |
| `09_visual_north_star_and_references.md` | 已建立 | 定義 Playground V2 的統一視覺北極星、反拼貼規則與外部參考來源 |
| `06_page_entry.md` | 已建立 | 入口頁 layout、視覺與互動規格 |
| `07_page_builder.md` | 已建立 | 建構頁 layout、資訊架構與交互規格 |
| `08_page_runner.md` | 已建立 | 試跑頁與 AI Hub 體驗模式規格 |
| `11_visual_design_tokens_motion.md` | 已建立 | 定義色彩、字體、層級、動效與模式視覺規則 |
| `13_python_source_of_truth_spec.md` | 已建立 | 定義 code-first canonical model 與保存規則 |
| `15_aihub_integration_contract.md` | 已建立 | 定義 AI Hub API 串接、責任邊界與風險 |
| `20_accessibility_responsive_spec.md` | 已建立 | 定義 Builder/Runner 的可存取性與 mobile-safe 響應式規則 |
| `21_testing_acceptance_matrix.md` | 已建立 | 定義功能驗收與基礎可用性驗收矩陣 |
| `24_builder_persona_modes.md` | 已建立 | 定義 Builder 的資訊深度策略與建立者使用原則 |
| `25_runner_layout_variants.md` | 已建立 | 定義 Runner 的內部版型模板與推薦規則 |
| `26_trust_adoption_layer.md` | 已建立 | 定義回應區塊下方的信任揭露微互動原則 |
| `29_visual_art_consistency_spec.md` | 已建立 | 定義三頁在色彩、字體、插圖、卡片、CTA 與審稿標準上的美術一致性 |
| `30_implementation_gap_matrix.md` | 已建立 | 對照藍圖與現有 SDK/gateway/frontend 實作，標示缺口與補強方向 |

## 後續應補文件

下列文件仍建議在後續批次補齊：

1. `12_content_microcopy.md`
2. `14_code_generation_roundtrip_spec.md`
3. `18_runtime_execution_attachments.md`
4. `19_security_privacy_error_states.md`
5. `22_analytics_observability.md`
6. `23_delivery_plan_pm_checklist.md`

下列文件已補齊，建議在後續設計深化時一併閱讀：

1. `24_builder_persona_modes.md`
2. `25_runner_layout_variants.md`
3. `26_trust_adoption_layer.md`
4. `29_visual_art_consistency_spec.md`
5. `30_implementation_gap_matrix.md`

## 規格撰寫原則

每份頁面規格至少要回答這些問題：

1. 這一頁的任務是什麼。
2. 使用者從哪裡進來。
3. 使用者能做什麼，不能做什麼。
4. 哪些 UI 元件是必要的。
5. 錯誤、空狀態、等待狀態怎麼呈現。
6. 匿名、登入、AI Hub 導流這三大來源在這一頁有哪些差異。
7. PM 如何驗收這一頁完成。

## 版本控制原則

1. 若產品定義變更，必須先更新 `01_product_charter.md`。
2. 若模式/權限變更，必須同步更新 `02_roles_modes_permissions.md`、`05_route_state_map.md`、`08_page_runner.md`。
3. 若 Python code canonical model 變更，必須同步更新 `13_python_source_of_truth_spec.md`。
4. 若 AI Hub 串接條件變更，必須同步更新 `15_aihub_integration_contract.md`。
5. 若視覺風格、品牌語氣或外部 reference 變更，必須同步更新 `09_visual_north_star_and_references.md` 與 `11_visual_design_tokens_motion.md`。
6. 若三頁的卡片語言、色票、字體、圖示或 CTA 規則變更，必須同步更新 `29_visual_art_consistency_spec.md`。