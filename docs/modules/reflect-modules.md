# Reflect

Reflect 是規劃模組在行動前使用的一站。規劃模組把工作送過來，反思模組留下一份回報，執行一律回到規劃模組，由規劃模組決定重查、再送反思或行動。反思模組不決定流程去向，也不評價回答，因為回答要到行動才產生。內建的兩個模組確認規劃與檢索有沒有正常完成。每個模組會先列出建立物件時使用的初始化參數；讀寫的中間欄位統一回到 [Module Family](index.md) 的 `Entities` 中央定義理解。

兩個內建模組的回報格式相同：

| 位置 | 欄位 | 內容 |
| --- | --- | --- |
| `payload` | `reflect_verdict` | `pass` 或 `fail`。 |
| `reflection` 條目的 metadata | `verdict` | 與 `reflect_verdict` 相同。 |
| `reflection` 條目的 metadata | `reason` | 判定原因。 |
| `reflection` 條目的 metadata | `suggestion` | 給規劃模組的建議；沒有建議時不帶這個欄位。 |
| `reflection` 條目的 metadata | `strategy` | `evidence_check` 或 `plan_check`。 |

`NextStepPlan` 在下一次造訪時讀這份回報。兩個模組都有 `description` 屬性，說明它確認什麼；`NextStepPlan` 沒有收到 `reflect_description` 時，把這段說明交給模型。

## EvidenceCheckReflect

參考論文：[CRITIC: Large Language Models Can Self-Correct with Tool-Interactive Critiquing](https://arxiv.org/abs/2305.11738)

`EvidenceCheckReflect` 用規則確認最近一次檢索有沒有找到內容，不呼叫模型。它只讀最近一次 `retrieved` 條目的 `hit_count`：

| 最近一次檢索 | `verdict` |
| --- | --- |
| `hit_count` 為 0 | `fail` |
| `hit_count` 大於 0 | `pass` |
| 沒有檢索條目，或條目沒有 `hit_count`，例如 `PassThroughRetrieve` | `pass`，`reason` 寫明沒有可確認的筆數 |

### 初始化參數

無。透過 `WorkflowConfig` 建立時，種類名稱是 `evidence_check`。

## PlanCheckReflect

`PlanCheckReflect` 用模型確認規劃模組選的步驟能不能執行、檢索有沒有正常完成，例如規劃選了一個不存在的步驟。模型讀到的內容是：最近一次規劃決定的 `thought` 與 `next_module`、最近一次檢索內容的前 500 字與 `hit_count`、感知結果的前 500 字，以及完整對話紀錄。它不讀行動結果。

模型呼叫失敗時，模組回報 `pass`，`reason` 以 `plan check did not run` 開頭，規劃模組照常往下走。使用者插話中斷時，中斷照常往外拋出，不當成模型失敗。

此模組需要明確的 OpenAI-compatible 連線設定：`api_key`、`base_url`、`model`。不需要模型時，改用規則式的 `EvidenceCheckReflect`。

### 初始化參數

| 參數 | 型態 | 必填 | 預設值 | 說明 |
| --- | --- | --- | --- | --- |
| `api_key` | `string` | 是 | 無 | OpenAI-compatible 端點金鑰。 |
| `base_url` | `string` | 是 | 無 | OpenAI-compatible API base URL。 |
| `model` | `string` | 是 | 無 | 每次推論呼叫送出的模型名稱。 |

透過 `WorkflowConfig` 建立時，種類名稱是 `plan_check`。
