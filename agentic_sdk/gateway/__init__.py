"""Gateway 套件 — 對外 OpenAI 相容前端,只代理上游 AMD NPU api.py。

注意:本 __init__ 刻意保持空白,不 re-export `create_app`。
原因是 `agentic_sdk.gateway.app` 會 import `routes_chat`,
而 `routes_chat` 又 import `agentic_sdk.workflow.modules.action`,
若使用者(或 action 節點)反向 import `agentic_sdk.gateway.upstream_client`
就會觸發 `gateway.__init__` → `app` → `routes_chat` → `action` 的循環匯入。
請直接 `from agentic_sdk.gateway.app import create_app` 使用。
"""
