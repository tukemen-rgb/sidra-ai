"""C-1925: the quarantine not-found error renders without spurious quotes.

EntryNotFoundError subclasses KeyError, whose __str__ wraps the message in
repr, so the CLI printed 「"no quarantine entry matching 'x'"」 with outer
quotes - unlike every other error in the tool. A plain __str__ fixes it while
keeping the KeyError base for `except KeyError` callers.
"""

from __future__ import annotations

import pytest

from sidra_ai.evals.quarantine_not_found_error_reads_cleanly import (
    evaluate_quarantine_not_found_error_reads_cleanly,
)
from sidra_ai.security.quarantine_review import EntryNotFoundError


def test_eval_passes():
    result = evaluate_quarantine_not_found_error_reads_cleanly()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 6


@pytest.mark.parametrize("message", [
    "no quarantine entry matching 'abc123'",
    "'ab' matches 3 entries; use more characters",
])
def test_str_is_the_plain_message(message):
    assert str(EntryNotFoundError(message)) == message


def test_still_a_keyerror():
    # The base is kept so `except KeyError` still catches it.
    with pytest.raises(KeyError):
        raise EntryNotFoundError("x")
