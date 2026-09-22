# Perceive

Perceive 模組負責把原始輸入整理成 workflow 後續節點可直接消費的感知結果。這一頁先定義 Perceive 家族處理哪些輸入型態，再依序展開目前文件採用的四個標準模組。每個模組會先列出建立物件時使用的初始化參數，再列出 workflow 執行時接收的標準輸入參數；整理後寫入 `Entities` 的欄位，會回到 [Module Family](index.md) 的中央定義理解。輸入來源包含純文字、結構化欄位與圖片檔，圖片格式支援 `image/png`、`image/jpeg`、`image/webp`。需要模型的 Perceive 模組會讀取 `MemoryStore` 的完整對話歷史；實際採用的記憶類型可以是 `InContextMemory`，也可以是同層可互換的 `CrossContextMemory`，但仍以最新 user turn 當成本輪要整理的焦點。

## PassThroughPerceive

參考論文：無特定 arXiv 對應；此模組是工程化 baseline。

`PassThroughPerceive` 將最新一輪使用者輸入直接整理成查詢內容，交給後續節點接手。它適合 README 的最小流程，也適合作為文字型流程的直接入口。這個模組代表的是最短路徑：收到新訊息後，先把可查詢的內容穩定交出去。

### 初始化參數

| 參數 | 型態 | 必填 | 預設值 | 說明 |
| --- | --- | --- | --- | --- |
| `input_label` | `string` | 否 | `""` | 寫入感知結果 metadata 的輸入標籤，方便後續節點或觀測資料辨識來源。 |

### 標準輸入參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `user_message` | `string` | `"請介紹 Agentic SDK"` | 本輪最新的使用者文字。 |
| `memory` | `MemoryStore` | `user -> assistant -> user ...` | 模組讀取完整對話歷史的共同抽象；實際型別可以是 `InContextMemory` 或 `CrossContextMemory`。 |

## TextPerceive

參考論文：[ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629)

`TextPerceive` 依文字內容做語意判讀，將輸入整理成後續可用的查詢、標籤與摘要。當流程需要的不只是原句，而是對需求做一次語意整理時，就會接到這個模組。模型輸入會包含完整對話歷史，再加上本模組自己的 guidance 與 fields 設定。

此模組需要明確的 OpenAI-compatible 連線設定：`api_key`、`base_url`、`model`。模組會在內部建立 OpenAI client，不讀取全域預設模型。

### 初始化參數

| 參數 | 型態 | 必填 | 預設值 | 說明 |
| --- | --- | --- | --- | --- |
| `api_key` | `string` | 是 | 無 | OpenAI-compatible 端點金鑰；例如 Ollama 可使用 `"ollama"` 或其他非空值。 |
| `base_url` | `string` | 是 | 無 | OpenAI-compatible API base URL，例如 `"http://localhost:11434/v1/"`。 |
| `model` | `string` | 是 | 無 | 每次推論呼叫送出的模型名稱，例如 `"llama3.2:1b"`。 |
| `welcome_message` | `string` | 否 | `""` | 給 UI 或 metadata 使用的提示文字，不會覆蓋使用者輸入。 |
| `options` | `array<object>` | 否 | `[]` | 可選意圖或服務範圍，供模型理解背景；不會直接覆蓋模型判斷。 |
| `importance` | `number` | 否 | `1.0` | 寫入 memory entry 的重要性權重。 |

### 標準輸入參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `user_message` | `string` | `"我無法登入後台，請幫我整理問題重點"` | 本輪最新的使用者文字。 |
| `memory` | `MemoryStore` | `user -> assistant -> user ...` | 模型會直接讀取的完整對話歷史；實際型別可以是 `InContextMemory` 或 `CrossContextMemory`。 |
| `input_options` | `array<object>` | `[]` | 可選項目；沒有選項時固定 `[]`。 |
| `input_fields` | `object` | `{}` | 結構化欄位；沒有欄位時固定 `{}`。 |
| `input_images` | `array<object>` | `[]` | 圖片清單；沒有圖片時固定 `[]`。 |

## TextImagePerceive

參考論文：[Flamingo: a Visual Language Model for Few-Shot Learning](https://arxiv.org/abs/2204.14198)

`TextImagePerceive` 將文字與圖片內容一起整理成後續可用的查詢與摘要。當流程同時需要讀取文字與圖片時，這個模組會把兩類資訊整合成後續可用的感知結果，支援 `image/png`、`image/jpeg`、`image/webp` 三種格式。模型輸入同樣會保留前面各輪的 user / assistant 歷史，最後一輪 user turn 則可轉成 OpenAI content parts。

此模組需要明確的 OpenAI-compatible 連線設定：`api_key`、`base_url`、`model`，且模型端點需支援圖文輸入。

### 初始化參數

| 參數 | 型態 | 必填 | 預設值 | 說明 |
| --- | --- | --- | --- | --- |
| `api_key` | `string` | 是 | 無 | OpenAI-compatible 端點金鑰。 |
| `base_url` | `string` | 是 | 無 | OpenAI-compatible API base URL。 |
| `model` | `string` | 是 | 無 | 每次推論呼叫送出的模型名稱；端點需支援圖文輸入。 |
| `welcome_message` | `string` | 否 | `""` | 給 UI 或 metadata 使用的提示文字。 |
| `options` | `array<object>` | 否 | `[]` | 可選意圖或服務範圍，供模型理解背景。 |
| `image_instruction` | `string` | 否 | `""` | 告訴模型看圖時要特別留意什麼。 |
| `importance` | `number` | 否 | `1.0` | 寫入 memory entry 的重要性權重。 |

### 標準輸入參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `user_message` | `string` | `"請根據這張截圖整理錯誤訊息"` | 本輪最新的使用者文字。 |
| `memory` | `MemoryStore` | `user -> assistant -> user ...` | 模型會直接讀取的完整對話歷史；實際型別可以是 `InContextMemory` 或 `CrossContextMemory`。 |
| `input_options` | `array<object>` | `[]` | 可選項目；沒有選項時固定 `[]`。 |
| `input_fields` | `object` | `{}` | 結構化欄位；沒有欄位時固定 `{}`。 |
| `input_images` | `array<object>` | `[{"mime_type":"image/png","name":"error-screen.png","content_ref":"blob://error-screen.png"}]` | 圖片清單；只允許 `image/png`、`image/jpeg`、`image/webp`。 |

## VoiceTextPerceive

參考論文：無特定 arXiv 對應；此模組是語音互動的工程化入口。

`VoiceTextPerceive` 讓使用者用講的代替打字。它與其他 Perceive 模組的差別在於**輸入不是在被呼叫時才出現的**——聲音在使用者想講的時候到，不在 workflow 詢問的時候到。模組因此持有一條長連線，把聽到的話累積起來，等自己這一輪被呼叫時交出去。

它只負責聽。說話屬於 Action，而且轉寫與語音合成本來就不共用連線；理由記在 [ADR 0001](../adr/0001-where-voice-lives.md)。

**安靜時不會上傳任何東西。** 純靜音與說話計費相同，而且會被服務辨識成沒有人說過的字，因此模組在送出前先以音量門檻過濾。這是正確性而非最佳化：不過濾的話，安靜的房間會持續產生假的使用者輸入。

### 初始化參數

| 參數 | 型態 | 必填 | 預設值 | 說明 |
| --- | --- | --- | --- | --- |
| `transport` | `AudioInputTransport` | **是** | 無 | 音訊來源。在模組外面建好再交進來——模組沒有辦法自己生一個，因此也沒有一份廠商清單。測試以假傳輸驅動整條流程，不需網路與憑證。 |
| `speech_threshold` | `int` | 否 | `500` | 判定為說話的音量下限（16 位元取樣的 RMS）。吵雜環境調高。 |
| `hangover_seconds` | `float` | 否 | `0.8` | 說話結束後仍繼續送出的安靜長度。服務靠聽到靜音判定一句話結束，切太乾淨就永遠等不到轉寫。 |

### 話比 run() 先到

`VoiceTextPerceive` 實作 `pending_input()`：它把聽到的話先收著，`Workflow.run()` 不必再被告知一次。這個約定不是語音專屬，任何模組都可以實作——詳見[工作流程](../workflow/index.md)。

### 音訊來源怎麼建

SDK 附的是 `RealtimeTranscription`，走 OpenAI SDK 的即時客戶端：

```python
from agentic_sdk.audio.realtime import RealtimeTranscription

listening = RealtimeTranscription(api_key=..., base_url=..., model=...)
perceive = VoiceTextPerceive(transport=listening)
```

| 參數 | 型態 | 必填 | 預設值 | 說明 |
| --- | --- | --- | --- | --- |
| `model` | `string` | 是 | 無 | 轉寫模型名稱。 |
| `api_key` | `string` | 否 | `None` | 端點金鑰。 |
| `base_url` | `string` | 否 | `None` | 端點位址；留空時使用 OpenAI 的預設位址。 |
| `language` | `string` | 否 | `"zh"` | 轉寫語言。 |
| `turn_detection` | `dict` | 否 | `server_vad`，靜音 300 毫秒 | 服務判定語句結束的方式。`server_vad` 依固定的靜音長度；`semantic_vad` 由模型判斷該停頓屬於句中換氣或句末，並以 `eagerness` 調整等待長度。 |
| `connect_timeout` | `float` | 否 | `30.0` | 等待服務接受連線的秒數上限，逾時拋出 `TimeoutError`。 |

`turn_detection` 決定服務怎麼判斷一句話結束——靠固定的靜音長度，或靠模型判斷這個停頓是換氣還是句末。它是**傳輸的參數**，不是模組的：模組只管送什麼上去。

**SDK 附的傳輸只會連 OpenAI**，不收 client、也不收廠商參數。端點的連線方式不同時，**覆蓋一個方法**：

```python
class MyTranscription(RealtimeTranscription):
    """我自己接的端點。SDK 不知道也不負責這一家。"""

    def _open(self):
        return SomeClient(...).beta.realtime.connect(model=self._model)
```

開連線之後的一切——session 設定、送音訊、事件分派——全部繼承。對模組而言，自訂的實作和 SDK 附的**完全沒有分別**。詳見 ADR-0003。

### 標準輸入參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `user_message` | `string` | `"請介紹 Agentic SDK"` | 本輪最新的使用者文字。 |
| `memory` | `MemoryStore` | `user -> assistant -> user ...` | 模組讀取完整對話歷史的共同抽象；實際型別可以是 `InContextMemory` 或 `CrossContextMemory`。 |

## TextPerceive

參考論文：[ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629)

`TextPerceive` 依文字內容做語意判讀，將輸入整理成後續可用的查詢、標籤與摘要。當流程需要的不只是原句，而是對需求做一次語意整理時，就會接到這個模組。模型輸入會包含完整對話歷史，再加上本模組自己的 guidance 與 fields 設定。

此模組需要明確的 OpenAI-compatible 連線設定：`api_key`、`base_url`、`model`。模組會在內部建立 OpenAI client，不讀取全域預設模型。

### 初始化參數

| 參數 | 型態 | 必填 | 預設值 | 說明 |
| --- | --- | --- | --- | --- |
| `api_key` | `string` | 是 | 無 | OpenAI-compatible 端點金鑰；例如 Ollama 可使用 `"ollama"` 或其他非空值。 |
| `base_url` | `string` | 是 | 無 | OpenAI-compatible API base URL，例如 `"http://localhost:11434/v1/"`。 |
| `model` | `string` | 是 | 無 | 每次推論呼叫送出的模型名稱，例如 `"llama3.2:1b"`。 |
| `welcome_message` | `string` | 否 | `""` | 給 UI 或 metadata 使用的提示文字，不會覆蓋使用者輸入。 |
| `options` | `array<object>` | 否 | `[]` | 可選意圖或服務範圍，供模型理解背景；不會直接覆蓋模型判斷。 |
| `importance` | `number` | 否 | `1.0` | 寫入 memory entry 的重要性權重。 |

### 標準輸入參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `user_message` | `string` | `"我無法登入後台，請幫我整理問題重點"` | 本輪最新的使用者文字。 |
| `memory` | `MemoryStore` | `user -> assistant -> user ...` | 模型會直接讀取的完整對話歷史；實際型別可以是 `InContextMemory` 或 `CrossContextMemory`。 |
| `input_options` | `array<object>` | `[]` | 可選項目；沒有選項時固定 `[]`。 |
| `input_fields` | `object` | `{}` | 結構化欄位；沒有欄位時固定 `{}`。 |
| `input_images` | `array<object>` | `[]` | 圖片清單；沒有圖片時固定 `[]`。 |

## TextImagePerceive

參考論文：[Flamingo: a Visual Language Model for Few-Shot Learning](https://arxiv.org/abs/2204.14198)

`TextImagePerceive` 將文字與圖片內容一起整理成後續可用的查詢與摘要。當流程同時需要讀取文字與圖片時，這個模組會把兩類資訊整合成後續可用的感知結果，支援 `image/png`、`image/jpeg`、`image/webp` 三種格式。模型輸入同樣會保留前面各輪的 user / assistant 歷史，最後一輪 user turn 則可轉成 OpenAI content parts。

此模組需要明確的 OpenAI-compatible 連線設定：`api_key`、`base_url`、`model`，且模型端點需支援圖文輸入。

### 初始化參數

| 參數 | 型態 | 必填 | 預設值 | 說明 |
| --- | --- | --- | --- | --- |
| `api_key` | `string` | 是 | 無 | OpenAI-compatible 端點金鑰。 |
| `base_url` | `string` | 是 | 無 | OpenAI-compatible API base URL。 |
| `model` | `string` | 是 | 無 | 每次推論呼叫送出的模型名稱；端點需支援圖文輸入。 |
| `welcome_message` | `string` | 否 | `""` | 給 UI 或 metadata 使用的提示文字。 |
| `options` | `array<object>` | 否 | `[]` | 可選意圖或服務範圍，供模型理解背景。 |
| `image_instruction` | `string` | 否 | `""` | 告訴模型看圖時要特別留意什麼。 |
| `importance` | `number` | 否 | `1.0` | 寫入 memory entry 的重要性權重。 |

### 標準輸入參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `user_message` | `string` | `"請根據這張截圖整理錯誤訊息"` | 本輪最新的使用者文字。 |
| `memory` | `MemoryStore` | `user -> assistant -> user ...` | 模型會直接讀取的完整對話歷史；實際型別可以是 `InContextMemory` 或 `CrossContextMemory`。 |
| `input_options` | `array<object>` | `[]` | 可選項目；沒有選項時固定 `[]`。 |
| `input_fields` | `object` | `{}` | 結構化欄位；沒有欄位時固定 `{}`。 |
| `input_images` | `array<object>` | `[{"mime_type":"image/png","name":"error-screen.png","content_ref":"blob://error-screen.png"}]` | 圖片清單；只允許 `image/png`、`image/jpeg`、`image/webp`。 |

## VoiceTextPerceive

參考論文：無特定 arXiv 對應；此模組是語音互動的工程化入口。

`VoiceTextPerceive` 讓使用者用講的代替打字。它與其他 Perceive 模組的差別在於**輸入不是在被呼叫時才出現的**——聲音在使用者想講的時候到，不在 workflow 詢問的時候到。模組因此持有一條長連線，把聽到的話累積起來，等自己這一輪被呼叫時交出去。

它只負責聽。說話屬於 Action，而且轉寫與語音合成本來就不共用連線；理由記在 [ADR 0001](../adr/0001-where-voice-lives.md)。

**安靜時不會上傳任何東西。** 純靜音與說話計費相同，而且會被服務辨識成沒有人說過的字，因此模組在送出前先以音量門檻過濾。這是正確性而非最佳化：不過濾的話，安靜的房間會持續產生假的使用者輸入。

### 初始化參數

| 參數 | 型態 | 必填 | 預設值 | 說明 |
| --- | --- | --- | --- | --- |
| `transport` | `AudioInputTransport` | **是** | 無 | 音訊來源。在模組外面建好再交進來——模組沒有辦法自己生一個，因此也沒有一份廠商清單。測試以假傳輸驅動整條流程，不需網路與憑證。 |
| `speech_threshold` | `int` | 否 | `500` | 判定為說話的音量下限（16 位元取樣的 RMS）。吵雜環境調高。 |
| `hangover_seconds` | `float` | 否 | `0.8` | 說話結束後仍繼續送出的安靜長度。服務靠聽到靜音判定一句話結束，切太乾淨就永遠等不到轉寫。 |

### 話比 run() 先到

`VoiceTextPerceive` 實作 `pending_input()`：它把聽到的話先收著，`Workflow.run()` 不必再被告知一次。這個約定不是語音專屬，任何模組都可以實作——詳見[工作流程](../workflow/index.md)。

### 音訊來源怎麼建

SDK 附的是 `RealtimeTranscription`，走 OpenAI SDK 的即時客戶端：

```python
from agentic_sdk.audio.realtime import RealtimeTranscription

listening = RealtimeTranscription(api_key=..., base_url=..., model=...)
perceive = VoiceTextPerceive(transport=listening)
```

| 參數 | 型態 | 必填 | 預設值 | 說明 |
| --- | --- | --- | --- | --- |
| `model` | `string` | 是 | 無 | 轉寫模型名稱。 |
| `api_key` | `string` | 否 | `None` | 端點金鑰。 |
| `base_url` | `string` | 否 | `None` | 端點位址；留空時使用 OpenAI 的預設位址。 |
| `language` | `string` | 否 | `"zh"` | 轉寫語言。 |
| `turn_detection` | `dict` | 否 | `server_vad`，靜音 300 毫秒 | 服務判定語句結束的方式。`server_vad` 依固定的靜音長度；`semantic_vad` 由模型判斷該停頓屬於句中換氣或句末，並以 `eagerness` 調整等待長度。 |
| `connect_timeout` | `float` | 否 | `30.0` | 等待服務接受連線的秒數上限，逾時拋出 `TimeoutError`。 |

`turn_detection` 決定服務怎麼判斷一句話結束——靠固定的靜音長度，或靠模型判斷這個停頓是換氣還是句末。它是**傳輸的參數**，不是模組的：模組只管送什麼上去。

### 標準輸入參數

| 參數 | 型態 | 格式 | 說明 |
| --- | --- | --- | --- |
| `pcm16` | `bytes` | 16 位元單聲道 PCM | 透過 `hear()` 傳入的麥克風片段。低於門檻的片段不會離開程序。 |

### 感知結果

寫入 `PERCEIVED` context entry，`metadata.spoken` 標示這一輪的內容是講出來的還是打字的。若呼叫 `run()` 時同時傳入文字訊息，以文字為準——對話記錄與感知結果必須對同一輪說同一件事。
