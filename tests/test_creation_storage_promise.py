"""残ると言い切らない (§31, C-1741).

The knowledge base gained §31 this cycle because the loop needed it twice
and did not have it. Its two facts, read at the sources on 2026-09-12:

* Storage is **best-effort** by default. An origin's data lasts "as long
  as the origin is below its quota and the device has room" - a browser
  may drop it. (MDN, *Storage quotas and eviction criteria*)
* **Safari deletes it after seven days.** With cross-site tracking
  prevention on, an origin whose site has had no interaction in the last
  seven days of browser use loses everything a script wrote -
  localStorage included. (MDN and web.dev, *Storage for the web*)

That is the same seven days §8 事実 4 builds D7 retention on. On iOS the
personal best and the ghost may be gone at exactly the moment the product
is counting on them to bring somebody back. The eviction is not this
loop's to fix. Telling the player their record is kept is.

Both panels said 「この端末だけに保存されます」. They now read one shared
sentence, because a promise written in two files is a promise that drifts.

Both directions: the caveat is present *and* the assertion is gone - a
page that prints both sentences is not honest, it is merely longer.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.games import TEMPLATES, generate_game
from sidra_ai.creation.together import STORAGE_NOTE, STORAGE_OVERCLAIM


def test_the_shared_sentence_does_not_assert_what_it_cannot() -> None:
    assert "保存されます" not in STORAGE_NOTE, STORAGE_NOTE
    assert "消す" in STORAGE_NOTE or "消える" in STORAGE_NOTE, STORAGE_NOTE
    assert STORAGE_OVERCLAIM not in STORAGE_NOTE


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_both_panels_say_it_can_be_cleared(template: str) -> None:
    """Two panels name a storage location: 調整 and キー設定.

    Read off the panels the page actually builds (C-1965). Counting the
    sentence in the HTML worked while each panel carried its own copy of
    it; both now read the one row in ``CANVAS_WORDS``, so the literal
    appears once however many panels say it. What has to be true is not
    "the string is in the file twice" but "two panels say it", and that is
    what this now asks.
    """

    import json
    import re
    import shutil
    import subprocess

    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is unavailable")

    from sidra_ai.creation.paneltext import panel_probe

    page = generate_game("ゲームを作って", template=template).html
    script = re.search(r"<script>(.*?)</script>", page, re.S).group(1)
    run = subprocess.run(
        ["node", "-"], input=panel_probe(script),
        capture_output=True, text=True, timeout=600,
    )
    assert run.returncode == 0, run.stderr[-400:]
    said = [t for t in json.loads(run.stdout.strip().splitlines()[-1])["texts"]
            if STORAGE_NOTE in t]
    assert len(said) >= 2, said


@pytest.mark.parametrize("template", sorted(TEMPLATES))
def test_the_old_assertion_is_gone(template: str) -> None:
    """Without this, adding a caveat beside the claim scores full marks."""

    page = generate_game("ゲームを作って", template=template).html
    assert STORAGE_OVERCLAIM not in page


def test_the_sentence_lives_in_one_place() -> None:
    """C-1342: the two panels must not carry their own copies."""

    import pathlib

    root = pathlib.Path(__file__).resolve().parents[1] / "src" / "sidra_ai" / "creation"
    written = [
        path.name
        for path in root.glob("*.py")
        if STORAGE_NOTE in path.read_text(encoding="utf-8")
    ]
    assert written == ["together.py"], written
