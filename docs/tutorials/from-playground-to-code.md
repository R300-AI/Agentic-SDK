# 看懂五大模組的共同規範

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/R300-AI/Agentic-SDK/blob/main/notebooks/06-from-playground-to-code.ipynb)

這份教材說明 Agentic SDK 如何判斷一個物件能不能放進 workflow。五大模組共用同一個執行標準：模組有 `name`，用 `__call__(state)` 接收 `WorkflowState`，並回傳 `ModuleOutput`。

## 你會學到

- 看懂五大模組共用的最小介面。
- 分辨 `WorkflowState`、`ModuleOutput`、`payload` 與 `context_updates` 的責任。
- 知道 `next_module` 如何決定 workflow 下一站。
- 用一個最小 action 驗證模組規範，而不是先寫複雜功能。

## 相關文件

- [模組家族](../modules/index.md)
- [工作流程](../workflow/index.md)
