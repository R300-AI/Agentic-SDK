# InContextMemory 統一修正規格草案

## 目的

這份草案用來統一修正 Agentic SDK 對 `MemoryStore`、`InContextMemory`、`PersistentMemory`、`WorkflowState`、以及各模組模型輸入的定義。目標不是只補一個 class 名稱，而是把文件、SDK、測試與 Playground 的認知全部對齊到同一套規格。

本草案要解決的核心問題是：

1. 使用者與助理的完整對話歷史目前沒有被當成一等輸入。
2. 文件把 `InContextMemory` 寫成既有預設引擎，但 SDK 內沒有對應的實作契約。
3. 需要模型的模組目前多半只吃 `user_message`，而不是完整對話歷史。
4. `MemoryStore`、`InContextMemory`、`PersistentMemory` 的層級與責任需要明確切開，避免把上層抽象和同層實作混為一談。

---

## 1. InContextMemory 應有的資料結構

### 1.1 規格定位

`InContextMemory` 應被定義為：

- 單一對話 session 的工作記憶
- 以時間順序保存 `user -> assistant -> user -> assistant` 的完整 turn 歷史
- 提供所有需要模型的模組共用的 conversation input
- 不負責語意召回排序；若採用偏持久化策略，召回能力可由 `PersistentMemory` 補強

`InContextMemory` 不應再被定義成：

- `WorkflowState` 的別名
- `Entities` 的別名
- `MemoryStore` 的別名
- 單純的節點中繼資料容器

### 1.2 建議資料模型

```python
from dataclasses import dataclass, field
from typing import Any, Literal


ConversationRole = Literal["system", "user", "assistant", "tool"]


@dataclass
class ConversationAttachment:
    kind: str
    content: bytes | str
    media_type: str | None = None
    name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationTurn:
    role: ConversationRole
    content: str
    turn_id: str
    workflow_name: str
    workflow_id: str
    session_id: str
    turn_index: int
    attachments: list[ConversationAttachment] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0


@dataclass
class InContextMemory:
    workflow_name: str
    workflow_id: str
    session_id: str
    turns: list[ConversationTurn] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
```

### 1.3 必要能力

`InContextMemory` 至少要提供下列能力：

```python
class InContextMemory:
    def append_turn(self, turn: ConversationTurn) -> None: ...
    def latest_user_turn(self) -> ConversationTurn | None: ...
    def latest_assistant_turn(self) -> ConversationTurn | None: ...
    def as_openai_messages(self) -> list[dict[str, Any]]: ...
    def as_text_transcript(self) -> str: ...
    def copy_for_run(self) -> "InContextMemory": ...
```

### 1.4 `Entities` 與 `InContextMemory` 的分工

應重新定義如下：

- `InContextMemory`：保存完整對話歷史與跨模組共用的 conversation context
- `Entities`：保存 workflow 執行中的結構化中繼結果，例如 `perceived_summary`、`plan_thought`、`latest_final_message`
- `ContextEntry`：保存觀測與 trace 型事件，對應每個節點做了什麼

這三層不能再混成同一個概念。

### 1.5 `MemoryStore`、`InContextMemory` 與 `PersistentMemory` 的分工

應重新定義如下：

- `MemoryStore`：所有 memory 類型的上層抽象，定義模組如何讀取完整對話歷史
- `InContextMemory`：`MemoryStore` 的一種實作，偏重 session 內工作記憶與對話承接
- `PersistentMemory`：`MemoryStore` 的一種實作，偏重長期保存、索引、搜尋與回查

也就是說：

- `MemoryStore` 解決「模組本輪如何一致地讀 memory」
- `InContextMemory` 解決「對話工作記憶如何承接」
- `PersistentMemory` 解決「跨執行期的記憶如何保存與回查」

### 1.6 目前實作的主要缺口

目前 `agentic_sdk/core/workflow.py` 每次 `run()` 都新建 `WorkflowState`，只附帶當輪 `user_message`。

目前 `agentic_sdk/memory/protocol.py` 的 `MemoryEntry` 沒有：

- `role`
- `session_id`
- `turn_index`
- 可重建完整對話順序的能力

目前 `agentic_sdk/memory/in_memory.py` 只有 `append/search`，沒有 transcript 取回能力。

---

## 2. Workflow.run 新簽名

### 2.1 新簽名目標

`Workflow.run` 需要從「只接單輪使用者輸入」改成「可接完整對話上下文」。

### 2.2 建議簽名

```python
def run(
    self,
    user_message: str | None = None,
    *,
    workflow_id: str | None = None,
    session_id: str | None = None,
    conversation: InContextMemory | None = None,
    conversation_turns: list[ConversationTurn] | None = None,
    attachments: list[Any] | None = None,
    memory_store: PersistentMemory | None = None,
    conversation_store: ConversationStore | None = None,
    event_callback: Callable[[dict[str, Any]], None] | None = None,
) -> WorkflowResult:
    ...
```

### 2.3 參數語意

- `user_message`
  - 本輪新輸入
  - 若 `conversation` 已含最新 user turn，可允許為 `None`

- `session_id`
  - 對話 session 主鍵
  - 用來讀寫完整對話歷史

- `conversation`
  - 呼叫端直接提供完整對話工作記憶

- `conversation_turns`
  - 給較簡單呼叫端的替代入口

- `memory_store`
    - 目前程式碼中指向持久化記憶的相容參數名；概念上對應 `PersistentMemory`

- `conversation_store`
  - 對話 transcript 的 durable backend

### 2.4 執行規則

新的 `Workflow.run` 應遵守：

1. 若提供 `conversation`，直接使用。
2. 若提供 `session_id` 但未提供 `conversation`，優先從 `conversation_store` 取回 transcript。
3. 若同時提供 `user_message`，必須先 append 一筆新的 user turn。
4. workflow 執行結束後，若有 assistant 回覆，必須 append assistant turn。
5. 各模組統一從 `state.memory` 取對話歷史，不再只依賴 `state.user_message`。

### 2.5 相容策略

為避免一次破壞所有現有呼叫端，短期可保留：

```python
workflow.run("TSiP 是什麼？")
```

但其內部應自動轉成：

- 建一個新的 `InContextMemory`
- append 一筆 user turn
- 執行 workflow
- append assistant turn

也就是說，舊呼叫方式仍可用，但內部邏輯要改成基於 conversation。

---

## 3. 各模組 message builder 該怎麼改

### 3.1 統一原則

所有需要模型的模組，都不應再各自直接拼 `user_message: ...` 字串。

應建立統一 helper，例如：

```python
def build_module_messages(
    state: WorkflowState,
    *,
    system_prompt: str,
    module_name: str,
    extra_context: dict[str, Any] | None = None,
    include_history: bool = True,
) -> list[dict[str, Any]]:
    ...
```

此 helper 的輸出規則：

1. 第一則永遠是 module-specific `system` prompt
2. 第二段開始是 `MemoryStore` 提供的完整對話歷史；常見實作可以是 `InContextMemory` 或 `PersistentMemory`
3. 最後再補 module-specific context，例如 retrieve 結果、reflect 檢查對象、圖片附件摘要等

### 3.2 建議 message 組裝格式

```python
[
    {"role": "system", "content": system_prompt},
    {"role": "user", "content": "<第 1 輪使用者>"},
    {"role": "assistant", "content": "<第 1 輪助理>"},
    {"role": "user", "content": "<第 2 輪使用者>"},
    ...,
    {
        "role": "system",
        "content": "module_context: {...}"
    },
]
```

若使用的是圖文模型，最後一輪 user turn 可改為 OpenAI content parts：

```python
{
    "role": "user",
    "content": [
        {"type": "text", "text": "<使用者本輪文字>"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}},
    ],
}
```

### 3.3 Perceive 應怎麼改

目前問題：

- 只讀 `state.user_message`
- 沒有可靠使用整段前文
- 對話承接能力靠 prompt 假設，不是資料模型保證

修正方向：

1. `TextPerceive` 與 `TextImagePerceive` 改成吃 `state.memory`
2. 模型輸入包含完整 user/assistant 歷史
3. 模組目標從「辨識當輪 intent」升級為「把整段上下文整理成本輪可執行需求」

建議輸出 payload：

```python
{
    "perceived_intent": "...",
    "perceived_summary": "...",
    "perceived_details": {...},
    "normalized_request": "...",
    "known_facts": [...],
    "missing_points": [...],
    "assumptions": [...],
}
```

### 3.4 Plan 應怎麼改

目前問題：

- 只讀 `user_message`
- 只補 `perceived_intent`
- 不會直接看前面 user/assistant 多輪互動

修正方向：

1. 直接讀完整對話歷史
2. 優先看 `normalized_request`
3. 再看 `missing_points`、附件、有無 retrieve context

建議 module context：

```python
{
    "normalized_request": state.lookup("normalized_request"),
    "known_facts": state.lookup("known_facts"),
    "missing_points": state.lookup("missing_points"),
    "has_attachment": len(state.attachments) > 0,
    "has_retrieved_context": state.latest_of(ContextEntryType.RETRIEVED) is not None,
}
```

### 3.5 GenerativeAction / ToolCallAction 應怎麼改

目前問題：

- prompt 只含 `retrieved_context` 與當輪 `user_message`
- 不含完整對話歷史
- 不含前面 assistant 已經承諾或已經問過的內容

修正方向：

1. 直接用完整 conversation history 當使用者上下文
2. 再補 `retrieved_context`
3. 若已有 `normalized_request`，應優先加入
4. ToolCallAction 應能看見前面表單追問與 assistant 已收集資訊

建議 module context：

```python
{
    "normalized_request": state.lookup("normalized_request"),
    "retrieved_context": state.lookup("latest_retrieved_content") or state.lookup("retrieved_snippet"),
    "perceived_details": state.lookup("perceived_details"),
}
```

### 3.6 Reflect 應怎麼改

目前問題：

- 只用當輪 `user_message` + `action_result`
- 不知道前面 assistant 問過什麼、承諾過什麼、漏問了什麼

修正方向：

1. 用完整 conversation history 檢查回答是否承接上下文
2. 比對 `normalized_request` 與 `action_result`
3. 若前文已有未回答問題，要能判定 fail

### 3.7 Retrieve 應怎麼改

`KeywordRetrieve` / `SemanticRetrieve` 不一定要直接把完整歷史全送進檢索，但 query 來源要升級。

建議優先順序：

1. `normalized_request`
2. `perceived_summary`
3. 最近幾輪 user turns 合成的 query
4. 最後才 fallback 到單輪 `user_message`

### 3.8 新增共用 helper 建議

建議新增：

- `conversation_to_openai_messages(...)`
- `conversation_to_text_transcript(...)`
- `build_module_messages(...)`
- `append_assistant_turn_from_result(...)`
- `append_user_turn_from_input(...)`

避免每個模組自行拼字串。

---

## 4. 文件頁面逐頁要刪掉或改寫的句子

本節以「刪除 / 改寫方向 / 建議新句」整理。

### 4.1 README

檔案：`README.md`

應補充而非只保留目前說法：

- 現行 README 只展示 `workflow.run("...")` 單輪呼叫，沒有說明完整對話歷史如何帶入。

建議新增段落：

> `Workflow` 可在單輪模式下直接執行，也可搭配 `MemoryStore` 實作保存完整 user / assistant 歷史。若採用 `InContextMemory`，會偏重當前 session 的工作記憶；若採用 `PersistentMemory`，則可偏重跨執行期保留與回查。當 workflow 內的模組需要模型時，模型輸入可包含整段對話歷史，而不只限於本輪訊息。

### 4.2 文件首頁

檔案：`docs/index.md`

應刪除或改寫的句子：

- `說明 Workflow 預設如何用 InContextMemory 承接執行中的狀態資料，以及之後可替換或注入哪些引擎層。`
- `查 Workflow 預設使用的 InContextMemory，以及可注入的其他引擎層。`

問題：

- 目前 SDK 並不存在這個對外可用的預設型別
- 句子把未落地規格說成既有行為

建議改寫：

> 說明 `Workflow` 如何承接單次執行狀態、完整對話工作記憶，以及可額外注入的長期記憶或對話儲存層。

### 4.3 Workflow Overview

檔案：`docs/workflow-overview.md`

應刪除的句子：

- `Workflow 會在內部建立一份 WorkflowState，公開別名為 InContextMemory。`
- `這份狀態的公開別名是 InContextMemory，也是預設 workflow engine 在單次 run 中承接資料的方式。`

問題：

- `WorkflowState` 不是 `InContextMemory`
- `WorkflowState` 比較像執行期容器，不是完整對話工作記憶型別

建議改寫：

> `Workflow` 執行時會建立一份 `WorkflowState` 作為本輪執行容器；若 workflow 啟用某個 `MemoryStore` 實作，則 `WorkflowState` 會持有一份對話記憶，供各模組讀取完整 user / assistant 歷史。

應改寫的 `Entities` 段落：

- 不要再把 `Entities` 當作 conversation memory 的中央定義

建議改寫：

> `Entities` 用來保存 workflow 執行中的結構化中繼資料，例如 `perceived_summary`、`normalized_request`、`latest_retrieved_content`、`latest_final_message`。完整對話歷史不屬於 `Entities`，而屬於 `MemoryStore` 的具體實作。

### 4.4 Workflow 引擎選項

檔案：`docs/workflow-engines.md`

應刪除的句子：

- `InContextMemory 是 Workflow 的預設引擎。`
- `Workflow 會用 InContextMemory 承接單次執行期間需要保存的輸入、中繼結果與暫時狀態。`
- `這一層通常承接的資料，會對應到文件裡定義的 Entities 物件。`
- `ActiveStore` 相關描述

問題：

- 把未實作的規格寫成既有產品能力
- 混淆工作記憶與中繼狀態
- 文件提到 `ActiveStore`，但 SDK 公開 API 沒有這個注入契約

建議重寫整頁主軸：

1. `WorkflowState` 是單次執行容器
2. `MemoryStore` 是上層 memory 抽象
3. `InContextMemory` 與 `PersistentMemory` 是同層、可互換的 memory 類型
4. `ConversationStore` 是 durable 對話歷史 backend

建議新句：

> `Workflow` 至少涉及兩個層次的概念：一個是上層抽象 `MemoryStore`，另一個是同層可互換的 `InContextMemory` 與 `PersistentMemory`。前者定義模組如何讀 memory，後兩者決定記憶策略與保存方式，不應混為同一套資料結構。

### 4.5 Perceive 模組頁

檔案：`docs/modules/perceive-modules.md`

應改寫的段落：

- 所有 `標準輸入參數` 目前都寫成單輪 `user_message`

問題：

- 不符合完整對話歷史作為模型輸入的目標

建議改寫：

> `TextPerceive` 與 `TextImagePerceive` 的主要輸入不只是一段 `user_message`，而是當前對話 session 中的完整 user / assistant 歷史，再加上本輪附件、欄位提示與整理規則。當沒有提供歷史時，才退化為單輪模式。

建議新增的初始化參數說明：

- `history_window` 或等效設定：控制送給模型的對話歷史範圍
- `image_instruction`：說明圖片判讀重點

### 4.6 Action 模組頁

檔案：`docs/modules/action-modules.md`

雖然本次沒有逐行盤點，但主軸必須補：

- `GenerativeAction` 與 `ToolCallAction` 的模型輸入不應只描述 retrieved context
- 必須說明它們會在 system prompt 之外讀取完整對話歷史與整理後需求

### 4.7 Plan 模組頁

檔案：`docs/modules/plan-modules.md`

必須補：

- Plan 的判斷輸入應包含完整對話歷史
- 不是只依賴單輪 `user_message`

### 4.8 Reflect 模組頁

檔案：`docs/modules/reflect-modules.md`

必須補：

- Reflect 的檢查標準應以整段對話需求是否被回應為準
- 不是只對比當輪 `user_message` 與 `action_result`

---

## 5. 建議的統一修正順序

### Phase 1: 規格與命名收斂

1. 定義 `ConversationTurn`
2. 定義 `InContextMemory`
3. 定義 `ConversationStore`
4. 明確切開 `WorkflowState` / `MemoryStore` / `InContextMemory` / `PersistentMemory`

### Phase 2: SDK 執行入口調整

1. 擴充 `Workflow.run`
2. `WorkflowState` 持有 `memory`
3. 自動記錄 user turn / assistant turn

### Phase 3: 模型模組統一 message builder

1. 先改 Perceive
2. 再改 Plan
3. 再改 GenerativeAction / ToolCallAction
4. 最後改 Reflect

### Phase 4: Retrieve query 升級

1. query 優先使用 `normalized_request`
2. 再 fallback 到當輪 `user_message`

### Phase 5: 文件與測試對齊

1. 改 `README.md`
2. 改 `docs/index.md`
3. 改 `docs/workflow-overview.md`
4. 改 `docs/workflow-engines.md`
5. 改各模組頁
6. 把單輪測試補成多輪歷史測試

---

## 6. 驗收標準

完成統一修正後，至少要符合：

1. SDK 對外存在可用的 `InContextMemory` 規格與型別。
2. `Workflow.run` 可帶入完整對話歷史或 session。
3. user / assistant 對話 turn 會完整保存。
4. 所有需要模型的模組都能讀取完整對話歷史。
5. `MemoryStore` 不再被誤認成某一種具體記憶實作，`InContextMemory` 與 `PersistentMemory` 的同層關係清楚可辨。
6. 文件不再把 `WorkflowState` 說成 `InContextMemory`。
7. 測試有多輪 user / assistant 對話案例。

---

## 7. 本草案對目前狀態的裁定

目前 Agentic SDK 與文件站的主要偏差可總結為：

- 文件先行定義了一個尚未實作完成的 `InContextMemory`
- SDK 目前實際採用的是「單輪 user_message + 中繼 payload」模型
- `MemoryStore`、`InContextMemory`、`PersistentMemory` 的概念原本被混用，導致抽象層與實作層級不清
- 若目標是讓所有模型模組都吃完整對話歷史，則需要進行橫向規格重構，而不是局部修補

因此，後續實作不應再把修正理解成「補一個 memory class」，而應理解成「重構整個 conversation input contract」。