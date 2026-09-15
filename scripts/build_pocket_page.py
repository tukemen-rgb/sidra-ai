"""Write the index as one HTML file a phone can open with no server at all.

The product answers from a PC that binds to loopback, so a phone can reach it
only on the same Wi-Fi with a token (LOCAL_RUNTIME.md 6b) - and not at all
while the PC is off or the owner is away. This is the other way round: take
the retrieval half of the product, and carry it.

The page holds the indexed chunks and a line-for-line port of the tokenizer
and BM25 (k1 1.2, b 0.75, the same diversification), so what it ranks is what
the product ranks - checked against the Python retriever on the real corpus
in ``tests/test_pocket_page_ranks_like_the_product.py``. It does not carry the
model, the security gate or the output guard: it finds evidence, it does not
answer.

What goes into the file is exactly what the store holds, and the store holds
only ALLOW-screened chunks - so a page built from a private corpus is private
to whoever holds the file, the same as ``index.jsonl``. Treat it as such.

    python scripts/build_pocket_page.py --out C:\\sidra\\pocket.html
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

TEMPLATE = ROOT / "src" / "sidra_ai" / "api" / "pocket_template.html"
PLACEHOLDER = "/*__CORPUS__*/null"


def render(chunks, *, label: str) -> str:
    """The page with ``chunks`` embedded. ``label`` names the corpus version."""

    rows = [{"p": c.provenance.path, "i": c.index, "t": c.content} for c in chunks]
    payload = json.dumps({"sha": label, "chunks": rows}, ensure_ascii=False)
    template = TEMPLATE.read_text(encoding="utf-8")
    if template.count(PLACEHOLDER) != 1:
        raise RuntimeError("pocket template lost its corpus placeholder")
    # `</script>` inside a chunk would end the script block early; JSON never
    # needs the literal slash, so escaping it is free.
    return template.replace(PLACEHOLDER, payload.replace("</", "<\\/"))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, help="where to write the HTML file")
    args = parser.parse_args()

    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import get_settings

    settings = get_settings()
    service = SidraService(settings=settings)
    chunks = list(service.retriever.store.chunks())
    if not chunks:
        print("NG  索引が空です。先に取り込み（POST /v1/github/analyze）を走らせてください")
        return 1
    shas = {c.provenance.commit_sha[:7] for c in chunks}
    label = next(iter(shas)) if len(shas) == 1 else f"{len(shas)} commits"
    out = Path(args.out)
    out.write_text(render(chunks, label=label), encoding="utf-8")
    documents = len({(c.provenance.repository, c.provenance.path) for c in chunks})
    print(f"OK  {out}  {documents} 文書 / {len(chunks)} 断片 / {out.stat().st_size / 1e6:.2f} MB")
    print("    このファイルは索引の中身そのものです。index.jsonl と同じ扱いで。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
