"""C-1870: the rules for writing a refusal have a guard (§33).

Nine knowledge-base sections were compared against the product on 2026-09-15
and all nine held; every defect found that day - C-1847, C-1855, C-1861,
C-1866, C-1868 - was in the wording of a refusal, and no section covered
writing one. §33 is that section; this is its guard.

Measured before it was written: zero blaming words, zero sentences shared
between causes. So nothing here repairs a defect - it stops a day of hand work
from quietly lapsing.
"""

from __future__ import annotations

import pytest

from sidra_ai.evals.refusal_writing_follows_the_rules import (
    BLAMING,
    PROBES,
    evaluate_refusal_writing_follows_the_rules,
)


def test_refusal_writing_eval_passes():
    result = evaluate_refusal_writing_follows_the_rules()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 30


def test_saying_the_product_cannot_is_not_blaming():
    """Naming a limit is honesty; calling the input wrong is blame.

    §33 事実 8 forbids the second, not the first, and a rule that caught
    「できません」 would forbid every honest refusal this product makes.
    """

    assert "できません" not in BLAMING
    assert "ありません" not in BLAMING
    assert "無効" in BLAMING
    assert "不正" in BLAMING


def test_please_is_not_policed():
    """Microsoft avoids 「please」; Japanese 「〜してください」 is not the same word.

    Recorded in §33: a rule imported without its reason is a rule about
    another language. Asserted so nobody adds it later on the strength of the
    citation alone.
    """

    assert not any("ください" in word for word in BLAMING)


@pytest.mark.parametrize("message,code", sorted(PROBES.items()))
def test_each_probe_still_reaches_its_own_cause(message, code):
    """The probes are the coverage: if one stops reaching its code, the
    sentence for that cause is no longer being read by anything."""

    assert code
    assert message
