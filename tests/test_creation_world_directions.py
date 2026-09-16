"""The dungeon's signposting is true about the dungeon (C-1888).

§3's mission graph, told to the player so §30 does not have to be remembered.
These tests are mostly about how the judge reads: the sentences come off the
running page, and a place counts as named through the page's own room names,
so renaming a room keeps the judge right rather than breaking it.
"""

from __future__ import annotations

from sidra_ai.evals.world_directions_are_true import (
    CLAIMS,
    _fragments,
    _names_room,
    evaluate_world_directions_are_true,
)


def test_all_five_directions_are_true() -> None:
    result = evaluate_world_directions_are_true()
    assert result.failures == ()
    assert result.passed
    assert result.true_claims == len(CLAIMS) == 5
    assert result.checks_total == result.checks_passed + len(result.failures)


def test_a_fragment_has_to_belong_to_one_room_only() -> None:
    """Otherwise 「の」 would name every room in the dungeon."""

    names = ["森のはずれ", "ひかり苔の洞窟", "風の祭壇"]
    assert "洞窟" in _fragments(names[1], [names[0], names[2]])
    assert "祭壇" in _fragments(names[2], [names[0], names[1]])
    # A piece every name carries identifies nothing and must not be offered.
    for name, others in ((names[0], names[1:]), (names[1], [names[0], names[2]])):
        assert all("の" != piece for piece in _fragments(name, others))


def test_naming_is_decided_against_the_pages_own_names() -> None:
    """The judge must not carry the words. Rename the rooms and it follows."""

    names = ["草原", "ふかい井戸", "塔の頂"]
    assert _names_room("東の井戸の敵が鍵を守っている", 1, names)
    assert not _names_room("東の井戸の敵が鍵を守っている", 2, names)
    assert not _names_room("なにも案内しない文", 1, names)


def test_the_judge_holds_no_copy_of_the_sentences() -> None:
    """C-1640's ledger problem: a judge with its own copy of the text goes
    green against a page that now says something else.

    Checked over the string literals the code can compare against, not over
    the prose - the module explains itself with 「洞窟」 as an example, and a
    test that banned the word from comments would be policing writing rather
    than behaviour.
    """

    import ast

    from sidra_ai.evals import world_directions_are_true as mod

    tree = ast.parse(open(mod.__file__, encoding="utf-8").read())
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef)):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstrings.add(id(body[0].value))
    comparable = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
    ]
    assert comparable, "no literals were examined"
    for word in ("洞窟", "祭壇", "ひかり苔"):
        assert not any(word in text for text in comparable), word


def test_the_probe_takes_no_name_the_page_uses() -> None:
    from sidra_ai.evals.world_directions_are_true import _PROBE

    assert "function knock(" not in _PROBE
    for name in ("function find(", "function stand(", "function use("):
        assert name not in _PROBE
