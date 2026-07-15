# Python Demo Scripts

這個目錄提供對應根目錄 README 三個 quickstart 的可執行 Python 腳本。

## 檔案

- `demo_01_direct_answer.py`: 對應 README 案例 1
- `demo_02_ollama_completion.py`: 對應 README 案例 2
- `demo_03_custom_action.py`: 對應 README 案例 3

## 執行方式

在 repo root 執行：

```powershell
C:/Python314/python.exe demo/demo_01_direct_answer.py
C:/Python314/python.exe demo/demo_02_ollama_completion.py
C:/Python314/python.exe demo/demo_03_custom_action.py
```

這三個腳本也可以直接在 `demo/` 目錄中執行，不需要額外手動設定 `PYTHONPATH`。腳本開頭會先切回 repo root，並補上最小必要的 `sys.path` 設定，確保 `agentic_sdk` 可被匯入。

第二個案例預設使用本機 Ollama 的 `llama3.2:1b`。若你想換模型，可設定環境變數 `AGENTIC_OLLAMA_MODEL`。