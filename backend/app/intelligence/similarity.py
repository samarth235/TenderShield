"""AI Bid Document Intelligence (Stage 7).

Bid PDF -> text -> section chunking -> embeddings -> cosine similarity, reported at
document, section and passage level so every score can be inspected at its source.

Backends:
  * ``tfidf``  - TF-IDF (word 1-2 grams) vectors; offline and deterministic (default).
  * ``sbert``  - sentence-transformers embeddings (install requirements-ml.txt).
"""

from __future__ import annotations

import logging
import re
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timezone
from itertools import combinations

import numpy as np

from ..config import get_settings
from ..db import fetch_all, put_artifact
from ..ingestion.pdf_text import document_pages

log = logging.getLogger(__name__)

HIGH_OVERLAP = 0.80
PASSAGE_MATCH = 0.75
HEADING = re.compile(r"^(\d+)\.\s+(.+)$")
FOOTER = re.compile(r"^Page \d+ of \d+$")


@dataclass
class Section:
    title: str
    page: int
    text: str
    sentences: list[str] = field(default_factory=list)


@dataclass
class BidDocument:
    document_id: str
    vendor_id: str
    filename: str
    sections: list[Section]

    @property
    def text(self) -> str:
        return "\n".join(s.text for s in self.sections)


def split_sections(pages: list[tuple[int, str]]) -> list[Section]:
    sections: list[Section] = []
    for page, text in pages:
        lines = [ln for ln in text.splitlines()[1:] if not FOOTER.match(ln)]  # drop running header / footer
        current: Section | None = None
        for line in lines:
            heading = HEADING.match(line)
            if heading and len(line) < 80:
                current = Section(title=heading.group(2).strip(), page=page, text="")
                sections.append(current)
            elif current is not None:
                current.text = f"{current.text} {line}".strip()
    for s in sections:
        s.sentences = [p.strip() for p in re.split(r"(?<=[.!?])\s+", s.text) if len(p.strip()) > 20]
    return sections


class TfidfEmbedder:
    name = "tfidf"

    def __init__(self, corpus: list[str]):
        from sklearn.feature_extraction.text import TfidfVectorizer

        self.vectorizer = TfidfVectorizer(ngram_range=(1, 2), sublinear_tf=True, stop_words="english", min_df=1)
        self.vectorizer.fit(corpus)

    def encode(self, texts: list[str]) -> np.ndarray:
        matrix = self.vectorizer.transform(texts).toarray()
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        return matrix / np.where(norms == 0, 1, norms)


class SbertEmbedder:
    name = "sbert"

    def __init__(self, model_name: str):
        from sentence_transformers import SentenceTransformer

        self.model = SentenceTransformer(model_name)

    def encode(self, texts: list[str]) -> np.ndarray:
        return np.asarray(self.model.encode(texts, normalize_embeddings=True))


def make_embedder(corpus: list[str]):
    settings = get_settings()
    if settings.embedding_backend == "sbert":
        try:
            return SbertEmbedder(settings.sbert_model)
        except Exception as exc:  # missing package or model download failure
            log.warning("sentence-transformers unavailable (%s); using TF-IDF", exc)
    return TfidfEmbedder(corpus)


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.clip(np.dot(a, b), 0.0, 1.0))


def load_bid_documents(conn: sqlite3.Connection, tender_id: str) -> list[BidDocument]:
    docs = fetch_all(conn, "SELECT * FROM documents WHERE tender_id = ? AND kind = 'technical_bid' ORDER BY vendor_id",
                     (tender_id,))
    return [
        BidDocument(d["document_id"], d["vendor_id"], d["filename"], split_sections(document_pages(conn, d["document_id"])))
        for d in docs
    ]


def compare_documents(docs: list[BidDocument]) -> tuple[list[dict], str]:
    all_sentences = [s for d in docs for sec in d.sections for s in sec.sentences]
    corpus = [d.text for d in docs] + [sec.text for d in docs for sec in d.sections] + all_sentences
    embedder = make_embedder(corpus)

    doc_vecs = embedder.encode([d.text for d in docs])
    sec_vecs = {
        (d.document_id, i): v
        for d in docs
        for i, v in enumerate(embedder.encode([s.text for s in d.sections]) if d.sections else [])
    }
    sent_vecs = dict(zip(all_sentences, embedder.encode(all_sentences))) if all_sentences else {}

    pairs = []
    for (ia, a), (ib, b) in combinations(enumerate(docs), 2):
        sections = []
        passages = []
        b_by_title = {s.title.lower(): (j, s) for j, s in enumerate(b.sections)}
        for i, sa in enumerate(a.sections):
            match = b_by_title.get(sa.title.lower())
            if match is None:
                continue
            j, sb = match
            sim = cosine(sec_vecs[(a.document_id, i)], sec_vecs[(b.document_id, j)])
            sections.append({
                "title": sa.title, "similarity": round(sim, 4),
                "a": {"document_id": a.document_id, "page": sa.page, "excerpt": sa.text[:240]},
                "b": {"document_id": b.document_id, "page": sb.page, "excerpt": sb.text[:240]},
            })
            if sim >= HIGH_OVERLAP:
                for sent_a in sa.sentences:
                    best = max(sb.sentences, key=lambda s: cosine(sent_vecs[sent_a], sent_vecs[s]), default=None)
                    if best is None:
                        continue
                    score = cosine(sent_vecs[sent_a], sent_vecs[best])
                    if score >= PASSAGE_MATCH:
                        passages.append({
                            "section": sa.title, "similarity": round(score, 4),
                            "a": {"document_id": a.document_id, "page": sa.page, "text": sent_a},
                            "b": {"document_id": b.document_id, "page": sb.page, "text": best},
                        })
        passages.sort(key=lambda p: -p["similarity"])
        pairs.append({
            "vendors": [a.vendor_id, b.vendor_id],
            "documents": [a.document_id, b.document_id],
            "filenames": [a.filename, b.filename],
            "document_similarity": round(cosine(doc_vecs[ia], doc_vecs[ib]), 4),
            "sections": sections,
            "high_overlap_sections": [s["title"] for s in sections if s["similarity"] >= HIGH_OVERLAP],
            "passages": passages[:12],
        })
    pairs.sort(key=lambda p: -p["document_similarity"])
    return pairs, embedder.name


def run_similarity(conn: sqlite3.Connection, tender_id: str) -> dict:
    docs = load_bid_documents(conn, tender_id)
    pairs, backend = compare_documents(docs) if len(docs) > 1 else ([], "none")
    sims = [p["document_similarity"] for p in pairs]
    result = {
        "tender_id": tender_id,
        "backend": backend,
        "documents": [{"document_id": d.document_id, "vendor_id": d.vendor_id, "filename": d.filename,
                       "sections": [s.title for s in d.sections]} for d in docs],
        "pairs": pairs,
        "baseline": {
            "median": round(float(np.median(sims)), 4) if sims else None,
            "max": round(float(np.max(sims)), 4) if sims else None,
        },
        "thresholds": {"high_overlap_section": HIGH_OVERLAP, "passage_match": PASSAGE_MATCH},
    }
    put_artifact(conn, tender_id, "similarity", result, datetime.now(timezone.utc).isoformat(timespec="seconds"))
    return result
