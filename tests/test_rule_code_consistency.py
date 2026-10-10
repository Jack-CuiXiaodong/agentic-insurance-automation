"""The business constants in risk/engine.py and the Chinese wording in
knowledge/*.md say the same thing in two different languages (Python and
prose) for two different audiences (the guardrail and the human reviewer).
Nothing *forces* them to agree -- CLAUDE.md asks contributors to keep them in
sync by hand. This file is the enforcement: it extracts the numbers and lists
the documents actually state and compares them to the constants, so a drift
between "what the code enforces" and "what the evidence shown to a human
claims it enforces" fails CI instead of surfacing as a support ticket.
"""

from __future__ import annotations

import glob
import os
import re

from risk.engine import AUTO_LIMIT, REQUIRED_DOCS

_KNOWLEDGE_DIR = os.path.join(os.path.dirname(__file__), "..", "knowledge")

# Matches "超过 10,000 元" / "限额人民币 10,000 元" style phrasing.
_LIMIT_RE = re.compile(r"(?:超过|限额)\D{0,8}?([\d,]+)\s*元")

_FILES_THAT_MUST_STATE_THE_LIMIT = ["理赔规则.md", "核赔权限.md", "转人工规则.md"]


def _read(name: str) -> str:
    with open(os.path.join(_KNOWLEDGE_DIR, name), "r", encoding="utf-8") as fh:
        return fh.read()


def _limit_mentions(text: str) -> list[int]:
    return [int(m.replace(",", "")) for m in _LIMIT_RE.findall(text)]


def test_detector_finds_the_limit_in_a_synthetic_sentence():
    """Self-check for the regex itself, independent of the real files."""
    assert _limit_mentions("金额超过人民币 10,000 元的，须转人工。") == [10_000]
    assert _limit_mentions("自动核赔限额为 10,000 元。") == [10_000]
    assert _limit_mentions("没有提到金额门槛的一句话。") == []


def test_every_rule_file_states_the_same_amount_as_auto_limit():
    for name in _FILES_THAT_MUST_STATE_THE_LIMIT:
        mentions = _limit_mentions(_read(name))
        assert mentions, f"{name} 没有提到任何金额门槛"
        assert all(m == AUTO_LIMIT for m in mentions), (
            f"{name} 里的金额门槛 {mentions} 和 risk.engine.AUTO_LIMIT="
            f"{AUTO_LIMIT} 不一致"
        )


def test_no_rule_file_states_a_different_amount():
    """Catches the other direction of drift: a stray mention of some other
    number anywhere in the knowledge base that nothing above would see."""
    for path in sorted(glob.glob(os.path.join(_KNOWLEDGE_DIR, "*.md"))):
        mentions = _limit_mentions(open(path, encoding="utf-8").read())
        bad = [m for m in mentions if m != AUTO_LIMIT]
        assert not bad, f"{os.path.basename(path)} 提到了和 AUTO_LIMIT 不一致的金额：{bad}"


_DOC_BULLET_RE = re.compile(r"^- \*\*(.+?)\*\*", re.MULTILINE)


def _required_docs_section(coverage: str) -> str:
    text = _read("单证要求.md")
    marker = f"## {coverage}"
    start = text.index(marker) + len(marker)
    rest = text[start:]
    nxt = rest.find("\n## ")
    return rest if nxt == -1 else rest[:nxt]


def test_document_requirements_match_the_code():
    for coverage, required in REQUIRED_DOCS.items():
        section = _required_docs_section(coverage)
        listed = _DOC_BULLET_RE.findall(section)
        assert listed == required, (
            f"单证要求.md 里「{coverage}」列出 {listed}，"
            f"risk.engine.REQUIRED_DOCS 是 {required}"
        )


def test_the_detector_actually_catches_drift(tmp_path, monkeypatch):
    """Prove the checks above are not vacuously true: point them at a knowledge
    directory with a changed amount and a changed document list and confirm
    both fail. This directly exercises the manual check the task description
    asked for (change 10,000 -> 20,000, watch it go red, change it back) --
    automated here so it stays true without anyone remembering to redo it."""
    bad_dir = tmp_path / "knowledge"
    bad_dir.mkdir()
    (bad_dir / "理赔规则.md").write_text(
        "# 车险理赔处理规则\n\n## 金额门槛\n- 赔付金额超过 20,000 元的，须转人工。\n",
        encoding="utf-8",
    )
    (bad_dir / "单证要求.md").write_text(
        "# 单证要求\n\n## 机动车损失保险\n- **定损单** —— 说明。\n",
        encoding="utf-8",
    )

    bad_limit_mentions = _limit_mentions((bad_dir / "理赔规则.md").read_text(encoding="utf-8"))
    assert bad_limit_mentions == [20_000]
    assert bad_limit_mentions != [AUTO_LIMIT]

    def _bad_section(coverage: str) -> str:
        text = (bad_dir / "单证要求.md").read_text(encoding="utf-8")
        marker = f"## {coverage}"
        start = text.index(marker) + len(marker)
        return text[start:]

    bad_listed = _DOC_BULLET_RE.findall(_bad_section("机动车损失保险"))
    assert bad_listed == ["定损单"]
    assert bad_listed != REQUIRED_DOCS["机动车损失保险"]
