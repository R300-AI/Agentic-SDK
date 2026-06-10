"""KnowledgeBase — 靜態領域知識索引（non-parametric memory）。

設計參考：
- Lewis et al. 2020 "RAG"（arXiv:2005.11401）— parametric vs non-parametric memory 的分工
- MemGPT (Packer et al. 2023, arXiv:2310.08560) — Archival Storage 對應此處 KB
- OpenAI Assistants API — file_search / vector stores 對應此處 KB

與 MemoryStore 的差異：
- KB 是 **預先建立** 的領域知識（產品型錄、SOP、FAQ），不會在 workflow 執行中增長
- MemoryStore 是 **執行中累積** 的對話歷史與經驗（recall storage）
- 兩者並存時，KB 結果優先（領域權威性高於個人對話）

格式為 JSON，方便人工編輯與情境替換。
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class KnowledgeEntry:
    id: str
    title: str
    content: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class KnowledgeHit:
    entry: KnowledgeEntry
    score: float


class KnowledgeBase:
    """檔案載入式知識庫，預設使用詞集相似度檢索（零外部依賴）。"""

    def __init__(self, name: str, entries: list[KnowledgeEntry], description: str = "") -> None:
        self.name = name
        self.description = description
        self.entries = entries

    @classmethod
    def from_file(cls, path: str | Path) -> "KnowledgeBase":
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"KnowledgeBase 檔案不存在：{p}")
        data = json.loads(p.read_text(encoding="utf-8"))
        entries = [
            KnowledgeEntry(
                id=str(e["id"]),
                title=str(e.get("title", "")),
                content=str(e["content"]),
                metadata=dict(e.get("metadata", {})),
            )
            for e in data.get("entries", [])
        ]
        return cls(
            name=str(data.get("name", p.stem)),
            description=str(data.get("description", "")),
            entries=entries,
        )

    def search(self, query: str, top_k: int = 3) -> list[KnowledgeHit]:
        if not query or not self.entries:
            return []
        q_terms = _tokenize(query)
        scored: list[KnowledgeHit] = []
        for e in self.entries:
            # 把 title + content 一起算分，標題命中加權
            text_terms = _tokenize(f"{e.title} {e.title} {e.content}")
            score = _jaccard(q_terms, text_terms)
            if score > 0:
                scored.append(KnowledgeHit(entry=e, score=score))
        scored.sort(key=lambda h: h.score, reverse=True)
        return scored[:top_k]


def _tokenize(text: str) -> set[str]:
    """中文按字切、英數按詞切，兩者並用作為簡易雙語檢索。"""
    tokens: set[str] = set()
    # 英數詞
    for w in re.findall(r"[A-Za-z0-9]+", text.lower()):
        tokens.add(w)
    # CJK 字元（單字 + bigram）
    cjk = re.findall(r"[\u4e00-\u9fff]", text)
    for ch in cjk:
        tokens.add(ch)
    for i in range(len(cjk) - 1):
        tokens.add(cjk[i] + cjk[i + 1])
    return tokens


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    union = len(a | b)
    return inter / union if union else 0.0
