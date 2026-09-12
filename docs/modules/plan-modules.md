# Plan

Plan 模組負責根據感知結果與目前上下文決定 workflow 的下一步。每個流程都有一個規劃模組：感知、檢索與反思做完都交回它，由它在檢索、反思、行動之中選一個，行動之後這次執行結束。這一頁的 `PassThroughPlan` 用固定規則選擇，`NextStepPlan` 用模型選擇。每個模組會先列出建立物件時使用的初始化參數；規劃過程讀寫的中間欄位統一回到 [Module Family](index.md) 的 `Entities` 中央定義理解。

透過 `WorkflowConfig` / `ModuleSpec.params` 建立 Plan 模組時，SDK 只接受本頁列出的初始化參數。個案名稱或 UI 顯示標籤不應透過初始化參數注入 planner。

規劃模組每次被造訪時，`state.plan_options` 列出這一次可以選的步驟。自訂規劃模組回傳不在其中的步驟時，`Workflow` 改走行動。

## PassThroughPlan

`PassThroughPlan` 不呼叫模型。`Workflow` 沒有指定 `plan` 時使用它。每次造訪依序判斷：

1. 這次執行還沒檢索過，選檢索。
2. 反思可選、且這次執行還沒反思過，選反思。
3. 其他情況，選行動。

每次造訪留下一筆 `plan_decision` 條目，metadata 的 `next_module` 是選擇的步驟，`strategy` 為 `pass_through`。

### 初始化參數

無。透過 `WorkflowConfig` 建立時，種類名稱是 `pass_through_plan`。

## NextStepPlan

參考論文：[ReAct: Synergizing Reasoning and Acting in Language Models](https://arxiv.org/abs/2210.03629)

`NextStepPlan` 根據感知摘要、完整對話歷史與已有上下文，決定下一步要查資料、先送反思，還是直接回答。閱讀這個模組時，可以把它理解成一個明確的路由點：先看它讀進哪些線索，再看它交出哪些決策欄位給後續節點使用。

此模組需要明確的 OpenAI-compatible 連線設定：`api_key`、`base_url`、`model`。不同 Plan 模組可以與 Perceive 或 Action 使用不同模型。

每次造訪時，模型收到的 prompt 只列出 `state.plan_options` 裡的步驟，格式是 `Choose next_module from: retrieve, reflect, action.`。反思做過之後，`module_context` 的 `latest_reflect_report` 帶最近一次反思回報的 `verdict`、`reason` 與 `suggestion`，模型依此決定重查、再送反思或行動。模型選了不在清單裡的步驟時，`next_module` 改為 `action`，決策條目的 `fallback` 為 `true`。

### 初始化參數

| 參數 | 型態 | 必填 | 預設值 | 說明 |
| --- | --- | --- | --- | --- |
| `api_key` | `string` | 是 | 無 | OpenAI-compatible 端點金鑰。 |
| `base_url` | `string` | 是 | 無 | OpenAI-compatible API base URL。 |
| `model` | `string` | 是 | 無 | 每次推論呼叫送出的模型名稱。 |
| `system_prompt` | `string|null` | 否 | `null` | 覆寫 planner 系統提示；未提供時由 SDK 根據 retrieve 描述產生預設 prompt。 |
| `retrieve_description` | `string|null` | 否 | `null` | 取回節點用途說明，會被放入 planner prompt；不應放入個案名稱或展示用標籤。傳入自訂 `system_prompt` 時仍然生效。 |
| `reflect_description` | `string|null` | 否 | `null` | 反思模組用途說明，只在反思可選時放入 planner prompt。未提供時使用掛上的反思模組自帶的 `description`；兩者都沒有時，prompt 不描述反思。傳入自訂 `system_prompt` 時仍然生效。 |
| `route_policy` | `callable|null` | 否 | `null` | 由呼叫方決定最終路由。收到 `(state, 模型選的模組)`，回傳要採用的模組；回傳模型的選擇即表示接受。SDK 不附預設政策——哪些問題需要查資料取決於題材，那是應用程式知道而通用 planner 不知道的事。 |

## NextStepWithSkills

`NextStepWithSkills` 是 `NextStepPlan` 加上技能。除了決定下一步，它還決定這一輪要不要取用某一個技能；其餘行為與 `NextStepPlan` 相同，流程與其他模組都不知道技能的存在。技能包的格式與檢查規則見[技能包](skill-packages.md)。

建立時傳入技能包路徑，模組當場讀完並掛上；執行期不再讀檔案。

```python
plan = NextStepWithSkills(
    api_key=api_key,
    base_url=base_url,
    model="gpt-4o-mini",
    skill_packages=["skill_packages/meeting-notes"],
)
```

### 技能怎麼被選中

兩條路，使用者指名優先：

1. **使用者指名**：訊息以 `/名稱` 開頭，且該名稱是已掛上的技能。開頭是別的路徑（例如 `/usr/local`）時當一般文字處理。
2. **模型挑選**：系統提示附上 `available_skills:` 清單，一行一個技能，格式是 `名稱: 說明`。模型在回覆裡多填一個 `skill` 欄位；填的名稱沒掛上就當作沒挑。

選中的技能，內容逐字加進對話，成為一則使用者角色的訊息——不摘要、不改寫、不覆蓋先前說過的話。後續各輪由對話本身帶著它，不重讀技能包。同一個技能在一段對話裡只加入一次，一段對話可以陸續取用多個技能。

決策條目的 metadata 多兩個欄位：`skill` 是這一輪取用的技能名稱，`skills_left_out` 是因為清單預算而沒列給模型看的技能數。`payload` 的 `picked_skill` 同樣是取用的技能名稱。

### 技能清單的預算

技能多的 agent 不應該把模型的輸入花在目錄上。清單先切每一條說明，再從尾端整條省略：

| 上限 | 預設值 | 作用 |
| --- | --- | --- |
| `max_listing_characters` | `8000` | 整份清單的字元上限。超過時後面的技能不列入，數量記在 `skills_left_out`。 |
| `max_listing_description_characters` | `1536` | 單一技能在清單裡的說明長度。超過的部分以 `…` 截斷，後面的技能因此仍列得出來。 |

沒列進清單的技能仍然掛著：使用者用 `/名稱` 指名時照樣取用。宣告 `disable-model-invocation: true` 的技能一律不列入清單，只能由使用者指名。

### 初始化參數

`NextStepPlan` 的參數全部適用，另有四個：

| 參數 | 型態 | 必填 | 預設值 | 說明 |
| --- | --- | --- | --- | --- |
| `skill_packages` | `str|Path|Iterable` | 否 | `()` | 技能包來源：資料夾、zip 壓縮檔，或帶版本的 git 網址 `https://…/name.git@v1.2.0`。單一來源可以不寫成串列。建立時取回並檢查，來源有問題丟 `SkillSourceRefused`，技能包不合格丟 `SkillPackageRefused`。見[技能包](skill-packages.md#從-github-掛載)。 |
| `max_skill_characters` | `int` | 否 | `20000` | 單一技能加進對話的內容上限，超過的技能包被拒絕。 |
| `max_listing_characters` | `int` | 否 | `8000` | 給模型看的技能清單總字元上限。 |
| `max_listing_description_characters` | `int` | 否 | `1536` | 清單裡單條說明的字元上限。 |
