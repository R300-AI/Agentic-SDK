from __future__ import annotations

import ast

from flask import Blueprint, Response, abort, session

from playground.services.mode_context import get_mode_context
from playground.services.source_builder import build_default_python_source, normalize_python_source, render_python_source
from playground.services.workflow_spec import compile_python_source


source_bp = Blueprint("source", __name__, url_prefix="/playground/source")


@source_bp.before_request
def require_source_view_permission():
    if not get_mode_context().can_view_code:
        abort(403)


@source_bp.get("/preview")
def preview_source():
    python_source = _current_python_source()
    return Response(_source_preview_markdown(python_source), mimetype="text/markdown")


def _current_python_source() -> str:
    spec = session.get("workflow_spec")
    if isinstance(spec, dict) and spec.get("version") == "2":
        python_source = compile_python_source(spec)
        session["python_source"] = python_source
        return python_source

    canonical_source = normalize_python_source(session.get("python_source") or build_default_python_source())
    session["python_source"] = canonical_source
    return render_python_source(canonical_source)


def _source_preview_markdown(python_source: str) -> str:
    python_imports, python_workflow = _split_python_source_blocks(python_source)
    placeholder_notice = "此 Playground 在執行期會從 Key Vault 取得 **api_key**、**base_url** 與模型設定；匯出後請以相同的 Key Vault 設定提供這些值。"
    if python_imports:
        source_steps = f"""## 匯入 SDK 模組

先複製 import 區塊，讓 Python 執行環境載入 **Workflow** 與必要模組。

```python
{python_imports}
```

## 建立 Workflow

{placeholder_notice}

```python
{python_workflow}
```"""
    else:
        source_steps = f"""## 建立 Workflow

複製下方 Python 程式碼；執行期的 **api_key**、**base_url**、**model** 或 **embedding_model** 必須由 Key Vault 提供。

```python
{python_workflow}
```"""
    return f"""{source_steps}
"""


def _split_python_source_blocks(python_source: str) -> tuple[str, str]:
    source = python_source.rstrip()
    if not source:
        return "", ""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return "", source

    import_end_line = 0
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            import_end_line = getattr(node, "end_lineno", node.lineno)
            continue
        break

    lines = source.splitlines()
    import_source = "\n".join(lines[:import_end_line]).rstrip()
    body_lines = lines[import_end_line:]
    while body_lines and not body_lines[0].strip():
        body_lines.pop(0)
    body_source = "\n".join(body_lines).rstrip()
    return import_source, body_source or source