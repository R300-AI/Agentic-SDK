"""A-03 — 五大節點 baseline 實作。

每個節點是一個資料夾,內含至少一個 baseline 演算法檔。`__init__.py` 暴露
`DEFAULT` 常數讓 `Workflow()` 預設拾起 baseline,使用者可在初始化時覆寫:

    from agentic_sdk.workflow import Workflow
    from agentic_sdk.workflow.nodes.plan.tree_of_thoughts import TreeOfThoughtsPlan

    wf = Workflow(plan=TreeOfThoughtsPlan())

新增演算法的 SOP 詳見 blueprint/source-layout.md「節點演算法擴展規範」。
"""
