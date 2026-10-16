"""Filing text chunker.

Wraps LangChain's RecursiveCharacterTextSplitter to produce embedding-ready
chunks with per-chunk metadata (ticker, form, accession, filing_date,
chunk_index).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.services.sec_client import Filing

DEFAULT_CHUNK_SIZE = 1000
DEFAULT_CHUNK_OVERLAP = 150

_BOILERPLATE_PATTERNS = [
    # Long runs of dots/dashes used in TOC
    re.compile(r"[.·]{6,}"),
    re.compile(r"-{6,}"),
    # Common XBRL leftover tags if any survived BeautifulSoup
    re.compile(r"<[^>]+>"),
]


@dataclass(slots=True)
class Chunk:
    text: str
    metadata: dict


def _clean(text: str) -> str:
    for pat in _BOILERPLATE_PATTERNS:
        text = pat.sub(" ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def chunk_filing(
    filing: Filing,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[Chunk]:
    if len(filing.raw_text) > 2_000_000:
        raise ValueError("Filing exceeds the supported indexing size")
    cleaned = _clean(filing.raw_text)
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    pieces = splitter.split_text(cleaned)

    if len(pieces) > 2500:
        raise ValueError("Filing exceeds the supported chunk count")
    chunks: list[Chunk] = []
    for i, piece in enumerate(pieces):
        chunks.append(
            Chunk(
                text=piece,
                metadata={
                    "ticker": filing.ticker,
                    "form": filing.form,
                    "accession": filing.accession,
                    "filing_date": filing.filing_date,
                    "chunk_index": i,
                },
            )
        )
    return chunks
