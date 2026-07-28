# Retriever 統一介面變更清單草案

## 目的

這份草案用來整理 `SemanticRetrieve` 從目前的低階注入式介面，調整為「對外統一配置、對內保留抽象」時，需要同步修改的程式碼、文件與依賴項目。

本次目標不是立刻定稿所有實作細節，而是先把後續要動的欄位、段落與檔案範圍收斂成一份可執行清單。

---

## 核心設計方向

### 對外原則

`SemanticRetrieve` 應該成為 retrieval 的統一 public facade。

也就是說，應用層使用者只需要設定：

- embedding provider 相關參數
- OpenAI-compatible 連線參數
- index artifact 路徑
- source document 路徑
- 是否自動建置或重建
- top-k 等檢索行為

使用者不需要自己先建立 `embedder` 或 `knowledge_base` 物件再傳入。

### 對內原則

SDK 內部仍保留：

- `Embedder` 抽象
- `KnowledgeBase` 抽象
- `VisionQueryBuilder` 抽象

也就是：

- 外部 API 統一
- 內部實作可替換
- 預設路徑可產品化
- 進階用法仍可保留 override 能力

---

## 1. 必改：SDK 程式碼

## 1.1 `agentic_sdk/modules/retrieve/semantic.py`

### 目前狀態

目前 `SemanticRetrieve` 的初始化參數為：

- `top_k`
- `embedder`
- `knowledge_base`
- `vision_query`

這是偏底層組裝者導向的介面，還不是 SDK 使用者導向的統一配置入口。

### 必改欄位

需要重新整理 `__init__` 的 public 參數，至少明確分出下列兩層：

1. 對外統一配置欄位
2. 對內 override 欄位

建議 public 欄位包含：

- `provider`
- `api_key`
- `base_url`
- `embedding_model`
- `sources`
- `saved_path`
- `top_k`
- `rebuild_if_missing`
- `rebuild_if_stale`
- `vision_query`

建議進階 override 欄位包含：

- `embedder`
- `knowledge_base`

### 必改段落

需要重寫或新增下列實作段落：

1. constructor 參數宣告
2. constructor 內的預設元件組裝邏輯
3. 預設 embedder 建立邏輯
4. 預設 knowledge base 建立邏輯
5. 當使用者自行傳入 `embedder` 或 `knowledge_base` 時的優先順序規則
6. 缺少必要參數時的錯誤訊息

### 必補行為規格

需要在實作中明確定義：

1. 若傳入 `embedder`，是否覆蓋 `provider/api_key/base_url/embedding_model`
2. 若傳入 `knowledge_base`，是否覆蓋 `index_path/source_path/rebuild policy`
3. 若 public config 與 override 同時出現，哪一邊優先
4. 若只想查 persistent memory，不提供知識庫時，是否允許退化執行

## 1.2 `agentic_sdk/modules/retrieve/__init__.py`

### 必改欄位

若本次新增新的 facade config 類別或預設 knowledge base 實作，這裡需要決定是否對外 export。

### 需決策項目

1. 是否新增 `SemanticRetrieveConfig`
2. 是否 export `OpenAIEmbedder`
3. 是否 export `FaissKnowledgeBase`

若決策是「對一般使用者不直接暴露」，這個檔案可以不改；但此決策要先在草案中寫清楚。

## 1.3 建議新增檔案：retrieval 配套實作

如果決定把官方預設 stack 納入 SDK，本次建議新增內部實作檔案，而不是把所有責任都塞回 `semantic.py`。

建議候選檔案如下：

1. `agentic_sdk/knowledge/base.py`
	- 定義 `KnowledgeBase` protocol
	- 定義 `search(query, top_k)` 共通介面

2. `agentic_sdk/knowledge/faiss.py`
	- 實作 `FaissKnowledgeBase`
	- 管理 index existence 檢查
	- 管理 artifact 載入
	- 管理 rebuild_if_missing / rebuild_if_stale

3. `agentic_sdk/modules/retrieve/embeddings.py`
	- 實作 `OpenAIEmbedder`
	- 統一 embeddings client 建立方式

4. `agentic_sdk/knowledge/ingestion.py`
	- 管理 document loading
	- 管理 chunking
	- 管理 embedding build pipeline

這一組新增檔案不一定要一次到位，但若要正式支援 FAISS 預設路徑，至少需要 `KnowledgeBase` protocol 與一個官方預設實作。

---

## 2. 必改：文件

## 2.1 `docs/modules/retrieve-modules.md`

### 目前狀態

這份文件目前存在兩個問題：

1. `SemanticRetrieve` 初始化參數與實作不一致
2. 還沒有把統一 facade 設計寫清楚

目前文件列出：

- `similarity_weight`
- `recency_weight`
- `importance_weight`

但目前 `SemanticRetrieve` constructor 並沒有這些參數。

### 必改段落

1. `SemanticRetrieve` 段落總說明
	- 改成「對外統一配置 semantic retrieval」的描述

2. `SemanticRetrieve` 初始化參數表
	- 改成新的 public facade 參數
	- 明確標示哪些是基本設定
	- 明確標示哪些是進階 override

3. `SemanticRetrieve` 使用流程說明
	- 補上 source documents -> chunk -> embedding -> index -> retrieve 的官方預設資料流

4. `VisionQueryBuilder` 相依說明
	- 說明它仍是配套元件，不是 semantic stack 的必要依賴

### 建議新增段落

1. `SemanticRetrieve` 最小可用範例
2. `SemanticRetrieve` 進階 override 範例
3. `自動建置策略` 小節
4. `官方預設 stack` 小節

## 2.2 `README.md`

### 目前狀態

README 目前只有：

- `KeywordRetrieve`
- `PassThroughRetrieve`

還沒有一段正式示範 `SemanticRetrieve`。

### 必改段落

1. `快速開始` 區塊
	- 新增一個 `SemanticRetrieve` 最小範例

2. `Retrieve` 能力敘述
	- 補上 semantic retrieval 的官方定位

3. `安裝` 或 `文件` 區塊
	- 若本次加入額外依賴，需要補安裝說明

### 建議新增內容

建議新增一個簡短範例，呈現使用者只需要配置：

- `api_key`
- `base_url`
- `embedding_model`
- `sources`
- `saved_path`

而不是先建立多個內部元件。

## 2.3 `docs/index.md` 或導覽頁

### 條件式修改

若 retriever 能力從次要模組升級成官方主推流程，導覽頁可補一句：

- semantic retrieval 採 OpenAI-compatible embeddings + FAISS default backend

如果本輪只做草案與底層 API，這一項可以延後。

---

## 3. 條件式修改：requirements

## 3.1 `requirements.txt`

### 目前狀態

目前已包含：

- `openai`

目前未見：

- `faiss-cpu`
- `markitdown`

### 需要修改的條件

只有在下列前提成立時，才建議修改 `requirements.txt`：

1. SDK 官方要提供預設 FAISS backend
2. SDK 官方要提供文件 ingestion build 路徑

### 建議新增項目

若要正式納入官方預設 stack，建議評估加入：

1. `faiss-cpu`
2. `markitdown`

### 需要補充的段落

若新增依賴，README 與 module docs 都需要同步補上：

1. 安裝說明
2. 平台限制說明
3. 是否可選安裝的說明

---

## 4. 建議補強：測試

## 4.1 建議新增 `tests` 用例

若本次真的改 public API，至少要補以下測試：

1. `SemanticRetrieve` 只用 public config 可正常初始化
2. `SemanticRetrieve` 在缺少必要參數時會拋出清楚錯誤
3. `SemanticRetrieve` 傳入 override 元件時，會覆蓋預設組裝
4. `knowledge base` 缺失時，是否能退化為只查 persistent memory

## 4.2 建議驗證的行為

1. `rebuild_if_missing=True` 時的首次建置流程
2. `rebuild_if_stale=True` 時的重建判定
3. README 與 docs 範例可對應實際 API

---

## 5. 建議執行順序

### 第一階段：先對齊規格與 public surface

1. 先改 `SemanticRetrieve` public constructor
2. 同步修正文檔與 README
3. 補最小初始化測試

### 第二階段：再導入官方 default backend

1. 新增 `KnowledgeBase` protocol
2. 新增 `OpenAIEmbedder`
3. 新增 `FaissKnowledgeBase`
4. 視需要加入 `markitdown`
5. 補 artifact build/rebuild 測試

---

## 6. 本草案的明確結論

本次若要落實 `SemanticRetrieve` 的統一對外介面，至少應同步動到：

1. `agentic_sdk/modules/retrieve/semantic.py`
1. `docs/modules/retrieve-modules.md`
2. `README.md`

本次若要把 FAISS 與文件 ingestion 定位成官方預設方案，則還應再動到：

1. `requirements.txt`
2. 新增 knowledge/embedding/ingestion 相關實作檔案
3. 補對應測試

也就是說：

- 文件必改
- `SemanticRetrieve` 程式碼必改
- `requirements.txt` 屬於條件式必改，取決於是否同時納入官方預設 FAISS stack
