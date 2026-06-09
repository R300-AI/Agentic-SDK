# Python SDK Integration — Agentic SDK Python 套件使用說明

> 受眾：應用端開發者(已熟悉 OpenAI Python SDK / LangChain)
> 目的：示範如何在零侵入的前提下,把現有 Python 應用切換到 Agentic SDK。

## 一、最小切換成本路徑

> **核心承諾:現有應用只改一個變數,就能跑在 TSiP 國產晶片上。**

### 1. OpenAI Python SDK

```python
from openai import OpenAI

client = OpenAI(
    base_url="http://<gateway>:8080/v1",   # ← 唯一改動
    api_key="dummy"                          # PoC 階段不驗 token
)

response = client.chat.completions.create(
    model="llama-3-8b-instruct@ryzenai-npu",
    messages=[{"role": "user", "content": "Hello"}]
)
print(response.choices[0].message.content)
```

### 2. LangChain

```python
from langchain_openai import ChatOpenAI

llm = ChatOpenAI(
    base_url="http://<gateway>:8080/v1",   # ← 唯一改動
    api_key="dummy",
    model="llama-3-8b-instruct@ryzenai-npu"
)

result = llm.invoke("Hello")
```

LangChain 的 Tool calling、Agent、Memory 等高階抽象不需修改,因為它們皆建構於 `ChatOpenAI` 之上。

### 3. AutoGen

```python
from autogen import AssistantAgent

assistant = AssistantAgent(
    name="assistant",
    llm_config={
        "config_list": [{
            "model": "llama-3-8b-instruct@ryzenai-npu",
            "base_url": "http://<gateway>:8080/v1",   # ← 唯一改動
            "api_key": "dummy",
        }]
    }
)
```

## 二、Agentic SDK 原生套件(可選)

對於希望取得 Agentic SDK 進階能力(動態 Offload、跨節點工作流、遙測 metadata)的使用者,提供原生 Python 套件:

```bash
pip install agentic-sdk
```

> 註:套件名稱與發布通道於 MVP 階段確定;PoC 階段先以 source install 形式提供。

### 範例:取得遙測 metadata

```python
from agentic_sdk import AgenticClient

client = AgenticClient(base_url="http://localhost:8080")

response, metadata = client.chat_with_metadata(
    model="gemma3-4b-npu",   # 上游 api.py 啟動時指定的模型 ID
    messages=[{"role": "user", "content": "Hello"}]
)

print(response.content)
print(f"上游模型: {metadata.upstream_model_id}")
print(f"工作流 ID: {metadata.workflow_id}")
print(f"行經節點: {metadata.nodes_visited}")
print(f"TTFT: {metadata.ttft_ms} ms")
```

`metadata` 內容對應 [05-api-reference/openai-compatible-api.md](openai-compatible-api.md) 中 `x-agentic-metadata` 與 SSE metadata chunk 的內容,使用者不必自行解析 header。

### 範例:跨節點工作流(進階)

```python
from agentic_sdk import Workflow, Node, NodeOutput

class PerceiveNode(Node):
    name = "perceive"
    required_capability = "vision"

    def run(self, ctx, inputs):
        # 呼叫具備 vision 能力的模型分析輸入
        result = ctx.llm.invoke(inputs["image"])
        return NodeOutput(next_node="plan", payload={"observation": result})

workflow = Workflow(nodes=[
    PerceiveNode(),
    PlanNode(),
    RetrieveNode(),
    ReflectNode(),
    ActionNode(),
])
result = workflow.run(initial_input={"image": "..."})
```

完整節點抽象與 Perceive / Plan / Retrieve / Reflect / Action 五大節點的路由語意,見 [03-agentic-orchestration/react-workflow-routing.md](../03-agentic-orchestration/react-workflow-routing.md);各節點的學理基準對齊 [docs/README.md §3](../README.md)。

## 三、PoC 階段套件範圍

| 模組 | 狀態 |
|------|------|
| `AgenticClient`(包裝 OpenAI client + metadata 解析) | ✅ PoC 必做 |
| `Workflow` / `Node` 編排原語 | ⚠️ PoC 提供最小可用版,延後優化 |
| LangChain `AgenticChatOpenAI` 子類(自動帶 metadata) | ❌ MVP 後評估 |
| LlamaIndex 整合 | ❌ MVP 後評估 |

## 四、相依性與安裝環境

| 項目 | 要求 |
|------|------|
| Python | ≥ 3.10 |
| OpenAI Python SDK | ≥ 1.0 |
| 作業系統 | 應用端不限,Gateway 端見部署文件 |

應用端對硬體 **無任何要求**——本套件在應用端只做 HTTP 呼叫與 metadata 解析,所有硬體相關運算皆發生於上游 `api.py` 行程內。

## 五、常見問題

**Q:可否同時使用 Agentic SDK 與 OpenAI 官方雲端服務?**
A:可以。建立兩個 `OpenAI` client 各自指向不同 `base_url` 即可。Agentic SDK 的 model ID 沿用上游 `api.py` 命名(如 `gemma3-4b-npu`),不會與 OpenAI 官方模型衝突。

**Q:模型回傳速度比預期慢?**
A:檢查 `metadata.ttft_ms` 與上游 README 標示的實測值差距。若顯著偏高,代表上游推論伺服器當下壓力過大或硬體未正確使用 NPU/iGPU 加速,請依上游 README 重新確認 conda 環境與驅動版本。

**Q:可否取得目前所有可用模型?**
A:`client.models.list()`(OpenAI SDK 標準方法)即可,回傳清單為上游 `api.py` 當前載入的模型。
