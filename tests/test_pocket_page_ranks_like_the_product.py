"""The pocket page must rank exactly what the product ranks, or it misleads.

``scripts/build_pocket_page.py`` carries the retrieval half of the product as
one HTML file a phone can open offline. Its value is that a question typed
there returns the evidence the product would return; a port that ranked even
slightly differently would show the owner a product that does not exist.

So the JavaScript is not tested by reading it. The page's script is run in
node against the Python retriever over the same chunks, and the two orders
and scores have to agree - on a fixture here, and (in the container that has
them) on the real corpus, where the port was first checked on 2026-09-15:
five reference questions, identical chunks, scores equal to four decimals.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import build_pocket_page  # noqa: E402
from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel  # noqa: E402
from sidra_ai.retrieval.search import BM25Retriever  # noqa: E402
from sidra_ai.retrieval.store import DocumentStore  # noqa: E402
from sidra_ai.security.gate import GatePolicy, SecurityGate  # noqa: E402

_REPO = "owner/alpha"

_DOCS = {
    "docs/security.md": (
        "## セキュリティ方針\n\nSIDRA は外部の API にリポジトリの内容を送らない。"
        "プロンプト注入は指示ではなくデータとして扱う。秘密と個人情報は索引に入らない。\n" * 3
    ),
    "docs/runtime.md": (
        "## ローカルで動かす手順\n\n専用の仮想環境を作り、echo で全部通してから模型を足す。"
        "VRAM を測ってから模型を選ぶ。待ち受けは loopback のまま。\n" * 3
    ),
    "docs/revenue.md": (
        "## 収益化の方針\n\n掲載順は売らない。投稿は無料。制作者が自分の作品で稼ぐ手段として"
        "アフィリエイトを検討する。\n" * 3
    ),
    "docs/story.md": "## 制作記録\n\n記録は本人が編集・削除できる。閲覧者への広告掲示はしない。\n" * 4,
}

_ASKS = ["セキュリティ方針は", "ローカルで動かす手順", "制作者が稼ぐ手段", "広告は出ますか", "存在しない話題"]


def _store() -> DocumentStore:
    gate = SecurityGate(GatePolicy(), allowed_repositories=[_REPO])
    store = DocumentStore(gate)
    for path, content in _DOCS.items():
        store.add(
            Document(
                content=content,
                provenance=Provenance(
                    source="github",
                    repository=_REPO,
                    path=path,
                    commit_sha="0" * 40,
                    timestamp=datetime(2026, 9, 15, tzinfo=timezone.utc),
                    source_type=SourceType.DOCS,
                    trust_level=TrustLevel.INTERNAL_REPO,
                    license="proprietary",
                ),
            )
        )
    return store


def _page_rankings(html: str, asks: list[str]) -> dict:
    """Run the page's own script in node and return what it would show."""

    script = html[html.index("<script>") + 8 : html.rindex("</script>")]
    # The page wires itself to a DOM on load; give it a stand-in and skip the
    # initial render so only the ranking function is exercised.
    script = script.replace(
        "const $ = id => document.getElementById(id);",
        'const $ = id => ({ set innerHTML(v) {}, value: "", addEventListener() {} });',
    ).replace("run(initial);", "")
    harness = script + (
        "\nconst ASKS = %s;\nconst out = {};\n"
        "for (const q of ASKS) out[q] = search(q).picked.map(r => [chunks[r.i].p, chunks[r.i].i, +r.s.toFixed(4)]);\n"
        "console.log(JSON.stringify(out));\n" % json.dumps(asks, ensure_ascii=False)
    )
    handle = tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8")
    try:
        handle.write(harness)
        handle.close()
        done = subprocess.run(["node", handle.name], capture_output=True, text=True, timeout=120)
    finally:
        Path(handle.name).unlink()
    assert done.returncode == 0, done.stderr[:500]
    return json.loads(done.stdout.strip().splitlines()[-1])


def test_the_template_still_has_somewhere_to_put_the_corpus() -> None:
    assert build_pocket_page.TEMPLATE.read_text(encoding="utf-8").count(
        build_pocket_page.PLACEHOLDER
    ) == 1


def test_a_closing_script_tag_inside_a_chunk_cannot_end_the_page_script() -> None:
    """Documents quote HTML. One `</script>` in a chunk would truncate the page."""

    store = _store()
    hostile = Document(
        content="説明の途中に </script><script>alert(1)</script> が現れる文書。" * 4,
        provenance=Provenance(
            source="github", repository=_REPO, path="docs/quoted.md", commit_sha="0" * 40,
            timestamp=datetime(2026, 9, 15, tzinfo=timezone.utc), source_type=SourceType.DOCS,
            trust_level=TrustLevel.INTERNAL_REPO, license="proprietary",
        ),
    )
    store.add(hostile)
    html = build_pocket_page.render(list(store.chunks()), label="test")
    body = html[html.index("<script>") + 8 :]
    assert body.count("</script>") == 1, "a chunk's </script> ended the page's script"


def test_the_page_ranks_exactly_what_the_python_retriever_ranks() -> None:
    if shutil.which("node") is None:  # pragma: no cover - environment guard
        pytest.skip("node is required to run the page's script")

    store = _store()
    chunks = list(store.chunks())
    html = build_pocket_page.render(chunks, label="test")
    retriever = BM25Retriever(store)

    got = _page_rankings(html, _ASKS)

    for ask in _ASKS:
        want = [
            [r.chunk.provenance.path, r.chunk.index, round(r.score, 4)]
            for r in retriever.search(ask, top_k=5)
        ]
        assert [g[:2] for g in got[ask]] == [w[:2] for w in want], (
            f"{ask!r}: page {got[ask]} / product {want}"
        )
        for g, w in zip(got[ask], want):
            assert abs(g[2] - w[2]) < 1e-3, f"{ask!r}: score {g[2]} vs {w[2]}"
    assert got["存在しない話題"] == [], "a question with no evidence must return nothing, as the product does"
