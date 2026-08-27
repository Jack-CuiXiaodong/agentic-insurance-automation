"""RAG retrieval tests."""

from rag.ingest import load_chunks
from rag.retriever import LexicalRetriever, _tokenize


def test_chunks_load_with_shape():
    chunks = load_chunks()
    assert chunks, "knowledge base should produce chunks"
    for c in chunks:
        assert c.source and c.text


def test_tokenizer_handles_chinese():
    """A Latin-only tokenizer returns [] here, which silently empties every
    vector and makes retrieval return nothing at all."""
    tokens = _tokenize("自动核赔限额")
    assert tokens
    assert "自动" in tokens  # bigram
    assert "核赔" in tokens


def test_tokenizer_still_handles_latin_and_mixed():
    assert _tokenize("auto processing limit") == ["auto", "processing", "limit"]
    mixed = _tokenize("维修发票 invoice")
    assert "invoice" in mixed and "发票" in mixed


def test_retrieves_approval_threshold_rule():
    r = LexicalRetriever()
    hits = r.search("赔付金额超过限额需要人工核赔", k=3)
    assert hits
    sources = {h.source for h in hits}
    assert sources & {"核赔权限.md", "理赔规则.md", "转人工规则.md"}


def test_retrieves_document_requirements():
    r = LexicalRetriever()
    hits = r.search("车险理赔需要哪些必需单证 定损单 事故认定书", k=3)
    assert any(h.source == "单证要求.md" for h in hits)


def test_retrieves_invoice_verification_rule():
    r = LexicalRetriever()
    hits = r.search("维修发票 增值税 查验 验真", k=3)
    assert any(h.source == "发票查验规则.md" for h in hits)


def test_scores_are_ranked_descending():
    r = LexicalRetriever()
    hits = r.search("欺诈嫌疑 转人工 升级处理", k=5)
    scores = [h.score for h in hits]
    assert scores == sorted(scores, reverse=True)
