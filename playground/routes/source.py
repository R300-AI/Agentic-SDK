from __future__ import annotations

import ast
import io
import zipfile
from pathlib import PurePosixPath

from flask import Blueprint, Response, abort

from playground.services import skill_store
from playground.services.mode_context import get_mode_context
from playground.services.session_spec import current_spec
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


@source_bp.get("/skill-packages.zip")
def download_skill_packages():
    """The mounted packages, laid out the way the exported code expects to find them."""
    entries = skill_store.mounted_entries(current_spec())
    if not entries:
        abort(404)
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        for entry in entries:
            root = skill_store.path_for(entry)
            for file in sorted(root.rglob("*")):
                if file.is_file():
                    archive.write(file, PurePosixPath("skill_packages", str(entry["name"]), file.relative_to(root).as_posix()).as_posix())
    return Response(
        buffer.getvalue(),
        mimetype="application/zip",
        headers={"Content-Disposition": "attachment; filename=skill_packages.zip"},
    )


def _current_python_source() -> str:
    return compile_python_source(current_spec())


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
{_skill_package_section()}"""


def _skill_package_section() -> str:
    """What the exported code needs beside it: the skill packages themselves.

    The code names each package by a path, and the files sit in this server's
    store, so taking the agent elsewhere means taking them along.
    """
    packages = [skill_store.describe(entry) for entry in skill_store.mounted_entries(current_spec())]
    if not packages:
        return ""
    lines = []
    for package in packages:
        skills = "、".join(skill["name"] for skill in package["skills"])
        lines.append(f"- **{package['name']}**（版本 {package['version']}）：{skills}")
    listed = "\n".join(lines)
    return f"""
## 技能包

規劃模組的 `skill_packages` 指向執行目錄下的 `skill_packages/<名稱>/`。把壓縮檔解開在與程式碼同一層，這幾個技能就跟著走：

{listed}

[下載技能包壓縮檔](/playground/source/skill-packages.zip)
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