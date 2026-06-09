# Context & Memory — 跨節點上下文管理與 Token 過期處理 [R05] [R06]

> 受眾：SDK 核心開發
> 目的：解釋為何邊緣端 Agent 必須做分層上下文管理,以及本專案採用的最小可行方案。

## 一、問題本質

邊緣設備(Ryzen AI PC、TSiP NPU 模組)的記憶體預算遠小於雲端伺服器。當 Agent 工作流跨越多個節點(Perceive → Plan → Retrieve → Reflect → Action)時,三種失效模式幾乎必然發生:

1. **Context 累積溢位**:對話歷史線性成長,KV Cache 在第 N 輪超出 NPU 可用記憶體 → OOM
2. **Token 過期**:某節點的中間結果未及時下游消費,但又佔據快取空間 → 後續節點觸發 Eviction 重算
3. **跨節點上下文遺失**:節點 A 的關鍵推理結論在傳遞到節點 C 時被截斷或語意失真

業界已有的處理路徑 [R05] (MemGPT 的分層記憶體)、[R06] (StreamingLLM 的 Attention Sink),但都假設「單一程序內」。本專案的場景是「跨容器、跨節點」,需要額外的傳輸層設計。

## 二、分層記憶體模型

借用 MemGPT 的作業系統類比,把 Agent 上下文分為三層:

| 層級 | 類比 | 存放位置 | 生命週期 |
|------|------|----------|----------|
| **Working Set** | CPU Cache | Runner 容器內 KV Cache | 單次推論呼叫 |
| **Active Context** | RAM | Gateway 內 in-memory store(Redis or Python dict) | 單次 Agent 工作流 |
| **Archived Context** | Disk | 本機檔案系統 / 物件儲存 | 跨工作流、可重啟恢復 |

跨節點傳遞的單位是 **Active Context 的引用 ID**,而非完整 payload。節點之間透過 ID 拉取,避免每次傳遞都複製完整對話歷史。

## 三、Token 過期處理機制

每筆 Active Context 條目都有兩個時間戳:

```python
@dataclass
class ContextEntry:
    entry_id: str
    content: str
    created_at: float            # 進入 Active 層的時間
    last_accessed_at: float      # 最近一次被某節點讀取的時間
    eviction_priority: int       # 0=固定保留, 1=可降級, 2=可丟棄
```

過期判定規則(透過配置驅動,反硬編碼):

| 配置項 | 預設值 | 量化依據 |
|--------|--------|----------|
| `CONTEXT_IDLE_DEMOTE_SEC` | `300` | 5 分鐘無存取的條目降級到 Archived |
| `CONTEXT_HARD_TTL_SEC` | `3600` | 1 小時後即使有存取也強制重新驗證,避免長尾洩漏 |
| `ACTIVE_CONTEXT_MAX_MB` | `512` | 邊緣節點留給 SDK 的 RAM 預算上限 |

當 Active 層觸及 `ACTIVE_CONTEXT_MAX_MB` 時,按 `eviction_priority` 與 `last_accessed_at` 排序降級。

## 四、跨節點傳遞契約

節點間透過 gateway 拉取上下文,介面定義:

```http
GET /internal/context/{entry_id}
  → 200 OK { "content": "...", "metadata": {...} }
  → 404 Not Found(已降級或過期)
  → 410 Gone(已強制 TTL 過期)
```

收到 404 / 410 的節點必須:
1. 嘗試從 Archived 層恢復(若條目存在於 Disk)
2. 若無法恢復,向 Gateway 申請重建並回報「上下文降級事件」(進入觀測層日誌)

## 五、PoC 範圍與不做事項

| 範圍 | 處理 |
|------|------|
| 單機內多容器之間(邏輯節點)的引用 ID 傳遞 | ✅ PoC 必做。「節點」在 PoC 期間指邏輯節點(同機不同容器),不是實體機器 |
| Active 層用 Python in-memory dict | ✅ PoC 簡化,跨實體機器階段需改 Redis(Phase 5 評估) |
| 跨實體機器(LAN 內)的引用 ID 傳遞 | ✅ **M4 實機驗收通過(2026-06-09)**。同一個 `WorkflowConfig` 由 `node_overrides` 分別指向 Ryzen NPU(`gemma3-4b-npu`, elapsed 5.938 s)與 Azure Foundry(`gpt-5.2`, elapsed 2.031 s),兩者 `entry_types` 序列完全一致,確認跨 backend 的上下文 schema 不變。佐證報告:[docs/quickstart-runs/multi-backend-20260609T095312Z.json](../../docs/quickstart-runs/multi-backend-20260609T095312Z.json) |
| 跨資料中心、跨地理區域的上下文同步 | ❌ 不在路線圖 |
| 加密、隱私保護(差分隱私、PII 過濾) | ❌ 不在 PoC 範圍,由整合商於上層處理 |

## 六、未解決的設計問題

以下問題在 PoC 階段不強求答案,但需追蹤:

- 當同一 entry 被多節點同時讀取並回寫時的衝突解決(目前採 last-write-wins,可能造成靜默資料遺失)
- Archived 層的儲存配額管理(目前無上限,長期運作會塞滿 disk)

兩者皆已記入待解清單,MVP 階段需提出方案。
