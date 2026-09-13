"""C-1532: the deck left its slides blank; the report announced 「根拠 5 件」.

Same index, same subject, opposite manner. Asked for a report on 「犬の飼い方」
over a corpus that has never heard of dogs, the report kept all five retrieved
facts - about jam and weekly sales - printed them under 「わかっていること」 with
a repository path beside each, and led with a confident count. The deck, asked
the same thing, demanded evidence per slide, left three blank, and said which.

The filter was not broken so much as blind. A one-character subject has no
two-character term to be found in (C-1512), so ``subject_terms`` offered
nothing and ``on_topic`` could not judge at all - while the *answer* path had
already been given probes that can see 犬 (C-1510's windows plus C-1512's lone
kanji). The report was simply asking a weaker question than its sibling.

What is deliberately NOT changed: the facts are still kept. Setting them all
aside produced a document of blank headings, which is the failure C-1403's
stand-down exists to prevent. The count was never wrong about how many
passages are in the file - it was wrong about what they are evidence for. So
this is a disclosure, not a filter.
"""

from __future__ import annotations

from sidra_ai.creation.documents import generate_document
from sidra_ai.creation.evidence import Fact, on_topic, subject_unmatched

JAM = Fact(text="ジャムは砂糖を加えて煮詰め、瓶を煮沸します。", source="recipes/jam-0.md")
WEEKLY = Fact(text="週報には今週の売上が 120 万円だったことを並べます。", source="docs/weekly-0.md")
FACTS = [JAM, WEEKLY]


def test_a_one_character_subject_is_now_visible_to_the_filter() -> None:
    """The hole itself. Before, 「犬」 produced no subject term at all, so the
    filter stood down for the same reason a subject-less request does."""

    assert subject_unmatched("犬の飼い方についてのレポートをまとめて作って", FACTS)


def test_nothing_is_set_aside_even_so() -> None:
    """C-1403 is not being reverted: a report of blank headings was worse."""

    kept, aside = on_topic("犬の飼い方についてのレポートをまとめて作って", FACTS)

    assert [fact.source for fact in kept] == [JAM.source, WEEKLY.source]
    assert aside == []


def test_a_subject_the_corpus_knows_is_still_filtered() -> None:
    """The other direction. A disclosure that fired everywhere would be a
    report that never trusts its own evidence."""

    kept, aside = on_topic("ジャムについてのレポートをまとめて作って", FACTS)

    assert [fact.source for fact in kept] == [JAM.source]
    assert [fact.source for fact in aside] == [WEEKLY.source]
    assert not subject_unmatched("ジャムについてのレポートをまとめて作って", FACTS)


def test_a_request_naming_no_subject_says_nothing_new() -> None:
    """「レポートを作って」 names no subject, so there is nothing to be off."""

    assert not subject_unmatched("レポートを作って", FACTS)


def test_the_artifact_noun_is_not_the_subject() -> None:
    """The trap :func:`_artifact_terms` was written for, one unit along: every
    passage here contains 「レポート」, so a probe built from the request's own
    artifact noun would match everything and the filter would never fire."""

    facts = [Fact(text="レポートの書き方の手順です。", source="docs/how-0.md")]

    assert subject_unmatched("ジャムについてのレポートをまとめて作って", facts)


def test_the_document_says_so_where_a_reader_starts() -> None:
    """In 概要, not only in a section a skim never reaches."""

    document = generate_document(
        "犬の飼い方についてのレポートをまとめて作って",
        facts=FACTS,
        subject_unmatched=True,
    )

    summary = document.markdown.split("## わかっていること")[0]
    assert "触れているものは" in summary
    assert "根拠として読まないでください" in summary
    assert "犬の飼い方そのものについての根拠は" in document.markdown.replace("「", "").replace("」", "")


def test_the_document_still_prints_the_evidence_it_kept() -> None:
    """Otherwise this is C-1403's blank-heading report with a caveat on top."""

    document = generate_document(
        "犬の飼い方についてのレポートをまとめて作って",
        facts=FACTS,
        subject_unmatched=True,
    )

    assert "煮沸" in document.markdown
    assert "recipes/jam-0.md" in document.markdown


def test_a_matched_subject_keeps_the_old_wording() -> None:
    """No caveat where none is due."""

    document = generate_document("ジャムについてのレポートをまとめて作って", facts=[JAM])

    assert "触れているものは" not in document.markdown
    assert "索引した資料から見つかった根拠を" in document.markdown


def test_a_subject_written_against_the_artifact_noun_still_matches() -> None:
    """The false alarm this nearly shipped with, and the reason the artifact
    noun is cut out of the request before the probes are built.

    Kanji and katakana run together with no kana between them, so
    「進捗レポートを作って」 is one run - 進捗レポート - whose three-character
    windows are 進捗レ and 捗レポ. Both straddle the subject and the artifact
    noun and match neither alone, so a fact that says 「進捗は 3 件です」
    failed to match its own subject and the report announced that the index
    knew nothing about 進捗. That is C-1403's case, the one this must never
    touch: subtracting the artifact's probes afterwards does not help,
    because the straddling windows are not the artifact's either.

    Caught by ``test_creation_empty_honest`` rather than by anything written
    for C-1532 - the destruction battery cannot find a case nobody thought
    of, and the existing suite could.
    """

    facts = [Fact(text="進捗は 3 件です。", source="PR-1.md")]

    assert not subject_unmatched("進捗レポートを作って", facts)
    kept, aside = on_topic("進捗レポートを作って", facts)
    assert [fact.source for fact in kept] == ["PR-1.md"]
    assert aside == []
