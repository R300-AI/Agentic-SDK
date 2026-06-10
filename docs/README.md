# docs — Agentic SDK 設計文檔索引

本目錄為 Agentic SDK 的「原子化文檔」庫,每篇 Markdown 邏輯獨立、可單獨閱讀。設計參數一律附量化依據,所有架構決策皆掛勾至下方文獻索引,確保本專案的設計選擇可追溯至業界既有的權威成果,而非獨樹一格的自創方案。

---

## 1. 文件導覽

| 路徑 | 主題 | 受眾 |
|------|------|------|
| [01-architecture/ai-hub-vision.md](01-architecture/ai-hub-vision.md) | AI Hub 在 TSiP 落地藍圖中的雙核心定位 | 架構師、決策層 |
| [01-architecture/microservices-design.md](01-architecture/microservices-design.md) | SDK 與上游推論伺服器的部署拓樸 | 後端工程師 |
| [02-model-card-contract/upstream-integration.md](02-model-card-contract/upstream-integration.md) | 與上游 `amd-ryzen-ai-benchmark` 的銜接契約 | SDK 整合者 |
| [03-agentic-orchestration/context-and-memory.md](03-agentic-orchestration/context-and-memory.md) | 跨節點上下文管理與 Token 過期處理 | SDK 核心開發 |
| [03-agentic-orchestration/knowledge-vs-memory.md](03-agentic-orchestration/knowledge-vs-memory.md) | KnowledgeBase 與 MemoryStore 的分工與替換流程 | SDK 核心開發、領域整合者 |
| [03-agentic-orchestration/react-workflow-routing.md](03-agentic-orchestration/react-workflow-routing.md) | 五大節點動態路由 | SDK 核心開發 |
| [03-agentic-orchestration/dynamic-offload-engine.md](03-agentic-orchestration/dynamic-offload-engine.md) | 邊緣端 NPU / GPU / CPU 異質卸載策略 | 資源層開發 |
| [04-observability-dashboard/telemetry-metrics.md](04-observability-dashboard/telemetry-metrics.md) | token/sec、記憶體峰值的遙測資料流 | 觀測層開發 |
| [04-observability-dashboard/visualization-ui.md](04-observability-dashboard/visualization-ui.md) | Multi-Model Dashboard 魔改策略 | UI 整合 |
| [04-observability-dashboard/phase5-graph-editor-plan.md](04-observability-dashboard/phase5-graph-editor-plan.md) | M5 圖形編排 UI 設計與實作計畫 | Phase 5 開發者 |
| [04-observability-dashboard/phase12-github-pages-plan.md](04-observability-dashboard/phase12-github-pages-plan.md) | M12 編輯器上架 GitHub Pages 規劃 | Phase 12 開發者 |
| [05-api-reference/openai-compatible-api.md](05-api-reference/openai-compatible-api.md) | OpenAI 相容端點規格 | 應用端開發者 |
| [05-api-reference/python-sdk-integration.md](05-api-reference/python-sdk-integration.md) | Agentic SDK Python 套件使用 | 應用端開發者 |

---

## 2. 學理基礎索引(Reference Index)

### 2.1 編號規則

所有引用採用 `[Rxx]` 格式,文件內以該編號回扣本表。分組以「研究主題」為單位,不以發表年份排序。讀者可循連結直接前往原文閱讀。

### 2.2 平台與工程基準

| 編號 | 文獻 / 規範 | 作用 |
|------|-------------|------|
| [R01] | [OpenAI API Reference](https://platform.openai.com/docs/api-reference) | 本專案對外 REST / SSE 介面相容基準 |
| [R02] | Kwon et al., [Efficient Memory Management for Large Language Model Serving with PagedAttention](https://arxiv.org/abs/2309.06180) (vLLM, SOSP 2023) | KV Cache 分頁化管理,動態 Offload 與記憶體預算估算的學理 |
| [R03] | Reddi et al., [MLPerf Mobile Inference Benchmark](https://arxiv.org/abs/2012.02328) (2020) | 邊緣端 Inference 延遲與功耗量測方法學,SLA 指標對齊基準 |
| [R04] | Mattson et al., [MLPerf: An Industry Standard Benchmark Suite for Machine Learning Performance](https://arxiv.org/abs/1910.01500) (2019) | 跨硬體可重現的效能比較框架,上游認證閘道方法論基礎 |

### 2.3 上下文與記憶體管理

| 編號 | 文獻 | 作用 |
|------|------|------|
| [R05] | Packer et al., [MemGPT: Towards LLMs as Operating Systems](https://arxiv.org/abs/2310.08560) (2023) | 分層記憶體架構(Working Set / Active / Archived),本專案上下文管理直接理論基礎 |
| [R06] | Xiao et al., [Efficient Streaming Language Models with Attention Sinks](https://arxiv.org/abs/2309.17453) (2023) | StreamingLLM 透過保留 Attention Sink,讓 LLM 處理無限串流而不重算 KV Cache |
| [R07] | Park et al., [Generative Agents: Interactive Simulacra of Human Behavior](https://arxiv.org/abs/2304.03442) (2023) | 多 Agent 互動與長期記憶設計,跨節點上下文社會性傳遞依據 |

### 2.4 編排與推理(Reasoning)

| 編號 | 文獻 | 作用 |
|------|------|------|
| [R08] | Yao et al., [ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629) (2022) | 「推理 ↔ 行動」交替執行典範,本專案五大節點編排的必遵框架 |
| [R09] | Wei et al., [Chain-of-Thought Prompting Elicits Reasoning in Large Language Models](https://arxiv.org/abs/2201.11903) (2022) | CoT,Plan 節點的最基礎推理模式 |
| [R10] | Yao et al., [Tree of Thoughts: Deliberate Problem Solving with Large Language Models](https://arxiv.org/abs/2305.10601) (2023) | ToT,Plan 節點的分支搜尋進階模式 |
| [R11] | Wang et al., [Plan-and-Solve Prompting](https://arxiv.org/abs/2305.04091) (2023) | 顯式分離「規劃」與「執行」,Plan 節點輸出格式參考 |
| [R12] | Wang et al., [Self-Consistency Improves Chain of Thought Reasoning in Language Models](https://arxiv.org/abs/2203.11171) (2022) | 多路徑投票,Plan 節點結果穩定性提升 |
| [R13] | Khattab et al., [DSPy: Compiling Declarative Language Model Calls into Self-Improving Pipelines](https://arxiv.org/abs/2310.03714) (2023) | 將 Prompt 工程編譯化,本專案節點介面標準化的啟發來源 |

### 2.5 檢索增強(Retrieval-Augmented)

| 編號 | 文獻 | 作用 |
|------|------|------|
| [R14] | Lewis et al., [Retrieval-Augmented Generation for Knowledge-Intensive NLP Tasks](https://arxiv.org/abs/2005.11401) (2020) | RAG 原始論文,Retrieve 節點的標準典範 |
| [R15] | Karpukhin et al., [Dense Passage Retrieval for Open-Domain Question Answering](https://arxiv.org/abs/2004.04906) (2020) | DPR,密集向量檢索的代表方法 |
| [R16] | Asai et al., [Self-RAG: Learning to Retrieve, Generate, and Critique through Self-Reflection](https://arxiv.org/abs/2310.11511) (2023) | Self-RAG 將 Retrieve 與 Reflect 結合,本專案兩節點協同的參考 |

### 2.6 自我反思(Self-Reflection)

| 編號 | 文獻 | 作用 |
|------|------|------|
| [R17] | Shinn et al., [Reflexion: Language Agents with Verbal Reinforcement Learning](https://arxiv.org/abs/2303.11366) (2023) | Reflexion,Reflect 節點的代表方法 |
| [R18] | Madaan et al., [Self-Refine: Iterative Refinement with Self-Feedback](https://arxiv.org/abs/2303.17651) (2023) | 自我精修迭代,Reflect 節點輸出回饋格式參考 |
| [R19] | Bai et al., [Constitutional AI: Harmlessness from AI Feedback](https://arxiv.org/abs/2212.08073) (2022) | Constitutional AI,Reflect 節點的安全性約束範式 |

### 2.7 工具使用(Tool Use)

| 編號 | 文獻 | 作用 |
|------|------|------|
| [R20] | Schick et al., [Toolformer: Language Models Can Teach Themselves to Use Tools](https://arxiv.org/abs/2302.04761) (2023) | Toolformer,Action 節點工具呼叫的學理基礎 |
| [R21] | Patil et al., [Gorilla: Large Language Model Connected with Massive APIs](https://arxiv.org/abs/2305.15334) (2023) | 大規模 API 工具庫,Action 節點對接外部服務的參考 |
| [R22] | Qin et al., [ToolLLM: Facilitating Large Language Models to Master 16000+ Real-world APIs](https://arxiv.org/abs/2307.16789) (2023) | 工具呼叫的大規模訓練與評估方法 |
| [R23] | Anthropic, [Model Context Protocol (MCP) Specification](https://modelcontextprotocol.io/) | MCP,跨應用工具呼叫的事實標準協定,Action 節點未來相容方向 |

### 2.8 編排框架(Engineering Reference)

| 編號 | 框架 / 平台 | 作用 |
|------|-------------|------|
| [R24] | [LangGraph](https://github.com/langchain-ai/langgraph) | 圖結構狀態機框架,跨節點 Agent 工作流參考實作 |
| [R25] | [LangSmith](https://www.langchain.com/langsmith) / [Arize Phoenix](https://github.com/Arize-ai/phoenix) | LLM Observability 平台,Dashboard 視覺化設計參考 |
| [R26] | [Langflow](https://github.com/langflow-ai/langflow) | MIT 授權圖形編排介面,Phase 5 圖形編排候選之一(見 [blueprint/risk-decisions.md D2](../blueprint/risk-decisions.md)) |
| [R27] | [React Flow](https://github.com/xyflow/xyflow) | MIT 授權圖形編輯函式庫,Phase 5 圖形編排候選之一 |

---

## 3. 五大節點對齊表(Perceive / Plan / Retrieve / Reflect / Action)

本表為本專案編排層的核心對齊文件。每個節點皆需追溯至業界既有典範,並列出可直接整合的開源 SDK 模組,確保本專案的編排不重新發明輪子,而是站在已有成果之上。

### 3.1 Perceive(感知)

| 面向 | 內容 |
|------|------|
| **節點職責** | 接收外部輸入(文字、影像、音訊、感測器訊號),轉換為下游節點可處理的結構化表示 |
| **學理基準** | 多模態理解類論文(本專案目前未鎖定特定 Perceive 範式,屬模型能力範疇);相關的 Plan 階段交接見 [R08] |
| **可直接整合的 SDK 模組** | • [Ollama](https://github.com/ollama/ollama)(多模態如 llava、bakllava)<br>• [HuggingFace Transformers](https://huggingface.co/docs/transformers) `AutoProcessor`<br>• [faster-whisper](https://github.com/SYSTRAN/faster-whisper)(語音轉文字)<br>• [LangChain Document Loaders](https://python.langchain.com/docs/integrations/document_loaders/)<br>• [LlamaIndex Readers](https://docs.llamaindex.ai/en/stable/module_guides/loading/connector/) |
| **對應本專案文件** | [03-agentic-orchestration/react-workflow-routing.md](03-agentic-orchestration/react-workflow-routing.md) §節點抽象 |

### 3.2 Plan(規劃)

| 面向 | 內容 |
|------|------|
| **節點職責** | 將使用者目標分解為可執行的子任務序列,決定下一步走向哪個節點 |
| **學理基準** | [R08] ReAct(推理 ↔ 行動交替)、[R09] Chain-of-Thought、[R10] Tree of Thoughts、[R11] Plan-and-Solve、[R12] Self-Consistency |
| **可直接整合的 SDK 模組** | • [LangChain Agents](https://python.langchain.com/docs/modules/agents/)(PlanAndExecute)<br>• [DSPy](https://github.com/stanfordnlp/dspy) `ChainOfThought` / `ProgramOfThought`<br>• [AutoGen](https://github.com/microsoft/autogen) `GroupChatManager`<br>• [CrewAI](https://github.com/joaomdmoura/crewAI) `Process`<br>• [LangGraph](https://github.com/langchain-ai/langgraph) custom planner node |
| **對應本專案文件** | [03-agentic-orchestration/react-workflow-routing.md](03-agentic-orchestration/react-workflow-routing.md) §路由決策來源 |

### 3.3 Retrieve(檢索)

| 面向 | 內容 |
|------|------|
| **節點職責** | 從外部知識來源(向量資料庫、API、本地檔案)取得 Plan 階段所需的事實依據 |
| **學理基準** | [R14] RAG、[R15] DPR、[R16] Self-RAG |
| **可直接整合的 SDK 模組** | • [LlamaIndex](https://docs.llamaindex.ai/) Retrievers(Vector / Keyword / Hybrid)<br>• [LangChain Retrievers](https://python.langchain.com/docs/modules/data_connection/retrievers/)(Multi-Vector、ParentDocument、ContextualCompression)<br>• [Haystack](https://github.com/deepset-ai/haystack) pipelines<br>• Vector DB 客戶端:[Chroma](https://github.com/chroma-core/chroma) / [Weaviate](https://github.com/weaviate/weaviate) / [Qdrant](https://github.com/qdrant/qdrant) / [Milvus](https://github.com/milvus-io/milvus)<br>• [FAISS](https://github.com/facebookresearch/faiss) |
| **對應本專案文件** | [03-agentic-orchestration/context-and-memory.md](03-agentic-orchestration/context-and-memory.md) §跨節點傳遞契約 |

### 3.4 Reflect(反思)

| 面向 | 內容 |
|------|------|
| **節點職責** | 對 Action 輸出做品質審查、檢查是否符合目標、必要時觸發回到 Plan 重新規劃 |
| **學理基準** | [R17] Reflexion、[R18] Self-Refine、[R19] Constitutional AI、[R16] Self-RAG |
| **可直接整合的 SDK 模組** | • [LangChain](https://python.langchain.com/) self-critique / CriticAgent chains<br>• [DSPy](https://github.com/stanfordnlp/dspy) `SelfRefine` / `Suggest`<br>• [AutoGen](https://github.com/microsoft/autogen) Critic agent pattern<br>• [Guardrails AI](https://github.com/guardrails-ai/guardrails) |
| **對應本專案文件** | [03-agentic-orchestration/react-workflow-routing.md](03-agentic-orchestration/react-workflow-routing.md) §回環與終止條件 |

### 3.5 Action(行動)

| 面向 | 內容 |
|------|------|
| **節點職責** | 呼叫外部工具或執行副作用(API 呼叫、檔案寫入、控制硬體),產出實際結果 |
| **學理基準** | [R08] ReAct、[R20] Toolformer、[R21] Gorilla、[R22] ToolLLM、[R23] MCP |
| **可直接整合的 SDK 模組** | • [OpenAI Function Calling / Tools API](https://platform.openai.com/docs/guides/function-calling)<br>• [LangChain Tools](https://python.langchain.com/docs/modules/tools/)(`Tool` / `StructuredTool`)<br>• [AutoGen](https://github.com/microsoft/autogen) function map<br>• [LlamaIndex Tools](https://docs.llamaindex.ai/en/stable/module_guides/deploying/agents/tools/) / `FunctionTool`<br>• [MCP Servers](https://modelcontextprotocol.io/)(Anthropic 規範,生態成長中) |
| **對應本專案文件** | [03-agentic-orchestration/react-workflow-routing.md](03-agentic-orchestration/react-workflow-routing.md) §跨節點異質模型調度 |

---

## 4. 跨節點基礎設施(支撐五大節點)

以下能力不屬於單一節點,而是讓五大節點能在邊緣叢集上跑得起來的底層支撐。

| 主題 | 學理基準 | 本專案文件 |
|------|----------|------------|
| 分層記憶體與 Token 過期 | [R05] [R06] [R07] | [03-agentic-orchestration/context-and-memory.md](03-agentic-orchestration/context-and-memory.md) |
| KV Cache 與動態 Offload | [R02] | [03-agentic-orchestration/dynamic-offload-engine.md](03-agentic-orchestration/dynamic-offload-engine.md) |
| SLA 量測與遙測 | [R03] [R04] | [04-observability-dashboard/telemetry-metrics.md](04-observability-dashboard/telemetry-metrics.md) |
| Multi-Model Dashboard | [R25] [R26] [R27] | [04-observability-dashboard/visualization-ui.md](04-observability-dashboard/visualization-ui.md) |
| OpenAI 相容介面 | [R01] | [05-api-reference/openai-compatible-api.md](05-api-reference/openai-compatible-api.md) |
| 圖狀態機路由 | [R24] | [03-agentic-orchestration/react-workflow-routing.md](03-agentic-orchestration/react-workflow-routing.md) |

---

## 5. 與上游 Model Card 的邊界

本專案 **不實作** SLA 自動化基準測試 Pipeline。所有 TTFT / Peak Memory / Soak Test 的量測與認證履歷產出,皆由上游儲存庫 [`R300-AI/amd-ryzen-ai-benchmark`](https://github.com/R300-AI/amd-ryzen-ai-benchmark) 負責,其方法論對齊 [R03] [R04]。

本專案僅消費其產出,銜接契約見 [02-model-card-contract/upstream-integration.md](02-model-card-contract/upstream-integration.md)。
