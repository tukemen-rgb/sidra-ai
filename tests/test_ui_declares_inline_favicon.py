"""C-1260: the ask page declares an inline favicon, so no /favicon.ico 404.

Opening the page logged a console 404 for /favicon.ico on every load and the
tab showed a blank icon. The page is self-contained (loopback, no CORS), so it
declares an inline data: favicon; the browser then uses it and never requests
/favicon.ico.
"""

from __future__ import annotations

import re

from sidra_ai.api.ui import ASK_PAGE
from sidra_ai.evals.ui_declares_inline_favicon import (
    evaluate_ui_declares_inline_favicon,
)

_ICON_LINK = re.compile(r"<link\b[^>]*\brel=\"[^\"]*icon[^\"]*\"[^>]*>", re.IGNORECASE)


def test_ui_declares_inline_favicon_eval_passes():
    result = evaluate_ui_declares_inline_favicon()
    assert result.failures == ()
    assert result.checks_passed == result.checks_total == 3


def test_page_has_inline_icon_link():
    link = _ICON_LINK.search(ASK_PAGE)
    assert link is not None
    assert 'href="data:image/svg+xml' in link.group(0)


def test_favicon_is_not_an_external_fetch():
    # The page's whole posture is that it fetches nothing from another host.
    for link in _ICON_LINK.findall(ASK_PAGE):
        assert "http://" not in link
        assert "https://" not in link
        assert 'href="//' not in link
