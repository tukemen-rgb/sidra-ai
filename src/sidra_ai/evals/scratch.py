"""One place a judge gets a scratch directory, and one place it goes away.

C-1770. Ninety-two call sites across seventy-nine eval modules reached for
``tempfile.mkdtemp()`` and none of them removed what they made. A judge
makes several of these per run and five loops run the collector all day,
so a week of measuring left ``/tmp`` holding 30G: ``qa-honesty-*`` alone
had 10,697 directories, the oldest dated 09-05.

That is not untidiness. When the disk fills, the collector dies partway
and ``--compare`` reports the metrics it never reached as REGRESSED and
LOST - which happened, and was read as a product failure before the real
cause was found (C-1759's third self-report: 297 REGRESSED, 296 LOST, all
of it a full disk). The apparatus was corrupting its own measurements.

Cleanup is at interpreter exit rather than at each judge's last line. A
judge reads the directory it made right up to the end of its own
function, and threading a context manager through ninety-two of them
would be a rewrite, not a repair. What had to stop is the pile that grows
*between* runs, and exiting is when that pile is made.
"""

from __future__ import annotations

import atexit
import shutil
import tempfile

#: Every directory this process handed out, in the order it did.
_MADE: list[str] = []


def scratch_dir(prefix: str = "") -> str:
    """A temporary directory that this process will remove when it exits."""

    path = tempfile.mkdtemp(prefix=prefix or "sidra-eval-")
    _MADE.append(path)
    return path


def scratch_made() -> tuple[str, ...]:
    """What has been handed out and not yet swept - for tests to read."""

    return tuple(_MADE)


@atexit.register
def sweep_scratch() -> int:
    """Remove everything handed out. Returns how many were swept.

    Never raises: a judge that has already reported its result must not
    be turned into a failure by a directory somebody else removed first,
    and this runs during interpreter shutdown where an exception is
    printed and ignored anyway.
    """

    swept = 0
    while _MADE:
        shutil.rmtree(_MADE.pop(), ignore_errors=True)
        swept += 1
    return swept


__all__ = ["scratch_dir", "scratch_made", "sweep_scratch"]
