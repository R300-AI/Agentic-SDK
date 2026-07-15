# Action Modules

Action 模組負責把前面節點收集到的資訊轉成 workflow 的最終輸出。現行程式碼中可直接使用的 Action 節點只有兩個：`DirectAnswerAction` 與 `CompletionAction`。

## 已實作模組

| 模組 | 需要模型 | 下一節點 | 主要用途 |
| --- | --- | --- | --- |
| `DirectAnswerAction` | 否 | `END` | 直接把最近一次檢索結果整理成答案 |
| `CompletionAction` | 是 | `END` | 透過 OpenAI-compatible client 或 Foundry 生成最終回答 |

## DirectAnswerAction

`DirectAnswerAction` 是 README 第一個快速開始範例使用的最小輸出模組。它不依賴生成模型，只會讀取 `latest_retrieved_content`，然後把該內容原樣提升為最終答案；這屬於 deterministic answer composition 的工程型基線，沒有對應單一研究論文。

### 初始化參數

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `（無）` | `-` | `-` | `DirectAnswerAction` 沒有 `__init__` 配置參數。 |

## CompletionAction

`CompletionAction` 會把使用者問題與最近一次檢索上下文組成 chat completion 請求，交給 OpenAI-compatible client、AMD upstream，或 Azure Foundry deployment 生成自然語言答案。它屬於 generative completion 類型的節點，論文背景可參考 GPT 類 few-shot/completion 範式的代表作 [Arxiv](https://arxiv.org/abs/2005.14165)。

### 初始化參數

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `backend` | `str | None` | `settings.workflow_action_backend`，再退回 `"upstream"` | 後端模式，只接受 `upstream` 或 `foundry`。 |
| `settings` | `Settings | None` | `get_settings()` | 設定來源；未提供時讀全域設定。 |
| `model` | `str | None` | `None` | 顯式指定模型名。upstream 下會傳給 OpenAI-compatible API；foundry 下會作為 model selector 使用。 |
| `upstream` | `UpstreamClient | None` | `None` | upstream 專用。注入 SDK 自己的 `UpstreamClient`；與 `base_url`、`client` 互斥。 |
| `base_url` | `str | None` | `None` | upstream 專用。用此 URL 建立內部 `UpstreamClient`；與 `upstream`、`client` 互斥。 |
| `client` | `Any` | `None` | 可直接注入 chat completions client。README 的 `openai_client` 就是走這個參數；在 upstream 下代表 OpenAI-compatible client，在 foundry 下可注入既有 Azure OpenAI client。 |
| `endpoint` | `str | None` | `None` | foundry 專用。覆蓋 Azure Foundry endpoint。 |
| `deployment` | `str | None` | `None` | foundry 專用。覆蓋 deployment；upstream 下若 `model` 未給，會被拿來當 model fallback。 |
| `api_key` | `str | None` | `None` | foundry 專用。覆蓋 Azure Foundry API key。 |
| `temperature` | `float | None` | `None` | 若提供，會傳給 completion API。 |
| `system_prompt` | `str | None` | 內建 `DEFAULT_SYSTEM_PROMPT` | 覆蓋預設 system prompt。 |
| `idle_timeout_sec` | `float` | `30.0` | foundry 串流路徑的 read idle timeout。 |