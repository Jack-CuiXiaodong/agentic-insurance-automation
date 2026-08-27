"""Ingest the Markdown knowledge base into retrievable chunks.

Pipeline: ``Markdown files -> sections -> chunks``. Kept deliberately small; the
chunk shape (``id / source / heading / text``) is stable so a heavier vector
store can be swapped in later without changing callers.
"""

from __future__ import annotations

import glob
import os
from dataclasses import dataclass, field
from typing import List

_KNOWLEDGE_DIR = os.path.join(os.path.dirname(__file__), "..", "knowledge")


@dataclass
class Chunk:
    id: str
    source: str
    heading: str
    text: str

    def as_dict(self) -> dict:
        return {"id": self.id, "source": self.source, "heading": self.heading, "text": self.text}


def _split_sections(md: str) -> List[tuple[str, str]]:
    """Split markdown into (heading, body) sections on ``##`` boundaries."""
    sections: List[tuple[str, str]] = []
    heading = ""
    buf: List[str] = []
    for line in md.splitlines():
        if line.startswith("## "):
            if buf:
                sections.append((heading, "\n".join(buf).strip()))
                buf = []
            heading = line[3:].strip()
        elif line.startswith("# "):
            heading = line[2:].strip()
        else:
            buf.append(line)
    if buf:
        sections.append((heading, "\n".join(buf).strip()))
    return [(h, b) for h, b in sections if b]


def load_chunks(knowledge_dir: str = _KNOWLEDGE_DIR) -> List[Chunk]:
    chunks: List[Chunk] = []
    for path in sorted(glob.glob(os.path.join(os.path.abspath(knowledge_dir), "*.md"))):
        source = os.path.basename(path)
        with open(path, "r", encoding="utf-8") as fh:
            md = fh.read()
        for i, (heading, body) in enumerate(_split_sections(md)):
            chunks.append(
                Chunk(id=f"{source}#{i}", source=source, heading=heading, text=body)
            )
    return chunks
