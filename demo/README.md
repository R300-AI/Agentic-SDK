# Python Demo Scripts

這個目錄提供對應根目錄 README 四個 quickstart 的可執行 Python 腳本。

## 檔案

- `demo_00_on_event.py`: 示範 `event_callback` 與 events schema
- `demo_01_direct_answer.py`: 對應 README 案例 1
- `demo_02_ollama_completion.py`: 對應 README 案例 2
- `demo_03_tool_call_action.py`: 對應 README 案例 3
- `demo_04_custom_action.py`: 對應 README 案例 4

## 執行方式

在 repo root 執行：

```powershell
C:/Python314/python.exe demo/demo_00_on_event.py
C:/Python314/python.exe demo/demo_01_direct_answer.py
C:/Python314/python.exe demo/demo_02_ollama_completion.py
C:/Python314/python.exe demo/demo_03_tool_call_action.py
C:/Python314/python.exe demo/demo_04_custom_action.py
```

這四個腳本也可以直接在 `demo/` 目錄中執行，不需要額外手動設定 `PYTHONPATH`。腳本開頭會先切回 repo root，並補上最小必要的 `sys.path` 設定，確保 `agentic_sdk` 可被匯入。

第二個案例預設使用本機 Ollama 的 `llama3.2:1b`。若你想換模型，可設定環境變數 `AGENTIC_OLLAMA_MODEL`。

第三個案例示範 OpenAI 標準 tool calling。它預設使用本機 Ollama OpenAI-compatible 端點；若你要改用其他支援 tool calling 的模型端點，可設定 `AGENTIC_TOOL_MODEL`、`AGENTIC_TOOL_BASE_URL` 與 `AGENTIC_TOOL_API_KEY`。