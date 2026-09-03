"""C-1403: a report must cite only the subject it was asked about.

The unit tests pin ``on_topic``'s rule, including the two ways it is wrong
if written carelessly - the artifact word must not count as a subject, and
a request with no subject at all must not empty the report. The last test
is the product one: it drives the real ``chat`` path.
"""

from __future__ import annotations

from sidra_ai.creation.evidence import Fact, on_topic


def _fact(text: str, path: str = "docs/a.md") -> Fact:
    return Fact(text=text, source=f"tukemen-rgb/sidra-ai {path}")


def test_facts_sharing_a_subject_term_are_kept() -> None:
    kept, aside = on_topic("週報をまとめて", [_fact("週報の売上は 120 万円でした。")])
    assert [f.text for f in aside] == []
    assert len(kept) == 1


def test_facts_sharing_nothing_are_set_aside() -> None:
    """The failure this exists to stop: an intruder inside a mixture.

    The on-topic fact has to be there. A batch with nothing on-topic is the
    unjudgeable case below, not this one.
    """

    kept, aside = on_topic(
        "週報をまとめて",
        [_fact("週報の売上は 120 万円。"), _fact("ジャムは砂糖を 60% 加えます。")],
    )
    assert [f.text for f in kept] == ["週報の売上は 120 万円。"]
    assert [f.text for f in aside] == ["ジャムは砂糖を 60% 加えます。"]


def test_the_artifact_word_is_not_a_subject() -> None:
    """「レポート」 names what is being asked for, not what it is about.

    This is the bug the first draft had: a jam passage that happened to say
    「レポート」 counted as on-topic for a weekly-report request, which is
    the exact failure the filter exists to stop.
    """

    kept, aside = on_topic(
        "週報についてのレポートをまとめて作って",
        [
            _fact("週報についてのレポートです。売上は 120 万円。"),
            _fact("ジャムについてのレポートをまとめます。砂糖を加えます。"),
        ],
    )
    assert [f.text for f in aside] == [
        "ジャムについてのレポートをまとめます。砂糖を加えます。"
    ]
    assert len(kept) == 1


def test_a_request_with_no_subject_keeps_everything() -> None:
    """Unjudgeable is not the same as off-topic.

    With no subject term there is nothing to compare against, so the
    pre-C-1403 behaviour stands rather than the report coming back empty.
    """

    facts = [_fact("ジャムは砂糖を 60% 加えます。"), _fact("週報の売上は 120 万円。")]
    kept, aside = on_topic("レポートを作って", facts)
    assert len(kept) == 2
    assert aside == []


def test_nothing_matching_keeps_everything_rather_than_emptying_the_report() -> None:
    """The floor. Found by a shipped test, not by thinking about it.

    「進捗レポートを作って」 over this repository's own docs is made of
    facts that never say 進捗. A strict reading set all of them aside and
    produced a document of blank headings - worse than the behaviour it
    replaced. When nothing matches, the filter has no evidence it
    understood the request, so it stands down.
    """

    facts = [
        _fact("索引した文書が 482 件ある", "docs/OUTCOMES.md"),
        _fact("回答には引用が付く", "docs/ARCHITECTURE.md"),
    ]
    kept, aside = on_topic("進捗レポートを作って", facts)
    assert [f.text for f in kept] == [f.text for f in facts]
    assert aside == []


def test_both_halves_are_returned_so_the_caller_can_say_so() -> None:
    facts = [_fact("週報の売上は 120 万円。"), _fact("ジャムは砂糖を加えます。")]
    kept, aside = on_topic("週報をまとめて", facts)
    assert len(kept) + len(aside) == len(facts)


def test_a_mixed_corpus_does_not_leak_into_the_report() -> None:
    """The product check: two subjects in one corpus, each asked for.

    Asserts on ``mixed`` as well as on the result, because a corpus that
    stopped handing over unrelated evidence would make the other two
    assertions pass with the filter deleted.
    """

    from sidra_ai.evals.document_topicality import evaluate_document_topicality

    result = evaluate_document_topicality()
    assert result.mixed == result.mixed_total, result.failures
    assert result.clean == result.mixed_total, result.failures
    assert result.kept == result.mixed_total, result.failures
    assert result.passed, result.failures
