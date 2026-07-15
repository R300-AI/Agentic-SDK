# Perceive

Perceive 模組負責把原始輸入整理成 workflow 後續節點可直接消費的理解結果。依這套文件的流程定義，Perceive 完成後會交給下一個節點；若 workflow 有接 `Plan`，則通常由 `Plan` 決定後續路徑。這一頁先列出可直接使用的 `InputPerceive`、`RuleBasedPerceive` 與 `LLMBasedPerceive`，再補上 `StructuredPerceive` 與 `MultimodalPerceive` 這兩種常見的感知物件型態，方便你定義自訂模組。

## InputPerceive

`InputPerceive` 是 README 第一與第三個快速開始範例使用的最小感知模組。它不做語意推理，只會將 `user_message` 直接整理成 `perceived_input` 與 `query` 供後續檢索使用；這是 SDK 的工程型入口，沒有對應單一研究論文。

### 初始化參數

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `（無）` | `-` | `-` | `InputPerceive` 沒有 `__init__` 配置參數。 |

## RuleBasedPerceive

`RuleBasedPerceive` 以輕量規則將輸入分成 `question`、`diagnose` 或 `general` 等 intent，適合不依賴外部模型的基線流程。它屬於 heuristic intent classification，沒有直接對應單一論文。

### 初始化參數

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `welcome_message` | `str` | `""` | 若提供，會寫入 `PERCEIVED` metadata，供 UI 顯示初始提示。 |
| `options` | `list[dict] | None` | `None` | 可選選項列表；若 user input 剛好命中 `label` 或 `value`，會優先採用該 option 的 `intent` 或 `value`。 |
| `importance` | `float` | `1.0` | 若 workflow 有接 `memory_store`，此值會寫入 `MemoryEntry.importance`。 |

## LLMBasedPerceive

`LLMBasedPerceive` 會把使用者輸入與可選項目一起交給 LLM，要求模型只回 JSON，輸出 `intent` 與 `summary`。這屬於 LLM-based intent understanding，可參考 in-context/few-shot 類生成式理解方法的代表作 [Arxiv](https://arxiv.org/abs/2005.14165)。

### 初始化參數

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `welcome_message` | `str` | `""` | 若提供，會寫入 `PERCEIVED` metadata，供 UI 顯示初始提示。 |
| `options` | `list[dict] | None` | `None` | 可選選項列表，會作為 `available_options` 背景資訊送給 LLM。 |
| `importance` | `float` | `1.0` | 若 workflow 有接 `memory_store`，此值會寫入 `MemoryEntry.importance`。 |
| `foundry_client` | `FoundryClient | None` | `get_foundry_client()` | 注入既有 Foundry client；未提供時會自建。 |

## StructuredPerceive

`StructuredPerceive` 會把表單欄位、量測欄位、補充觀察或其他結構化輸入整理成統一的輸入摘要，適合 LaNew 與 ICOPE 這類以欄位資料為主的流程。方法定位上可視為把結構化輸入轉成後續 reasoning 可用的摘要，流程設計可參考 ReAct 的輸入整理思路 [Arxiv](https://arxiv.org/abs/2210.03629)。

### 初始化參數

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `field_schema` | `list[dict] | None` | `None` | 欄位定義與欄位順序，用來決定哪些輸入要保留。 |
| `required_fields` | `list[str] | None` | `None` | 需要優先檢查的欄位名稱。 |
| `summary_template` | `str | None` | `None` | 若提供，控制輸入摘要的輸出格式。 |

## MultimodalPerceive

`MultimodalPerceive` 會把文字、圖片、附件或其他多模態輸入整理成統一感知結果，適合 LaNew 的足測報表與 BCI 的多模態輸入。多模態感知的做法可參考 BLIP-2 [Arxiv](https://arxiv.org/abs/2301.12597) 與 LLaVA [Arxiv](https://arxiv.org/abs/2304.08485)。

### 初始化參數

| 參數 | 型態 | 預設值 | 說明 |
| --- | --- | --- | --- |
| `client` | `Any` | `None` | 視覺或多模態模型 client。 |
| `system_prompt` | `str | None` | `None` | 控制多模態感知摘要的輸出方式。 |
| `attachment_policy` | `str` | `"images_only"` | 附件處理策略，例如只讀圖片、讀全文或忽略附件。 |
| `max_summary_chars` | `int` | `500` | 控制輸入摘要長度。 |