"""An eighteen-second wait must not look like a hang.

Nothing in this repository can make the model faster on the machine that runs
it - the measured breakdown puts nearly all of a question's time in the GPU's
prompt processing (docs/research/perf-competitive-2026-09-08.md). What the
page can do is stop being silent about it: the industry line is that past ten
seconds a wait needs a progress indication, and an unchanging string is not
one.

So this file pins the two halves of that promise. The counter has to exist and
be driven by a clock, and it has to be stopped on **every** way the request
can end - a timer still running after an error would keep painting over the
error message a second later, which is worse than never having shown one.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from sidra_ai.api.ui import ASK_PAGE  # noqa: E402


def test_the_wait_is_counted_not_merely_announced() -> None:
    assert "setInterval(" in ASK_PAGE
    assert "waitingSince" in ASK_PAGE
    # The seconds have to come from the clock, not from a fixed string.
    assert "Date.now() - waitingSince" in ASK_PAGE


def test_the_counter_is_stopped_on_success_error_and_afterwards() -> None:
    """Three exits: the resolved answer, the catch, and the final then."""

    assert ASK_PAGE.count("stopWaiting();") >= 3
    assert "clearInterval(waitingTimer)" in ASK_PAGE


def test_a_long_wait_says_something_more_than_a_shorter_one() -> None:
    """A number alone still reads as stuck; the page names the likely stage."""

    assert re.search(r"seconds\s*>=\s*8", ASK_PAGE)
    assert re.search(r"seconds\s*>=\s*3", ASK_PAGE)


def test_it_stays_a_page_that_fetches_nothing() -> None:
    """The whole point of the entry page: loopback, no third party, no CDN."""

    assert "http://" not in ASK_PAGE
    assert "https://" not in ASK_PAGE


def test_the_waiting_line_is_written_as_text_not_markup() -> None:
    """Same rule as every other line this page writes."""

    assert "statusLine.textContent = waitingText();" in ASK_PAGE
    assert "statusLine.innerHTML" not in ASK_PAGE
