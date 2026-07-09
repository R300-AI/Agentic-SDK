# Perceive Modules

Perceive 模組負責接住原始輸入，整理成 workflow 後續節點可直接使用的理解結果。MVP 先提供一個 README 最小入口，外加一個正式模型型感知模組。

## MVP 模組

| 模組 | 需要模型 | 讀取 | 寫入 | 定位 |
| --- | --- | --- | --- | --- |
| InputPerceive | 否 | `input` | `perceived_input` | README 最小入口 |
| LLM Perceive | 是 | `input` | `perceived_input`、`query` | 正式文字理解模組 |

## InputPerceive

這是 README 範例用來建立第一條 workflow 的最小感知模組。它不要求模型，只負責把外部傳入的主輸入交給後續節點。

**對應論文：** 無單一對應論文；此模組屬 SDK 的最小工程入口，重點在 workflow 對接而不是特定研究方法。

### 建構參數

無必填模型參數。MVP 公開敘事只保證它能接住輸入並轉成 `perceived_input`。

### 輸入契約

必須可讀取 `input`。

### 輸出契約

至少寫入 `perceived_input`。

## LLM Perceive

!!! info "模型規格"
    此模組一律使用 `OpenAI SDK form`，不以供應商專屬呼叫格式寫入公開文件。

**對應論文：** [Language Models are Few-Shot Learners](https://arxiv.org/abs/2005.14165)

| 參數 | 是否必填 | 說明 |
| --- | --- | --- |
| `client` | 是 | OpenAI SDK client 實例。 |
| `model` | 是 | 模型名稱，沿用 OpenAI SDK 的模型指定方式。 |
| `system_prompt` | 否 | 定義輸入理解任務與輸出邊界。 |
| `output_schema` | 否 | 限制感知結果結構，讓後續節點更容易穩定讀取。 |

LLM Perceive 通常會從 `input` 生成較乾淨的 `perceived_input`，必要時也可同步產出給 retrieve 使用的 `query`。

如果你只是想搭出 README 的第一條流程，用 InputPerceive 即可；若需要穩定文字理解，再升級成 LLM Perceive。