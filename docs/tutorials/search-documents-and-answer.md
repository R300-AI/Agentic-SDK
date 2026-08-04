# 讓 Agent 檢查回答有沒有依據

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/R300-AI/Agentic-SDK/blob/main/notebooks/05-search-documents-and-answer.ipynb)

這份教材示範如何用 `EvidenceCheckReflect` 檢查 Agent 的回答是否有查到的資料撐腰。重點不是背參數，而是看懂加上 Reflect 前後，結果裡多了哪些可供程式判斷的訊號。

## 你會學到

- 比較有無 `EvidenceCheckReflect` 時，同一題的回應差在哪裡。
- 讀懂 `reflect_verdict` 這個機器可判讀的驗收結果。
- 從 `context_updates` 裡的 reflection entry 看驗收依據與原因。
- 知道 `on_failure='end'` 與 `on_failure='retry_plan'` 分別會把流程導向哪裡。

## 相關文件

- [Reflect](../modules/reflect-modules.md)
- [參考資料](../modules/retrieve-modules.md)
