"""Local SQLite persistence for memories and operation receipts."""

from __future__ import annotations

import math
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path


# Words too common to say anything about relevance.
_STOPWORDS = frozenset(
    "a an and are as at be by does do for from has have how i in is it its of on or "
    "our that the their this to was what when where which who why will with you your".split()
)


def keywords(text: str) -> set[str]:
    """Lowercase content words, ignoring stopwords and very short tokens."""
    words = set()
    for word in re.findall(r"[a-z0-9]+", text.casefold()):
        if len(word) <= 2 or word in _STOPWORDS:
            continue
        if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
            word = word[:-1]  # crude plural folding: "reviews" matches "review"
        words.add(word)
    return words


@dataclass(frozen=True)
class MemoryRecord:
    memory_id: int
    content: str
    disclosure: str


class LocalStore:
    """Own a SQLite connection holding local memories and receipts."""

    def __init__(self, database_path: Path | str) -> None:
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.initialize()

    def initialize(self) -> None:
        with self.connection:
            self.connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS memories (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    demo_key TEXT NOT NULL UNIQUE,
                    content TEXT NOT NULL CHECK(length(trim(content)) > 0),
                    disclosure TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS operation_receipts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    operation_id TEXT NOT NULL UNIQUE,
                    purpose TEXT NOT NULL,
                    provider_id TEXT,
                    provider_locality TEXT,
                    model_id TEXT,
                    disclosure TEXT NOT NULL,
                    decision TEXT NOT NULL CHECK(decision IN ('allowed', 'denied', 'failed')),
                    reason TEXT NOT NULL,
                    source_refs_json TEXT NOT NULL,
                    context_sha256 TEXT NOT NULL,
                    response_sha256 TEXT,
                    policy_version TEXT NOT NULL,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )

    def add_memory(self, demo_key: str, content: str, disclosure: str) -> int:
        with self.connection:
            self.connection.execute(
                "INSERT OR IGNORE INTO memories(demo_key, content, disclosure) VALUES (?, ?, ?)",
                (demo_key, content, disclosure),
            )
        row = self.connection.execute(
            "SELECT id FROM memories WHERE demo_key = ?", (demo_key,)
        ).fetchone()
        assert row is not None
        return int(row["id"])

    def search_memories(self, query: str, limit: int = 3) -> list[MemoryRecord]:
        """Return the memories most relevant to the query.

        Deliberately simple and explainable (no embeddings, no vector store):
        each shared keyword scores more when it is rare across memories, so a
        word that appears everywhere ("team") counts for nothing. Memories that
        score under half of the best match are dropped. Keeping weak matches out
        matters for privacy as well as quality: anything retrieved can tighten
        the disclosure level of the whole request.
        """
        wanted = keywords(query)
        if not wanted or limit < 1:
            return []
        rows = [
            (MemoryRecord(int(r["id"]), str(r["content"]), str(r["disclosure"])), keywords(r["content"]))
            for r in self.connection.execute("SELECT id, content, disclosure FROM memories")
        ]
        total = len(rows)
        frequency: dict[str, int] = {}
        for _, words in rows:
            for word in words:
                frequency[word] = frequency.get(word, 0) + 1
        scored = []
        for record, words in rows:
            score = sum(math.log(total / frequency[w]) for w in wanted & words)
            if score > 0:
                scored.append((score, record))
        if not scored:
            return []
        best = max(score for score, _ in scored)
        relevant = [(s, r) for s, r in scored if s >= best / 2]
        relevant.sort(key=lambda item: (-item[0], item[1].memory_id))
        return [record for _, record in relevant[:limit]]

    def write_receipt(self, receipt: dict[str, object]) -> int:
        columns = (
            "operation_id", "purpose", "provider_id", "provider_locality", "model_id",
            "disclosure", "decision", "reason", "source_refs_json", "context_sha256",
            "response_sha256", "policy_version",
        )
        with self.connection:
            cursor = self.connection.execute(
                f"INSERT INTO operation_receipts ({', '.join(columns)}) "
                f"VALUES ({', '.join('?' for _ in columns)})",
                tuple(receipt.get(column) for column in columns),
            )
        return int(cursor.lastrowid)

    def receipts(self) -> list[dict[str, object]]:
        rows = self.connection.execute("SELECT * FROM operation_receipts ORDER BY id")
        return [dict(row) for row in rows]

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "LocalStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
