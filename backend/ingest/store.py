from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass
class StoredAcademicDocument:
    source_id: str
    source: str
    type: str
    title: str | None
    url: str | None
    published_at: str | None
    pdf_url: str | None
    full_pdf: bytes


def init_db(db_path: Path) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS academic_documents (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL,
                source TEXT NOT NULL,
                type TEXT NOT NULL,
                title TEXT,
                url TEXT,
                published_at TEXT,
                pdf_url TEXT,
                full_pdf BLOB NOT NULL,
                ingested_at TEXT NOT NULL,
                UNIQUE(source_id, url)
            )
            """
        )
        conn.commit()
    finally:
        conn.close()


def upsert_document(db_path: Path, document: StoredAcademicDocument) -> None:
    init_db(db_path)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute(
            """
            INSERT INTO academic_documents (
                source_id, source, type, title, url, published_at, pdf_url, full_pdf, ingested_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(source_id, url) DO UPDATE SET
                source = excluded.source,
                type = excluded.type,
                title = excluded.title,
                published_at = excluded.published_at,
                pdf_url = excluded.pdf_url,
                full_pdf = excluded.full_pdf,
                ingested_at = excluded.ingested_at
            """,
            (
                document.source_id,
                document.source,
                document.type,
                document.title,
                document.url,
                document.published_at,
                document.pdf_url,
                document.full_pdf,
                datetime.utcnow().isoformat() + "Z",
            ),
        )
        conn.commit()
    finally:
        conn.close()
