from __future__ import annotations

from flask import session

from playground_v2.models import ModeContext


MODE_LABELS = {
    "anonymous": "本機試用",
    "manual_auth": "已登入 AI Hub",
    "aihub_readonly": "AI Hub 唯讀體驗",
    "aihub_editable": "AI Hub 可編輯",
}


def get_mode_context() -> ModeContext:
    mode = session.get("mode", "anonymous")
    source_origin = session.get("source_origin", "manual_new")
    can_edit = mode in {"anonymous", "manual_auth", "aihub_editable"}

    return ModeContext(
        mode=mode,
        label=MODE_LABELS.get(mode, MODE_LABELS["anonymous"]),
        role="direct_user" if mode == "aihub_readonly" else "creator",
        can_save=can_edit,
        can_edit=can_edit,
        can_export=False,
        can_view_code=can_edit,
        is_aihub=mode in {"aihub_readonly", "aihub_editable"},
        source_origin=source_origin,
        source_label=_source_label(source_origin),
    )


def _source_label(source_origin: str) -> str:
    labels = {
        "manual_new": "本機設定",
        "aihub_loaded": "已從 AI Hub 載入",
        "aihub_shared_readonly": "由 AI Hub 分享",
    }
    return labels.get(source_origin, "本機設定")