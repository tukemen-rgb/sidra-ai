"""SameGame enforces the four rules puzzle.py calls its honesty (C-1889).

Five judges already watched this template and all of them sat on top of the
rules - the fall, the economy, the run, the jam sentence, the hammer. §34
事実 1: a rule that does not refuse is not a rule.
"""

from __future__ import annotations

from sidra_ai.evals.puzzle_rules_hold import RULES, evaluate_puzzle_rules_hold


def test_all_four_rules_hold_both_ways() -> None:
    result = evaluate_puzzle_rules_hold()
    assert result.failures == ()
    assert result.passed
    assert result.held == len(RULES) == 4
    assert result.checks_total == result.checks_passed + len(result.failures)


def test_clearing_and_jamming_are_separate_outcomes() -> None:
    """The rule puzzle.py names as the lie it refuses to tell.

    Both end screens have to speak, they have to say different things, and
    the one that claims a clear has to be the board that really emptied.
    """

    result = evaluate_puzzle_rules_hold()
    assert "clear_is_not_jam" in result.rules


def test_the_judge_holds_no_copy_of_the_end_screens() -> None:
    """C-1640, and C-1888 for the same reason one cycle ago.

    Checked over the literals the code can compare against, not the prose -
    the module quotes both sentences while explaining itself.
    """

    import ast

    from sidra_ai.evals import puzzle_rules_hold as mod

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
    labels = set()
    for node in ast.walk(tree):
        targets = (
            node.targets
            if isinstance(node, ast.Assign)
            else [node.target]
            if isinstance(node, ast.AnnAssign)
            else []
        )
        if any(isinstance(t, ast.Name) and t.id == "RULES" for t in targets):
            labels = {
                id(k)
                for k in ast.walk(node)
                if isinstance(k, ast.Constant) and isinstance(k.value, str)
            }
    comparable = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstrings
        and id(node) not in labels
    ]
    assert comparable, "no literals were examined"
    for word in ("全部消えた", "もう消せる手がない"):
        assert not any(word in text for text in comparable), word


def test_the_hammer_is_left_to_its_own_judge() -> None:
    """Two judges over one behaviour is two things to keep in step.

    The hammer is a second route through the same branch, and every board
    this judge sets runs at zero hammers.
    """

    from sidra_ai.evals.puzzle_rules_hold import _PROBE

    assert "hammers = 0" in _PROBE
    assert not any(key.startswith("hammer") for key, _name in RULES)


def test_each_collapse_question_is_asked_on_its_own_board() -> None:
    """Falling down and closing left are two rules, not one.

    Measured the hard way: the first board left a column empty, so the
    sideways rule fired during the test for the downward one and the probe
    read the answer to a question it had not asked - C-1887's two locks in
    one test, again.
    """

    from sidra_ai.evals.puzzle_rules_hold import _PROBE

    assert "out.fell" in _PROBE
    assert "out.closed" in _PROBE
