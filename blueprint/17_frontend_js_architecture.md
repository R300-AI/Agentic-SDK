# Frontend JavaScript Architecture Specification

## 目的

這份文件定義 Playground V2 在 Flask + HTML/JS 架構下的前端腳本組織方式。

## 原則

1. 不把整站做成 Node/Vite SPA。
2. 以 server-rendered HTML 為基礎。
3. 用小型、頁面導向的 JS 模組增強互動。
4. 保持 builder 與 runner 的狀態邏輯可測且可維護。

## 模組切分建議

```text
static/js/
├─ entry/
│  └─ entry-page.js
├─ builder/
│  ├─ builder-page.js
│  ├─ starter-template.js
│  ├─ input-contract.js
│  ├─ module-form.js
│  ├─ output-contract.js
│  ├─ readiness-check.js
│  ├─ summary-panel.js
│  └─ source-sync.js
├─ runner/
│  ├─ runner-page.js
│  ├─ shell-layout.js
│  ├─ scene-profile.js
│  ├─ slot-registry.js
│  ├─ input-composer.js
│  ├─ result-surface.js
│  ├─ evidence-panel.js
│  ├─ artifact-panel.js
│  ├─ history-panel.js
│  ├─ code-preview.js
│  └─ save-panel.js
└─ shared/
   ├─ api-client.js
   ├─ toast.js
   ├─ dialog.js
   └─ mode-context.js
```

## 狀態原則

### Builder 前端狀態

只保存暫時互動狀態，例如：

1. 目前選中模組
2. 尚未提交的欄位輸入
3. 展開/收合狀態
4. starter template 選擇
5. input contract 選擇
6. output contract 選擇
7. readiness check 結果快取

Builder 的正式資料仍應由 server 或共享的 `python_source` 對應中介 state 管理。

### Runner 前端狀態

保存：

1. 聊天訊息暫態
2. 附件預覽
3. code preview drawer 開關
4. save panel loading state
5. 當前 runner scene profile
6. 啟用中的 capability set
7. 各 slot panel 的展開狀態

## 前後端同步原則

1. Builder 完成一次有效變更後，應重新同步最新 Python source。
2. Runner 顯示的 code preview 必須來自同一份最新 source。
3. 不能同時維護兩份互相漂移的主配置模型。
4. Runner scene profile 若存在，必須由 source 或 host-side transient metadata 派生，不可獨立持久化為第二主模型。
5. Builder 的 input/output contract UI 若存在，必須最終映射回實際 module 選擇與 `python_source`，不可獨立漂移。

## Runner Scene Composition

Runner 前端應採 slot-based composition，而不是為每個 use case 寫獨立頁面。

### Scene Profile

`scene_profile` 是 render-time 物件，可包含：

1. `layout_variant`
2. `enabled_slots`
3. `input_mode`
4. `result_mode`
5. `capabilities`

它的來源可以是：

1. 由 `python_source` 派生
2. host 依 agent metadata 推導
3. server 在 `/playground/run/profile` 回傳

### Slot Registry

前端應維護一份通用 slot registry，把 UI 區塊註冊為可組合模組，例如：

1. `conversation`
2. `structured_input`
3. `result_summary`
4. `artifacts`
5. `evidence`
6. `history`
7. `actions`

### 設計限制

1. 不針對單一案例硬編碼頁面。
2. 若新增 Agent 場景，只能優先透過新 capability 或新 slot 組合擴充。
3. 只有在 slot-based 組合不足以表達時，才允許新增新型 product component。

## 模式感知

前端所有頁面都應能讀到 server 注入的 `mode context`：

1. anonymous
2. manual_auth
3. aihub_readonly
4. aihub_editable

這個 context 用來決定：

1. 哪些按鈕顯示
2. 哪些 panel 載入
3. 哪些操作被禁用

## PM 驗收標準

1. 不存在一個巨大的全域腳本負責所有頁面。
2. Builder 與 Runner 腳本職責清楚。
3. 模式權限控制不是只靠 CSS 隱藏，而是前後端共同控制。
4. 新 Agent 的場景化需求可透過 runner slot composition 落地，而不是複製一份新 runner 頁面。