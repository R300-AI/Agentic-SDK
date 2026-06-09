# Five-Node Workflow Routing — 跨節點動態路由 [R08] [R24]

> 受眾:SDK 核心開發
> 目的:說明 Agent 工作流如何在 Perceive / Plan / Retrieve / Reflect / Action 五大節點間動態路由,以及為何採用圖狀態機而非線性 Pipeline。

> 文獻編號對應 [docs/README.md §2](../README.md);各節點的學理基準與可整合 SDK 模組對齊 [docs/README.md §3](../README.md)。

## 定位:在 Action Item 中的角色

| 層面 | 狀態 |
|------|------|
| 是否為現階段 Action Item | 本身不是,但是「上下文管理」跟「實際工作流」能跑起來的必要框架 |
| 是否可省略 | ❌ 不可。Perceive / Plan / Retrieve / Reflect / Action 是 SDK 必須遵從的編排典範,如 [CLAUDE.md 目標一](../../CLAUDE.md) 明示 |
| 是否對外暴露 | ❌ 內部實作機制,對外只暴露 OpenAI 相容 API |

實際上,**上下文如何在節點間傳遞** 只有在「為什麼要傳」有明確路由規則時才無歧義,而 ReAct [R08] 提供的就是這個規則。兩者是表裡關係。

## 一、為什麼是圖,不是 Pipeline

線性 Pipeline(Perceive → Plan → Action)只能處理「一次想清楚」的任務。真實的 Agent 工作流必須支援:

- **Reflect 回環** [R17] [R18]:Action 結果不符預期,Reflect 後重新 Plan
- **Retrieve 旁路** [R14] [R16]:Plan 階段需要外部知識補強,先 Retrieve 再回 Plan
- **多分支判斷**:Perceive 後,根據輸入類別走不同分支(影像 → ImageAnalyst、文字 → TextAnalyst)
- **早停**:某節點已得到足夠信心的結論時跳過後續節點

這些模式用 DAG 不足以表達,必須是允許環路的圖狀態機。**LangGraph** [R24] 是業界已驗證的參考實作,本專案的路由抽象與其概念對齊,但不直接綁定其實作。

## 二、五大節點職責

| 節點 | 職責 | 學理基準 | 詳細模組選項 |
|------|------|----------|--------------|
| **Perceive** | 接收外部輸入(文字、影像、音訊、感測器),轉換為結構化表示 | 多模態理解相關研究 | [docs/README.md §3.1](../README.md) |
| **Plan** | 將目標分解為子任務序列,決定下一步走向 | [R08] ReAct, [R09] CoT, [R10] ToT, [R11] Plan-and-Solve, [R12] Self-Consistency | [docs/README.md §3.2](../README.md) |
| **Retrieve** | 從外部知識來源取得 Plan 階段所需的事實依據 | [R14] RAG, [R15] DPR, [R16] Self-RAG | [docs/README.md §3.3](../README.md) |
| **Reflect** | 對 Action 輸出做品質審查,必要時觸發回 Plan | [R17] Reflexion, [R18] Self-Refine, [R19] Constitutional AI | [docs/README.md §3.4](../README.md) |
| **Action** | 呼叫外部工具或執行副作用,產出實際結果 | [R20] Toolformer, [R21] Gorilla, [R22] ToolLLM, [R23] MCP | [docs/README.md §3.5](../README.md) |

## 三、節點抽象

每個節點實作統一介面:

```python
class Node(Protocol):
    name: str                              # "perceive" | "plan" | "retrieve" | "reflect" | "action"
    required_capability: ModelCapability   # 例:reasoning / vision / tool-use / retrieval

    def run(self, ctx: ContextRef, inputs: dict) -> NodeOutput: ...

class NodeOutput(TypedDict):
    next_node: str | None                  # None 代表工作流結束
    payload: dict                          # 傳遞給下一節點的內容
    context_updates: list[ContextEntry]    # 寫回 Active Context
```

`required_capability` 是路由決策的關鍵——SDK 會根據此欄位,從通過認證的模型池中挑選符合能力的模型執行該節點,實現「模型 × 節點」的解耦。

## 四、典型工作流拓樸

五節點之間的合法轉換關係(允許環路):

```
                ┌────────────────────────────┐
                │                            │
                ▼                            │
     ┌─────────────────┐                     │
     │    Perceive     │                     │
     └────────┬────────┘                     │
              ↓                              │
     ┌─────────────────┐    ┌────────────┐   │
     │      Plan       │ ←─ │  Retrieve  │   │
     └────────┬────────┘    └─────▲──────┘   │
              │                   │          │
              ├───────────────────┘          │
              ↓                              │
     ┌─────────────────┐                     │
     │     Action      │                     │
     └────────┬────────┘                     │
              ↓                              │
     ┌─────────────────┐                     │
     │     Reflect     │─────────────────────┘
     └────────┬────────┘  (不滿意:回 Plan)
              ↓
            (END)
```

不是所有工作流都必須走完所有節點。最短可達路徑為 `Perceive → Plan → Action → END`(無 Retrieve、無 Reflect)。

## 五、路由決策來源

路由決策由 **Plan 節點** 自主產出,不由外部 Orchestrator 硬編碼。Plan 節點的回傳必須符合:

```json
{
  "next_node": "retrieve",
  "payload": {"query": "病患歷史影像 2024Q4", "top_k": 5},
  "context_updates": [...]
}
```

SDK 的責任是把 `next_node` 字串對應到實際節點實例並執行,**SDK 不參與「該走哪條路」的判斷**——這個決定權留給 LLM。這是 ReAct [R08] 的核心精神:讓推理過程驅動行動,而非框架預設流程。

## 六、回環與終止條件

允許回環必然帶來無限迴圈風險。本專案透過三道閘門控制:

| 閘門 | 配置項 | 量化依據 |
|------|--------|----------|
| 單一工作流最大節點執行次數 | `WORKFLOW_MAX_NODE_HOPS=50` | 觀察過去整合案例 P99 約為 30 次,加 67% 安全邊際 |
| 單一節點重複進入次數 | `WORKFLOW_MAX_REVISIT=5` | 同一節點被重訪超過 5 次視為陷入迴圈 |
| 單一工作流總執行時間 | `WORKFLOW_TIMEOUT_SEC=600` | 涵蓋醫療影像分析 P99 工作流長度 |

任一閘門觸發 → 工作流終止 → 寫入觀測日誌(降級事件)→ 回傳部分結果給呼叫端,而非靜默失敗。

## 七、跨節點異質模型調度

不同節點可使用不同模型,由 SDK 在執行時根據 `required_capability` 與當下節點負載決定:

```
┌──────────────────────────────────────────────────────┐
│ Perceive  (vision capability)                         │
│   → 路由到 phi3-vision 容器 (Ryzen AI iGPU)           │
├──────────────────────────────────────────────────────┤
│ Plan      (reasoning capability)                      │
│   → 路由到 llama3-8b 容器 (Ryzen AI NPU)              │
├──────────────────────────────────────────────────────┤
│ Retrieve  (retrieval capability)                      │
│   → 路由到 embedding 模型 + 向量 DB (CPU)             │
├──────────────────────────────────────────────────────┤
│ Reflect   (reasoning capability,可與 Plan 同模型)     │
│   → 路由到 llama3-8b 容器 (Ryzen AI NPU)              │
├──────────────────────────────────────────────────────┤
│ Action    (tool-use capability)                       │
│   → 路由到 qwen-tsip 容器 (TSiP NPU)                  │
└──────────────────────────────────────────────────────┘
```

實際路由策略由 [dynamic-offload-engine.md](dynamic-offload-engine.md) 定義。

## 八、PoC 範圍

| 範圍 | 處理 |
|------|------|
| 直接使用 LangGraph [R24] 作為內部實作 | ✅ PoC 採用,避免重造輪子 |
| 對外暴露 LangGraph 概念 | ❌ 對外只暴露 OpenAI 相容 API,SDK 內部用 LangGraph 不外洩 |
| 五節點內建實作 | ✅ PoC 內建 Perceive / Plan / Retrieve / Reflect / Action 完整骨架 |
| 自訂節點型別擴充機制 | ⚠️ PoC 提供五大節點為基底,使用者擴充節點型別留待 MVP |
| Retrieve 節點預設後端 | PoC 採 [Chroma](https://github.com/chroma-core/chroma) + sentence-transformers,符合 [R14] [R15] |
| Reflect 節點預設策略 | PoC 採 [R17] Reflexion 最小實作(verbal feedback,不訓練) |
