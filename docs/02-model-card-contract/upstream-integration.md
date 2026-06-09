# Upstream Integration — 與上游推論伺服器的銜接契約 [R03]

> 受眾:SDK 整合者、上游 Pipeline 維護者
> 目的:定義 Agentic SDK 如何銜接 [`R300-AI/amd-ryzen-ai-benchmark`](https://github.com/R300-AI/amd-ryzen-ai-benchmark) 已提供的 OpenAI 相容推論伺服器。

## 一、邊界宣告

本專案 **不實作** 以下能力,皆屬於上游:

- SLA 量測 Pipeline(TTFT / Peak Memory / Soak Test)
- 模型 × 晶片組合的認證履歷產出
- NPU / iGPU 驅動、Vitis AI EP、ROCm 等執行環境的封裝
- 模型的下載、量化、ONNX 轉換
- 對外提供 OpenAI 相容 HTTP server(`api.py` 已提供)

本專案僅做為**上游推論伺服器的 Agentic 編排層**,在已存在的 OpenAI 相容 API 之上加 Perceive / Plan / Retrieve / Reflect / Action 五大節點的工作流能力。

## 二、上游已提供的能力(SDK 直接依賴)

依 [上游 README](https://github.com/R300-AI/amd-ryzen-ai-benchmark) 描述,使用者依環境啟動 `api.py` 即可獲得:

```bash
# NPU backend
conda activate ryzen-ai-1.7.1
python api.py --model gemma3-4b-npu

# iGPU backend
conda activate rocm-pytorch
python api.py --model gemma4-2b-gpu
```

啟動後上游於 `http://localhost:8000` 暴露:

- `POST /v1/chat/completions`(含 `stream=true` SSE)
- `GET /v1/models`(回傳當前載入的模型清單)
- 支援 Vision LM(`image_url` content type)

本專案 SDK 視此介面為**既定事實**,不重新包裝、不代理、不抽象。

## 三、契約最小化原則

兩方之間的契約僅有一條:**上游必須持續維持 OpenAI Chat Completions API 相容性**。

SDK 端不依賴:
- 任何上游內部資料結構(`ryzenai/` 模組、`weights/` 目錄結構)
- 上游的模型管理流程(模型如何下載、量化、載入)
- 上游的驗證機制(認證履歷的 schema、簽章方式)

「使用者選擇啟動哪個模型」這件事完全由使用者依上游 README 決定;SDK 端只在啟動時呼叫一次 `GET /v1/models` 取得當前可用清單。

## 四、SDK 端配置

SDK 透過 `.env` 指向上游推論伺服器:

| 配置項 | 預設值 | 說明 |
|--------|--------|------|
| `UPSTREAM_API_BASE_URL` | `http://localhost:8000/v1` | 上游 `api.py` 暴露的 OpenAI 相容端點 |
| `UPSTREAM_API_KEY` | `local` | 上游目前不驗證 API Key,留欄位以維持 OpenAI SDK 相容形態 |
| `UPSTREAM_HEALTHCHECK_TIMEOUT_SEC` | `5` | SDK 啟動時對上游做一次 `GET /v1/models` 的逾時上限 |

SDK 啟動時若 healthcheck 失敗:
1. 印出明確錯誤訊息「上游推論伺服器無回應,請先依 amd-ryzen-ai-benchmark README 啟動 api.py」
2. **不啟動** Agent 工作流引擎,避免後續每次節點呼叫都失敗

## 五、認證模型的選擇

「哪些模型通過認證」這件事**完全由上游 README 的支援模型列表決定**。本專案不維護自己的認證清單、不做 SHA 驗證、不做簽章核對——這些都在上游的責任範圍內。

使用者選擇啟動非認證模型時,風險由使用者自負(SDK 不阻擋,只是 Workflow 行為可能無法保證符合 SLA)。

## 六、相依的上游版本

| 項目 | 鎖定 |
|------|------|
| 上游 OpenAI API 端點 base path | `/v1` |
| 上游模型 ID 命名規則 | 結尾 `-npu` 為 NPU backend、`-gpu` 為 iGPU backend(依上游 README §快速開始) |
| 上游 commit | 待 PoC 第一次整合時鎖定,並寫入 [blueprint/risk-decisions.md](../../blueprint/risk-decisions.md) |

## 七、不在本契約內的事項

明確記錄以避免日後誤解:

- ❌ 本專案不對「模型品質」做任何承諾;這由上游 SLA 履歷負責
- ❌ 本專案不代上游分發模型權重
- ❌ 本專案不為上游修補 OpenAI API 相容性的缺漏(若上游某端點未實作,SDK 在該端點失效,而非自行模擬)
- ❌ 本專案不維護「跨上游版本的相容矩陣」;若上游 schema 變更,本專案視為斷裂變更
