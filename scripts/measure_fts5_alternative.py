"""Would sqlite + FTS5 rank this corpus as well as the hand-written BM25? (C-1464)

The board carried "sqlite + FTS5" from the beginning on the reasoning that
the in-memory index has a ceiling. C-1133 measured the ceiling; this
measures the replacement, on the only question that decides it: does the
corpus still answer as well?

The comparison is deliberately generous to FTS5. It is fed the project's
OWN tokens - ``" ".join(tokenize(chunk))`` indexed with a whitespace-ish
tokenizer - so every measured decision in ``search.tokenize`` (CJK bigrams,
the kana-only rule, the interrogative rule, the stopwords) survives the
swap. What cannot survive is the scoring: SQLite's ``bm25()`` is fixed at
k1=1.2 and this corpus was tuned to **k1=1.5**, and its statistics are
whole-table where the current retriever scopes them to the filter.

    python scripts/measure_fts5_alternative.py <repo=path ...>

Exit 0 always: a measurement, not a gate.
"""

import sys, contextlib, io, sqlite3, time
sys.path.insert(0,'src'); sys.path.insert(0,'scripts')
import measure_outcomes as mo
from pathlib import Path
from sidra_ai.retrieval.search import BM25Retriever, SearchResult, tokenize
from sidra_ai.retrieval.store import DocumentStore
from sidra_ai.security.gate import GatePolicy, SecurityGate

class Fts5Retriever:
    def __init__(self, store):
        self._store = store
        self.store = store
        self._db = sqlite3.connect(":memory:")
        self._db.execute(
            "CREATE VIRTUAL TABLE chunks USING fts5(body, tokenize='unicode61 remove_diacritics 0')"
        )
        self._chunks = []
        rows = []
        for chunk in store.chunks():
            self._chunks.append(chunk)
            rows.append((" ".join(tokenize(chunk.content)),))
        self._db.executemany("INSERT INTO chunks(body) VALUES (?)", rows)

    def search(self, query, *, top_k=5, repositories=None, source_types=None, min_score=0.0):
        terms = [t for t in dict.fromkeys(tokenize(query))]
        if not terms:
            return []
        match = " OR ".join('"' + t.replace('"', '') + '"' for t in terms)
        try:
            cur = self._db.execute(
                "SELECT rowid, bm25(chunks) FROM chunks WHERE chunks MATCH ? "
                "ORDER BY bm25(chunks) LIMIT ?", (match, top_k * 20))
            hits = cur.fetchall()
        except sqlite3.OperationalError:
            return []
        repo_filter = None if repositories is None else {r.lower() for r in repositories}
        type_filter = None if source_types is None else set(source_types)
        out, per_doc = [], {}
        for rowid, score in hits:
            chunk = self._chunks[rowid - 1]
            p = chunk.provenance
            if repo_filter is not None and p.repository.lower() not in repo_filter: continue
            if type_filter is not None and p.source_type not in type_filter: continue
            key = chunk.document_id
            if per_doc.get(key, 0) >= 2: continue
            per_doc[key] = per_doc.get(key, 0) + 1
            out.append(SearchResult(chunk=chunk, score=-score))
            if len(out) >= top_k: break
        return out

targets, missing = mo.parse_targets(sys.argv[1:])
if missing is None or not targets:
    print(__doc__, file=sys.stderr)
    raise SystemExit(2)
gate=SecurityGate(GatePolicy(),allowed_repositories=[n for n,_ in targets]); store=DocumentStore(gate)
with contextlib.redirect_stdout(io.StringIO()): mo.ingest(targets,store,gate)
for name, make in (("BM25 (現行)", BM25Retriever), ("FTS5", Fts5Retriever)):
    r = make(store)
    t=time.time(); r.search("北極星指標", top_k=5); build=time.time()-t
    with contextlib.redirect_stdout(io.StringIO()):
        out = mo.measure_answerable(r, targets)
    scored = out["scored"] or 1
    disc = 100*out["answered"]/scored - 100*out["control_hits"]/scored
    t=time.time()
    for q in [q.question for q in __import__("sidra_ai.evals.outcome_questions", fromlist=["x"]).OUTCOME_QUESTIONS][:20]:
        r.search(q, top_k=5)
    per=1000*(time.time()-t)/20
    print(f"{name:12s} answered {out['answered']}/{scored}  control {out['control_hits']}  "
          f"弁別 {disc:+.1f}pt  MRR {out.get('mrr',0):.3f}  初回 {build:.2f}s  検索 {per:.1f}ms")
