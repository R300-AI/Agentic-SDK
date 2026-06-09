"""Dashboard 套件。

職責邊界:
- 純讀者,不修改 Gateway 狀態
- 透過 HTTP 拉資料(`/internal/telemetry/snapshot`),不直接 import RingBufferHandler
- 與 Gateway 共用 venv 但屬於獨立行程,可獨立啟停
- 面板程式碼只認 `DataSource` Protocol,不知資料來源實際是 Gateway 還是 mock
"""
