"""Knowledge base import (Markdown/CSV) and an in-memory index for fact retrieval."""
from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field

from rapidfuzz import fuzz

from .textutils import Quantity, content_words, extract_quantities, overlap


@dataclass
class FactRecord:
    """A KB fact in the form the judges and mock agent consume."""

    id: int
    category: str
    title: str
    content: str
    quantities: list[Quantity] = field(default_factory=list)

    @property
    def text(self) -> str:
        return f"{self.title}. {self.content}"


@dataclass
class ScoredFact:
    fact: FactRecord
    score: float
    overlap: float


class KnowledgeIndex:
    """Ranks KB facts by similarity to a sentence (content-word overlap + fuzzy match)."""

    def __init__(self, facts: list[FactRecord]):
        self.facts = facts
        for fact in self.facts:
            if not fact.quantities:
                fact.quantities = extract_quantities(fact.content)
        self.all_quantity_keys: set[str] = {q.key for f in facts for q in f.quantities}

    @classmethod
    def from_rows(cls, rows: list[dict[str, object]]) -> KnowledgeIndex:
        return cls(
            [
                FactRecord(int(r.get("id", i)), str(r.get("category", "")), str(r["title"]), str(r["content"]))
                for i, r in enumerate(rows)
            ]
        )

    def rank(self, sentence: str, top_k: int = 3) -> list[ScoredFact]:
        """Return the top-k facts most related to ``sentence``."""
        scored: list[ScoredFact] = []
        for fact in self.facts:
            ov = overlap(sentence, fact.text)
            fz = fuzz.token_set_ratio(sentence.lower(), fact.text.lower()) / 100
            scored.append(ScoredFact(fact, 0.65 * ov + 0.35 * fz, ov))
        scored.sort(key=lambda s: s.score, reverse=True)
        return scored[:top_k]

    def search(self, query: str, limit: int = 5) -> list[FactRecord]:
        """Facts relevant to a free-text query (used for LLM prompts and the UI)."""
        words = content_words(query)
        if not words:
            return self.facts[:limit]
        return [s.fact for s in self.rank(query, top_k=limit) if s.score > 0.15]


def parse_markdown(text: str) -> list[dict[str, str]]:
    """Parse ``## Category`` / ``### Title`` / body Markdown into fact dicts.

    Bullet lists under a category without ``###`` headings are imported as one
    fact per bullet, titled with the bullet's first words.
    """
    facts: list[dict[str, str]] = []
    category = "General"
    title: str | None = None
    body: list[str] = []

    def flush() -> None:
        nonlocal title, body
        content = " ".join(line.strip() for line in body if line.strip())
        if title and content:
            facts.append({"category": category, "title": title, "content": content})
        title, body = None, []

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("### "):
            flush()
            title = stripped[4:].strip()
        elif stripped.startswith("## "):
            flush()
            category = stripped[3:].strip()
        elif stripped.startswith("# "):
            flush()
        elif re.match(r"^[-*]\s+", stripped) and title is None:
            item = re.sub(r"^[-*]\s+", "", stripped)
            facts.append({"category": category, "title": " ".join(item.split()[:6]).rstrip(".:,"), "content": item})
        elif title is not None:
            body.append(stripped)
    flush()
    return facts


def parse_csv(text: str) -> list[dict[str, str]]:
    """Parse CSV with columns ``category,title,content[,tags]`` (header required)."""
    reader = csv.DictReader(io.StringIO(text))
    facts: list[dict[str, str]] = []
    for row in reader:
        lowered = {k.strip().lower(): (v or "").strip() for k, v in row.items() if k}
        content = lowered.get("content") or lowered.get("fact") or ""
        if not content:
            continue
        facts.append(
            {
                "category": lowered.get("category") or "General",
                "title": lowered.get("title") or " ".join(content.split()[:6]),
                "content": content,
                "tags": lowered.get("tags", ""),
            }
        )
    return facts
