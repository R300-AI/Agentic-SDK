from __future__ import annotations

import pytest

from agentic_sdk.core import Attachment
from agentic_sdk.memory import InContextMemory, InMemoryStore


@pytest.mark.parametrize(
    "attachment,expected_image_url",
    [
        (Attachment(kind="image", content=b"image-bytes", media_type="image/png"), "data:image/png;base64,aW1hZ2UtYnl0ZXM="),
        (Attachment(kind="image", content="data:image/jpeg;base64,abc", media_type="image/jpeg"), "data:image/jpeg;base64,abc"),
        (Attachment(kind="image", content="https://example.test/image.webp", media_type="image/webp"), "https://example.test/image.webp"),
        (Attachment(kind="image", content=b"gif", media_type="image/gif"), None),
        (Attachment(kind="text", content=b"not-an-image", media_type="text/plain"), None),
    ],
)
def test_memory_stores_render_attachments_identically(attachment, expected_image_url):
    stores = [InContextMemory(), InMemoryStore()]

    for store in stores:
        store.append_message("user", "請判讀附件", attachments=[attachment])

    messages = [store.as_openai_messages(include_attachments=True) for store in stores]

    assert messages[0] == messages[1]
    if expected_image_url is None:
        assert messages[0][-1]["content"] == "請判讀附件"
    else:
        assert messages[0][-1]["content"] == [
            {"type": "text", "text": "請判讀附件"},
            {"type": "image_url", "image_url": {"url": expected_image_url}},
        ]
