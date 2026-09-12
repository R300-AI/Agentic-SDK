# 讓 Agent 檢查回答有沒有依據

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/R300-AI/Agentic-SDK/blob/main/notebooks/05-search-documents-and-answer.ipynb)

這份教材示範如何用 `EvidenceCheckReflect` 在回答之前確認查到了資料。重點不是背參數，而是看懂加上 Reflect 前後，結果裡多了哪些可供程式判斷的訊號，以及規劃模組怎麼讀這個訊號。

## 涵蓋內容

- 比較有無 `EvidenceCheckReflect` 時，同一題的執行路徑與結果差在哪裡。
- 讀懂 `reflect_verdict` 這個機器可判讀的確認結果。
- 從 reflection 條目看確認依據與原因，並確認它排在行動結果之前。
- 知道 `PassThroughPlan` 與 `NextStepPlan` 讀到 `fail` 之後各自怎麼走。

## 相關文件

- [Reflect](../modules/reflect-modules.md)
- [參考資料](../modules/retrieve-modules.md)
