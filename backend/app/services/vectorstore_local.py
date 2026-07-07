"""Local SQLite vector store — the zero-setup default backend.

Chunks and their embeddings live in a single SQLite file (separate from the
app database so a wipe/reingest never touches research history). Vectors are
L2-normalized float32 blobs; queries load one ticker's vectors (a filing is a
few hundred chunks) and rank by dot product with numpy — exact cosine, no
index needed at this scale.
"""

from __future__ import annotations

import asyncio
import json
import sqlite3
from pathlib import Path

import numpy as np

from app.config import get_settings
from app.observability.logging import get_logger
from app.services.chunker import Chunk
from app.services.vectorstore import QueryMatch

log = get_logger(__name__)


def _db_path() -> Path:
    path = Path(get_settings().vector_db_path).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path(), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS chunks (
            ticker      TEXT NOT NULL,
            accession   TEXT NOT NULL,
            chunk_index INTEGER NOT NULL,
            text        TEXT NOT NULL,
            metadata    TEXT NOT NULL,
            vector      BLOB NOT NULL,
            PRIMARY KEY (ticker, accession, chunk_index)
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS ix_chunks_ticker ON chunks (ticker)")
    return conn


def _normalize(vec: list[float]) -> np.ndarray:
    arr = np.asarray(vec, dtype=np.float32)
    norm = float(np.linalg.norm(arr))
    return arr / norm if norm > 0 else arr


async def upsert_chunks(
    ticker: str,
    chunks: list[Chunk],
    vectors: list[list[float]],
) -> int:
    if len(chunks) != len(vectors):
        raise ValueError("chunks and vectors length mismatch")
    if not chunks:
        return 0

    ticker = ticker.upper()
    accession = chunks[0].metadata["accession"]

    def _sync() -> int:
        rows = [
            (
                ticker,
                accession,
                int(c.metadata["chunk_index"]),
                c.text,
                json.dumps(c.metadata, default=str),
                _normalize(vec).tobytes(),
            )
            for c, vec in zip(chunks, vectors, strict=True)
        ]
        with _connect() as conn:
            # Re-ingest is clean: drop prior copies of this accession first.
            conn.execute(
                "DELETE FROM chunks WHERE ticker = ? AND accession = ?",
                (ticker, accession),
            )
            conn.executemany(
                "INSERT OR REPLACE INTO chunks "
                "(ticker, accession, chunk_index, text, metadata, vector) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
        log.info(
            "local_vectorstore_upsert",
            extra={"ticker": ticker, "accession": accession, "chunks": len(rows)},
        )
        return len(rows)

    return await asyncio.to_thread(_sync)


async def query(
    ticker: str,
    vector: list[float],
    top_k: int = 5,
) -> list[QueryMatch]:
    ticker = ticker.upper()

    def _sync() -> list[QueryMatch]:
        with _connect() as conn:
            rows = conn.execute(
                "SELECT text, metadata, vector FROM chunks WHERE ticker = ?",
                (ticker,),
            ).fetchall()
        if not rows:
            return []

        matrix = np.frombuffer(b"".join(r[2] for r in rows), dtype=np.float32).reshape(
            len(rows), -1
        )
        q = _normalize(vector)
        scores = matrix @ q
        order = np.argsort(scores)[::-1][:top_k]
        return [
            QueryMatch(
                score=float(scores[i]),
                text=rows[i][0],
                metadata=json.loads(rows[i][1]),
            )
            for i in order
        ]

    return await asyncio.to_thread(_sync)


def count_chunks_sync(ticker: str | None = None) -> int:
    """Used by the readiness probe; cheap enough to run inline."""
    with _connect() as conn:
        if ticker:
            row = conn.execute(
                "SELECT COUNT(*) FROM chunks WHERE ticker = ?", (ticker.upper(),)
            ).fetchone()
        else:
            row = conn.execute("SELECT COUNT(*) FROM chunks").fetchone()
    return int(row[0])
