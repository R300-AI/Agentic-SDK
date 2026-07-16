"""Attachment — 多模態使用者輸入的最小資料載體。

設計約束:
- 與框架無關:不依賴 OpenAI / Gemma 等具體 SDK 結構
- data_url 採 RFC 2397(`data:<mime>;base64,<...>`)以避免引入 file storage
- Gateway 與 SDK 共用同一份 dataclass,序列化由 Pydantic 在邊界完成
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

AttachmentKind = Literal["image", "file"]


@dataclass
class Attachment:
    """單一附件條目。

    kind:image / file。image 走多模態 image_url part;file 留待 Phase 2 接 vector index
    mime:MIME type(image/png、image/jpeg…)
    data_url:`data:<mime>;base64,<payload>` 或 https URL;送進 OpenAI 多模態 API 用
    name:原始檔名,僅供顯示與除錯,模型不消費
    """

    kind: AttachmentKind
    mime: str
    data_url: str
    name: str | None = None

    @classmethod
    def from_dict(cls, raw: dict) -> "Attachment":
        return cls(
            kind=raw.get("kind", "image"),
            mime=raw["mime"],
            data_url=raw["data_url"],
            name=raw.get("name"),
        )

    def to_dict(self) -> dict:
        out = {"kind": self.kind, "mime": self.mime, "data_url": self.data_url}
        if self.name:
            out["name"] = self.name
        return out
