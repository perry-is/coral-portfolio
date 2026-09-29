"""Minimal local SQLite persistence for synthetic memories and route receipts."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MemoryRecord:
    memory_id: int
    content: str
    disclosure: str


class LocalStore:
    """Own a SQLite connection containing only local demo state."""

    def __init__(self, database_path: Path | str) -> None:
        self.path = Path(database_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
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
                    disclosure TEXT NOT NULL,
                    decision TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    source_refs_json TEXT NOT NULL,
                    context_sha256 TEXT NOT NULL,
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

    def get_memory(self, memory_id: int) -> MemoryRecord:
        row = self.connection.execute(
            "SELECT id, content, disclosure FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        if row is None:
            raise KeyError(f"No memory with id {memory_id}")
        return MemoryRecord(int(row["id"]), str(row["content"]), str(row["disclosure"]))

    def write_receipt(self, receipt: dict[str, object]) -> int:
        with self.connection:
            cursor = self.connection.execute(
                """INSERT INTO operation_receipts
                   (operation_id, purpose, provider_id, provider_locality, disclosure,
                    decision, reason, source_refs_json, context_sha256, policy_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    receipt["operation_id"], receipt["purpose"], receipt["provider_id"],
                    receipt["provider_locality"], receipt["disclosure"], receipt["decision"],
                    receipt["reason"], receipt["source_refs_json"],
                    receipt["context_sha256"], receipt["policy_version"],
                ),
            )
        return int(cursor.lastrowid)

    def receipt_count(self) -> int:
        row = self.connection.execute("SELECT COUNT(*) AS count FROM operation_receipts").fetchone()
        assert row is not None
        return int(row["count"])

    def close(self) -> None:
        self.connection.close()

    def __enter__(self) -> "LocalStore":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
