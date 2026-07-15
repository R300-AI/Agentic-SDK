# Plan

Plan 模組負責根據感知結果與目前上下文決定 workflow 的下一步。這一頁先把 Plan 家族的核心責任收斂成「交出下一節點決策」，再用單一標準名 `NextStepPlan` 來承接這個角色。規劃過程讀寫的中間欄位統一回到 [Module Family](index.md) 的 `Entities` 中央定義理解，因此這一頁聚焦在模組角色與決策責任。

## NextStepPlan

舊名對應：`ReActPlan`

`NextStepPlan` 根據感知摘要與已有上下文，決定下一步要查資料還是直接回答。閱讀這個模組時，可以把它理解成一個明確的路由點：先看它讀進哪些線索，再看它交出哪些決策欄位給後續節點使用。