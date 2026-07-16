# Flask Application Architecture Specification

## 目的

這份文件定義 Playground V2 的 Flask 後端架構，確保之後實作時，不會把 AI Hub 串接、builder 狀態、runner 執行與模板渲染混雜在單一模組中。

## 架構原則

1. Flask 負責 route、session、server-side 權限判定與模板輸出。
2. Python source 的生成/回朔邏輯應獨立成 domain service。
3. AI Hub API 呼叫應封裝為 client/service，不直接寫在 route handler。
4. runner 執行與 UI route 應分層。

## 建議目錄

```text
playground_v2/
├─ app.py
├─ routes/
│  ├─ entry.py
│  ├─ builder.py
│  ├─ runner.py
│  └─ aihub.py
├─ services/
│  ├─ source_builder.py
│  ├─ source_parser.py
│  ├─ runner_service.py
│  └─ aihub_client.py
├─ templates/
│  ├─ entry.html
│  ├─ builder.html
│  ├─ runner.html
│  └─ partials/
├─ static/
│  ├─ css/
│  ├─ js/
│  └─ img/
└─ models/
   └─ ui_state.py
```

## Route 職責

### entry routes

負責：

1. 顯示入口頁
2. 驗證是否有 AI Hub deep link
3. 導向 builder 或 runner

### builder routes

負責：

1. 顯示建構頁
2. 更新 server-side `python_source`
3. 處理 builder 到 runner 的遷移

### runner routes

負責：

1. 顯示試跑頁
2. 執行 workflow
3. 提供 code preview
4. 匯出 `.py`

### aihub routes

負責：

1. 驗證登入
2. 載入既有配置
3. 保存最新配置

## Session 模型

Session 建議至少保存：

1. `mode`
2. `python_source`
3. `agent_id`
4. `source_origin`
5. `account_context_present`

不得保存：

1. 明文密碼
2. 非必要的長期敏感資訊

## Service 職責

### source_builder

將 builder UI state 生成標準 Python source。

### source_parser

將符合支援子集的 Python source 回朔成 builder 可理解的中介 UI state。

### runner_service

處理試跑時的 workflow 執行、附件注入、結果回傳。

### aihub_client

封裝 AI Hub 的 verify/load/save API。

## 模板策略

1. 使用 server-rendered HTML 作為頁面骨架
2. 使用輕量 JS 補上互動
3. 避免把整個產品做成重型 SPA

## PM 驗收標準

1. Route handler 中沒有大量商業邏輯與字串拼接。
2. AI Hub 串接呼叫都有集中封裝。
3. Python source 生成與回朔不是散落在模板腳本裡。