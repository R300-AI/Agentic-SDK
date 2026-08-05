from __future__ import annotations

import base64

from agentic_sdk.core.entities import Attachment


_SUPPORTED_IMAGE_MEDIA_TYPES = {"image/png", "image/jpeg", "image/webp"}


def image_url_for_attachment(attachment: Attachment) -> str | None:
    media_type = (attachment.media_type or "").lower()
    if attachment.kind != "image" and not media_type.startswith("image/"):
        return None
    if media_type and media_type not in _SUPPORTED_IMAGE_MEDIA_TYPES:
        return None
    if isinstance(attachment.content, bytes):
        encoded = base64.b64encode(attachment.content).decode("ascii")
        return f"data:{media_type or 'image/png'};base64,{encoded}"
    content = str(attachment.content).strip()
    return content if content.startswith(("data:image/", "http://", "https://")) else None
