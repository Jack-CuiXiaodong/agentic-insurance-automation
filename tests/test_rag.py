"""RAG retrieval tests."""

from rag.ingest import load_chunks
from rag.retriever import LexicalRetriever


def test_chunks_load_with_shape():
    chunks = load_chunks()
    assert chunks, "knowledge base should produce chunks"
    for c in chunks:
        assert c.source and c.text


def test_retrieves_approval_threshold_rule():
    r = LexicalRetriever()
    hits = r.search("claims above the limit require human approval", k=3)
    assert hits
    sources = {h.source for h in hits}
    assert sources & {"approval_rules.md", "claim_rules.md", "escalation_rules.md"}


def test_retrieves_document_requirements():
    r = LexicalRetriever()
    hits = r.search("what supporting documents are required for a medical claim", k=3)
    assert any(h.source == "document_requirements.md" for h in hits)


def test_scores_are_ranked_descending():
    r = LexicalRetriever()
    hits = r.search("fraud indicator escalation", k=5)
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)
