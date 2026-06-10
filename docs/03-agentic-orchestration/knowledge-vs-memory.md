# 知識庫 vs. 對話記憶 — KnowledgeBase 與 MemoryStore 的分工

本文釐清 Agentic SDK 中兩種「非參數記憶」(non-parametric memory) 的角色分野，
作為 Retrieve 節點同時接入 `KnowledgeBase` 與 `MemoryStore` 的設計依據。

---

## 1. 為何要區分

依 [R14] RAG 的原始論文，外部記憶相對於模型權重(parametric memory)而言為非參數來源；
[R05] MemGPT 進一步把非參數記憶拆為 Recall(對話歷程)與 Archival(可寫入的長期儲存)。
本專案沿用此分層，但把「靜態且預先建立」與「動態且隨對話成長」進一步明確劃分：

- **KnowledgeBase**：靜態的領域知識索引(產品型錄、SOP、FAQ)。由領域擁有者預先建立，運行時唯讀。
- **MemoryStore**：動態的對話痕跡(每輪 user/assistant 訊息、命中過的事實)。隨工作流持續寫入。

兩者在 Retrieve 節點被合併召回，但寫入路徑、生命週期、所有權完全分離。

---

## 2. 對照表

| 維度 | KnowledgeBase(本次新增) | MemoryStore(沿用) |
|------|--------------------------|---------------------|
| 內容性質 | 領域知識、產品資料、SOP | 對話片段、檢索命中、推論結果 |
| 來源 | JSON 檔(可換成向量索引) | 工作流執行期間自動寫入 |
| 寫入時機 | 部署前由領域擁有者準備 | 每輪 Perceive / Action 自動追加 |
| 生命週期 | 與部署版本綁定，極少變動 | 隨 session 增長，可分層淘汰 |
| 召回方式 | 文字相似度(MVP)→ 向量檢索 | 相似度 + 時間衰減 + 重要性加權 |
| 對應 [R05] 層 | 接近 Archival Storage(只讀子集) | 對應 Recall + Active Memory |
| 對應 [R14] | 外部知識庫 | 對話脈絡的延伸 |

設計上兩者皆由 `Retrieve` 節點消費，輸出統一寫入 `state["context"]`，
下游 Plan / Action 節點不需要區分來源即可使用。

---

## 3. 在工作流裡的接線

```python
from agentic_sdk.knowledge import KnowledgeBase
from agentic_sdk.workflow.nodes.retrieve import SemanticRetrieve
from agentic_sdk.memory import MemoryStream

kb = KnowledgeBase.from_file("examples/knowledge/shoe_store.json")
mem = MemoryStream()

retrieve = SemanticRetrieve(
    knowledge_base=kb,    # 靜態領域知識
    memory_stream=mem,    # 動態對話記憶
    top_k=3,
)
```

Retrieve 節點會先查 KB、再查 Memory，並把結果以可讀片段合併到 `state["context"]`；
中介資料(`metadata`)同時保留 `kb_*` 與既有 Memory 欄位，方便觀測層追蹤召回來源。

---

## 4. 用自己的領域知識替換預設範例(三步驟)

預設範例 `examples/knowledge/shoe_store.json` 為虛構的鞋店產品型錄，僅供 PoC 展示。
要替換為自有領域，請依下列步驟操作：

1. **準備 JSON**：每筆資料含 `id`、`title`、`content`，視需求加 `metadata`(分類、價格、連結等)。

   ```json
   [
     {
       "id": "kb-001",
       "title": "標題",
       "content": "段落內容，用於相似度比對",
       "metadata": {"category": "可選分類"}
     }
   ]
   ```

2. **放置檔案**：建議置於 `examples/knowledge/<your_domain>.json` 或專案的 `data/` 目錄。
3. **更新編排設定**：在編輯器 Retrieve 節點的「知識庫檔案」欄位填入新路徑，或在程式碼把
   `KnowledgeBase.from_file(...)` 的路徑換掉即可，無需改動其他節點。

Action 節點的人設(`system_prompt`)同樣建議一併更新，以對齊新的領域語氣。

---

## 5. 後續演進方向

- **檢索升級**：MVP 採 Jaccard 相似度足以驗證資料流；正式環境應替換為向量檢索([R15] DPR)，
  介面保持 `search(query, top_k)` 不變，呼叫端無感。
- **熱更新**：未來若需要在不重啟工作流的情況下換掉知識庫，可在 `KnowledgeBase` 上加版本欄位，
  由 Retrieve 節點在每輪檢查是否需要 reload。本階段刻意不做，避免過度設計。
- **與 Reflect 結合**：召回結果可被 [R16] Self-RAG 風格的 Reflect 節點檢查相關性，
  決定是否重新檢索或改寫查詢，留待 Phase 3 評估。
