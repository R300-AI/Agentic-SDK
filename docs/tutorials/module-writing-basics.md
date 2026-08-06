# 五大模組的共同寫法

[![Open In Colab](https://colab.research.google.com/assets/colab-badge.svg)](https://colab.research.google.com/github/R300-AI/Agentic-SDK/blob/main/notebooks/07-from-playground-to-code.ipynb)

這份教材說明如何用 Python 撰寫可放進工作流程的模組。五大模組都遵循同一個基本寫法：物件提供 `name`，以 `__call__(state)` 接收目前狀態，完成後回傳 `ModuleOutput`。

## 你會學到

- 看懂模組共同的最小寫法。
- 分辨 `WorkflowState`、`ModuleOutput`、`payload` 與 `context_updates` 各自保存的資料。
- 知道 `next_module` 如何指定下一個步驟。
- 用一個小型回覆步驟確認模組是否能放入工作流程。

## 相關文件

- [工作流程](../workflow/index.md)
- [模組家族](../modules/index.md)