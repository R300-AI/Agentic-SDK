# Python Source of Truth Specification

## 目的

這份文件定義 Playground V2 的核心資料原則：Python source code string 是唯一真實來源。

## 核心原則

1. Playground 內部可以有暫時 UI state。
2. 但真正被保存、分享、回朔、載入、匯出的，只能是 Python source string。
3. YAML、JSON、前端 schema object 都不能成為正式持久化真實來源。

## Canonical Artifact

### 唯一正式 Artifact

`python_source: str`

這份字串代表完整的 Agentic SDK Workflow 定義，以及讓系統可重新載入該 Workflow 所需的最小 Python 結構。

## 允許的派生資料

以下資料允許由 `python_source` 派生，但不能反客為主：

1. builder UI 表單狀態
2. 模組摘要卡
3. 試跑頁 workflow 摘要
4. code preview 視圖
5. save status / export time 等外部 metadata
6. runner scene profile
7. runtime capability map
8. task archetype label

## 不允許的真實來源

以下資料不可成為正式主來源：

1. YAML workflow text
2. JSON config blob
3. browser localStorage 中的中介 schema
4. server-side cache 中的非 Python config object

## Sceneable Runner 邊界

Runner 可以為不同 Agent 呈現不同程度的場景化 UI，但這種場景化不能引入第二份正式 workflow 配置來源。

### 允許的做法

1. 從 `python_source` 推導 runner capability
2. 由 host 依 `python_source` 建立暫時的 `scene_profile`
3. 依 agent runtime 能力切換不同 runner slots 與 panels

### 不允許的做法

1. 保存一份獨立的場景化 JSON 作為 agent 正式配置主來源
2. 讓 runner scene schema 反向覆蓋 `python_source` 的 workflow 定義
3. 只保存 scene metadata 而不保存對應的 Python source

### 衍生資料定位

`scene_profile` 與 `runtime_capability_map` 若存在，其定位只能是：

1. render-time derived state
2. host-side transient metadata
3. UI composition input

它們不是 canonical artifact。

同理，任務 archetype、版型模板、首屏節奏等概念，若存在，也只能作為由既有 Workflow / Modules 推導出的 UI 輔助心智，而不是獨立正式保存資料。

## Python Source 結構要求

V2 第一版生成的 Python source 應遵循穩定模板，至少包含：

1. 必要 import
2. 可選的 `OpenAI` client 初始化
3. 可選的自訂類別區塊（如自訂 Action）
4. `workflow = Workflow(...)`

### 建議結構

```python
from openai import OpenAI

from agentic_sdk import Workflow
from agentic_sdk.modules import ...


class CustomAction:
    ...


openai_client = OpenAI(...)

workflow = Workflow(
    perceive=...,
    retrieve=...,
    action=...,
)
```

## 保存規則

保存到 AI Hub 的內容只能是：

1. `agent_id`
2. `python_source`
3. 由 AI Hub 自己記錄的保存時間與狀態

Playground host 不應另存一份正式 YAML/JSON 配置副本。

## 回朔規則

### 允許回朔

只有符合 V2 支援子集的 Python source，可以完整回到 builder UI。

### 部分回朔

若 source 超出支援子集：

1. 仍可試跑
2. 仍可預覽 code
3. 但 builder 只能顯示受限摘要或拒絕完整編輯

## URL / 分享規則

匿名模式下允許以 URL 或 host 自定義分享方式攜帶 Python source，但該分享內容的本質仍是 Python source string。

## 版本化考量

若未來 Agentic SDK 公開 API 變更，必須先回答：

1. 舊版 Python source 是否仍能被 V2 載入
2. builder 是否需要升級回朔子集
3. 是否需要在 Python source 上加上非執行性註解版本標記

## PM 驗收標準

1. 系統保存時沒有正式 YAML/JSON 配置副本。
2. 匯出 `.py` 與保存到 AI Hub 使用同一份 canonical source。
3. builder 與 runner 的資料同步由 Python source 主導，而不是雙向漂移的 schema object。
4. Runner 的場景化程度可以改變，但不會創造第二份正式 workflow 真實來源。