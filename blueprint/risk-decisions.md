# Risk Decisions — 已消除的風險與替代方案紀錄

> 受眾:後續維護者、新加入工程師
> 目的:把專案啟動前曾經考慮過、但後來基於新事實放棄的設計選擇記錄下來,避免日後有人再走一次同樣的彎路。

每條決策有四要素:**風險原貌、新事實、決策、預期效應**。

---

## D1 — 放棄 Runner 容器化 + Model Card SHA 驗證

### 風險原貌(2026 Q1 評估)

- **R4. Ryzen AI NPU runtime 的容器化**:NPU 驅動容器化(裝置直通、權限、驅動版本對齊)常是隱形地雷,會拖慢 M0
- **R1. 上游 Model Card 的實際格式還沒看到**:SDK 端要解析什麼欄位、SHA 算法是什麼、檔案在哪、更新節奏如何,都是黑盒

當時藍圖規劃:

- F-02:`model-runner-llama3-ryzenai-npu` 容器骨架,實作 `/healthz` + `/internal/infer`
- F-03:Model Card SHA 驗證機制
- F-05:從上游取得真實 Model Card 放入 `assets/model-cards/`

### 新事實

上游 [amd-ryzen-ai-benchmark](https://github.com/R300-AI/amd-ryzen-ai-benchmark) 已提供:

- `api.py`:OpenAI 相容 HTTP server,於 `localhost:8000` 暴露 `POST /v1/chat/completions` + `GET /v1/models`
- 完整的 conda 環境設定指南(`ryzen-ai-1.7.1` for NPU、`rocm-pytorch` for iGPU)
- 已實測支援的模型列表(`gemma3-4b-npu` 等)
- OpenAI SDK + Open WebUI 整合範例

意即:**「模型 × 晶片」的部署與對外 API 化已由上游解決**。本專案再做一次是重複工作,且會增加版本同步的維護成本。

### 決策

| 原規劃 | 改為 |
|--------|------|
| 本專案實作 Runner 容器、`/internal/infer` | ❌ 取消,使用者依上游 README 啟動 `api.py` |
| 本專案實作 Model Card SHA 驗證 | ❌ 取消,認證責任完全歸於上游 |
| 本專案實作 Gateway 多 runner 路由 | ❌ 取消;backend 屬於 **Action node 屬性**,同一個 Gateway / 同一個 Workflow 內由 `node_overrides` 切換(M4-2 已實作,見 `tests/test_multi_backend.py`)|
| F-02 / F-03 / F-05 | ❌ 移除 |
| 新增 F-02(上游客戶端封裝、healthcheck,接受 `base_url` 參數可指向多台機器) | ✅ 新增 |

### 預期效應

- 風險 R4(NPU 容器化)**整段消除**
- 風險 R1(Model Card 格式)**整段消除**
- Phase 0 工作量從 5 項砍到 4 項
- M0 達成時間預估減少約一半(無需處理 NPU 驅動容器化)
- 本專案職責更清晰:「Agentic 編排層」,不再有「推論伺服器封裝者」的角色混淆

### 衍生風險

- **新風險 R6**:上游 API schema 若有斷裂變更(如 `model` 欄位命名改變),本專案會跟著壞——已在 [docs/02-model-card-contract/upstream-integration.md](../docs/02-model-card-contract/upstream-integration.md) §六 鎖定上游 commit 來緩解

---

## D2 — Dashboard 從 Langflow fork 改為 Streamlit + 圖形編排延後

### 風險原貌(2026 Q1 評估)

- **R2. Langflow 拖曳 UI 綁到「本專案五節點型別」的工程量被低估**:Langflow 原生節點抽象未必能乾淨對應到 `Perceive/Plan/Retrieve/Reflect/Action + required_capability`,可能需要 fork 比預期深

當時藍圖規劃:

- B-01:Fork Langflow 至本專案的 `dashboard/` 子目錄
- B-02:替換 Langflow 預設 LangChain 後端為 Gateway 呼叫
- B-07:Langflow 圖形編輯介面綁定本專案五節點型別

### 新事實 + 重新分析

回頭審視 M3 驗收條件:

- M3-2:「五節點完整工作流在 Dashboard 上即時可見(節點進入/離開、Token 消耗)」
- M3-3:Dashboard 需求 3 面板可用

**這些條件全部只需要「執行觀測」能力,完全不需要「圖形編排」能力。**

「圖形編排」是「讓使用者自製工作流」的延伸能力,但 PoC 階段使用者用 OpenAI SDK 直接呼叫就能驗證——M3 不需要它。

### 決策

| 能力 | 階段 | 工具 |
|------|------|------|
| **執行觀測**(M3 必需) | Phase 2(Track B) | Streamlit(MIT,Python,免 fork) |
| **圖形編排** | Phase 5(M3 後評估,啟動條件見 [docs §四](../docs/04-observability-dashboard/visualization-ui.md)) | 待啟動時再選型(Langflow / React Flow / 自製),Phase 1/2 不投入 |

### 預期效應

- 風險 R2(Langflow fork 深度未知)**延後到 M3 之後再面對**,且屆時可基於 M3 累積的實際使用情境做更明智的選型
- Track B 工程量從「fork + 替換後端 + 綁定節點型別 + 整合觀測」收斂為「Streamlit 四面板」
- B-01 / B-02 / B-07 移除,改為 B-01~B-08 全部與觀測有關
- Phase 2 預估工時從「不確定」降為「1–2 週可完成」

### 衍生風險

- **新風險 R7**:Streamlit 的視覺品質弱於 Langflow,對外展示時可能影響「叢集管理協定」的說服力——緩解方式是 demo 錄影時聚焦在「節點動向 + 即時資料」而非 UI 美感

---

## D3 — Quickstart 時間目標從 15 分鐘放寬到 30 分鐘

### 風險原貌

- **R3. 「15 分鐘陌生人能跑完」這個門檻很高**:Docker + 模型映像檔下載 + Ryzen AI NPU 驅動環境的現實,15 分鐘目標偏激進

### 新事實 + 重新分析

D1 後拓樸變更:

- 不再有 Docker(改純 Python 行程)
- 不再有模型映像檔下載(模型由上游管理)
- 上游 Ryzen AI Software 1.7.1 + conda 環境的安裝仍需時間

把「15 分鐘」拆開看:

- 上游環境安裝:**不在本專案可控範圍**,屬於上游責任
- 本專案啟動(Gateway + Dashboard):≤ 5 分鐘可達成
- 第一次跑通五節點工作流:≤ 5 分鐘

### 決策

| 原規劃 | 改為 |
|--------|------|
| M3-1:15 分鐘完成全部步驟 | 30 分鐘完成全部步驟(含上游環境安裝);本專案部分 ≤ 5 分鐘 |
| 卡關次數 ≤ 1 | 卡關次數 ≤ 2(更務實) |

### 預期效應

- M3-1 達成率從原估 3–4 成提升到 6 成以上
- 驗收條件更貼近現實,避免「demo 當天才發現過不了」
- 本專案的責任邊界明確化:只對「第二步開始」負責

---

## D4 — Reflect 節點預設策略保留 fallback

### 風險原貌

- **R5. Reflexion 最小實作的「夠用品質」門檻**:Reflexion 若品質太差,整條 demo 看起來像「無意義的 retry 迴圈」

### 決策

A-09 工作項定義為:

- 主路徑:Reflexion 最小實作(verbal feedback,不訓練)
- Fallback:rule-based 規則(輸出長度 < N 重試一次)

PoC 階段預設啟用主路徑,demo 前 1 天若發現主路徑品質明顯不夠,切換到 fallback,並在 [docs](../docs/03-agentic-orchestration/react-workflow-routing.md) 內標注 PoC 階段的簡化選擇。

### 預期效應

- R5 從「可能拖垮 demo」降級為「demo 前可決策的開關」
- 不需要在 PoC 階段投入大量精力調 Reflexion 品質

---

## D5 — LLM 雙 backend 策略(AMD 本機 + Azure Foundry)

### 風險原貌

D1 後架構上預設「所有節點都走同一個上游 api.py」。但進一步評估 PoC 需求後發現:

- ReAct (Plan) 與 Reflexion (Reflect) 都需 LLM 產 `Thought`,與 Action 生成使用者可見回應走同一模型會:
  1. 單一 NPU 同時服務「一次對話 × 多輪編排推理」,延遲取舍不佳
  2. 不同職責的 prompt 混用同一 context window,token 預算難以測量
- [CLAUDE.md §二](../CLAUDE.md) 重點之一是「Multi-Model Dashboard」,但上游 api.py 一次只能跑一個模型,「Multi」無法呈現

### 新事實

- 專案維護者可提供 Azure AI Foundry deployment(包含 endpoint + API key)供 PoC 驗證使用
- Azure Foundry 的 OpenAI 相容接口與 AMD 上游 api.py 表面一致,雙者可以同一個 LLMBackend Protocol 抽象
- Phase 4 TSiP 到位後,Plan/Reflect 可透過修改 `.env` 換回本機第二個 AMD NPU 伺服器,節點程式無需變動

### 決策

| 原規劃 | 改為 |
|--------|------|
| F-02 實作單一 `upstream_client.py` 代理上游 | 保持不變;Azure Foundry 不進 Gateway 代理層,避免 Agentic SDK 越界接手 Model Card 以外的推論來源 |
| Plan / Reflect 走上游 api.py | Plan / Reflect 節點實作內部以 `openai.AzureOpenAI(...)` 呼叫 Azure Foundry deployment |
| Action 走上游 api.py | 不變(經 Gateway 代理的 `UPSTREAM_API_BASE_URL`) |
| Multi-Model Dashboard 只能顯示 1 個模型 | 同時顯示 AMD NPU 與 Azure Foundry 兩條 inference path,真實呈現 Multi-Model |
| `.env` 只有 `UPSTREAM_API_BASE_URL` | 保持 `UPSTREAM_API_BASE_URL`,另新增 `AZURE_FOUNDRY_ENDPOINT` / `AZURE_FOUNDRY_API_KEY` / `AZURE_FOUNDRY_DEPLOYMENT` |

### 預期效應

- Plan / Reflect / Action 職責物理隔離,token budget 與延遲可獨立量測
- 「Multi-Model Dashboard」在 PoC 階段能真實呈現(雙 LLM 來源),不是 mock
- Phase 4 TSiP 完全在地化的路徑只是「換 Plan/Reflect 節點內部的 base_url」,不是「改架構」
- Gateway / Model Card 的職責邊界保持清晰:Gateway = OpenAI 相容代理 + 編排;Model Card = 認證過的「模型 × 晶片」

---

## 仍存活的風險(Phase 0–3 期間需要持續觀察)

### R6 — 上游 API schema 斷裂變更

**緩解方式**:
- 在 [docs/02-model-card-contract/upstream-integration.md](../docs/02-model-card-contract/upstream-integration.md) §六 鎖定上游 commit
- Phase 0 完成時跟上游維護者(@MarkovChenITRI)確認 schema 穩定性承諾

### R7 — Streamlit 視覺品質弱於原預期

**緩解方式**:
- demo 錄影聚焦「節點動向 + 即時資料」而非 UI 美感
- 若 demo 後客戶明確要求更好的 UI,啟動 M5(圖形編排階段)時一併處理

### R8 — 上游 OpenAI API 未實作某些端點

例如本專案若需要 `embeddings` 端點(用於 Retrieve 節點),但上游 `api.py` 尚未實作。

**緩解方式**:
- A-08 工作項已採 sentence-transformers 本地 embedding(不依賴上游)
- 一般工作流只依賴 `chat/completions`,確認上游已支援

---

## D6 — Editor ChatPanel 對話 UX 設計基準

### 設計決策（2026-06-10 確立）

以 **Open WebUI** 為對話介面的設計參考基準，確立以下三條不可妥協的 UX 原則：

#### 原則一：引導選項每輪顯示

引導選項（Perceive 節點的 `options`）不只在首輪（`showPlaceholder`）顯示。每一輪輪到使用者輸入時，選項列應出現在輸入框上方，讓使用者可選擇預設路徑或自由輸入。

**設計理由**：使用者不一定記得所有可用選項；多輪對話中途切換意圖（例如從「推薦鞋款」改為「尺寸問題」）是合理行為，不應只能在第一輪觸發。

#### 原則二：圖片附件採 Open WebUI 風格預覽

- 上傳後以 **大圖縮圖（64px）** 而非小 chip 呈現，讓使用者可確認上傳內容
- 縮圖可點擊展開（lightbox）
- 移除按鈕懸停顯示，不擋住縮圖
- 支援多圖並排橫向捲動

#### 原則三：Assistant 訊息渲染 Markdown

Assistant 的回應中可能含有 `##`、`###`、`**bold**`、`- list` 等 Markdown 語法。對話框必須以 `marked` 渲染為 HTML，而非原始文字顯示。

**安全注意**：`marked` 輸出需以 `sanitize` 或白名單過濾（PoC 階段因 LLM 輸出來源可控，先用 `marked` 直接輸出，MVP 前補 DOMPurify）。

### 實作依賴

- `marked` 18.x（MIT）：Markdown → HTML
- 未來 MVP 補強：`dompurify`（XSS 防禦）

---

## 決策變更流程

任何已記錄的決策(D1–D5)若日後需要推翻:

1. 在本文件新增 D-N 條目,引用被推翻的決策編號
2. 寫明新事實與新決策
3. 同步調整 [tracks.md](tracks.md) / [milestones.md](milestones.md) 對應工作項
4. 提 PR,標題前綴 `[blueprint] revert D-X`

避免「決策悄悄漂移」是這份文件存在的最大價值。
