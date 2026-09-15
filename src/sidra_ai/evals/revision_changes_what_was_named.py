"""Told to increase one thing, does the product increase that thing?

C-1853. The revision vocabulary has a second axis - what the tuning panel
calls 「敵の数」 on an adventure, 「足場の数」 on a platformer, 「盤の幅」 on a
puzzle - and the words that move it (増やして/減らして/多く/少なく/広く/狭く)
fired on the verb alone. Nothing asked what was being increased, so on a real
adventure:

* 「さっきのゲームの宝石をもっと増やして」 → 「修正しました: 敵の数 4」
* 「さっきのゲームの宝石を減らして」 → 「修正しました: 敵の数 3」

A new version of the page was written each time. That is worse than declining:
the product performed an edit nobody asked for and reported it as the edit that
was asked for. 「部屋を増やして」 and 「ハートを増やして」 answered 「変更なし
（すでにその設定です）」 - no harm, but a false reason, since the word had never
been read at all.

The comment above the band table already said what was missing: what the axis
means differs per template, and only the panel's label knows which. So the fix
reads ``AXIS_LABELS`` instead of adding a table, and the judging happens in the
reviser, the one place that knows which template the target is.

What this measures, in both directions:

* a named thing that is not the axis moves nothing, and writes no file;
* the axis's own word still works - per template, read from ``band_owner`` so
  this eval cannot pass by agreeing with a hard-coded 「敵」;
* naming nothing (「もっと増やして」) still moves the axis, because that is a
  request for the axis itself;
* naming the artifact (「ゲームをもっと増やして」) is naming nothing;
* difficulty, theme and accent are untouched;
* and a message that asks for both gets told about both.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.creation.revise import band_owner
from sidra_ai.creation.tuning import AXIS_LABELS
from sidra_ai.evals.scratch import scratch_dir
from sidra_ai.ingestion.state import StateStore

#: Things an adventure has that its band axis is not an amount of. Each is a
#: real feature of the page (gems, rooms, hearts) so none of them is a nonsense
#: word the parser could dismiss for another reason.
NOT_THE_AXIS: tuple[str, ...] = ("宝石", "部屋", "ハート")

#: One request per template, and the template's own axis word comes from
#: band_owner rather than from here.
TEMPLATE_REQUESTS: tuple[tuple[str, str], ...] = (
    ("adventure", "迷宮を冒険するゲームを作って"),
    ("platformer", "ジャンプで進むゲームを作って"),
    ("puzzle", "パズルゲームを作って"),
)

_REFUSED = "増減できません"


@dataclass(frozen=True)
class RevisionNamedResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _service(prefix: str) -> tuple[SidraService, Path]:
    root = Path(scratch_dir(prefix))
    service = SidraService(
        Settings(data_dir=str(root), model_backend="echo"),
        state_store=StateStore(root / "state.json"),
    )
    return service, root


def _files(root: Path) -> int:
    return len(list((root / "artifacts").iterdir()))


def evaluate_revision_changes_what_was_named() -> RevisionNamedResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    service, root = _service("c1853-adventure-")
    service.chat("迷宮を冒険するゲームを作って")
    before = _files(root)

    # --- (A) a thing that is not the axis moves nothing -------------------
    answers = {
        word: service.chat(f"さっきのゲームの{word}をもっと増やして").get("answer") or ""
        for word in NOT_THE_AXIS
    }
    moved = {w: a for w, a in answers.items() if "敵の数" in a and _REFUSED not in a}
    add(not moved, f"A: the enemy count moved for: {sorted(moved)}")

    # --- (B) and no version was written ----------------------------------
    #     The check that matters: an apology that still edits the page is
    #     the outcome this item exists to prevent.
    add(_files(root) == before,
        f"B: files were written: {before} -> {_files(root)}")

    # --- (C) the sentence names what they asked for, and the real axis ----
    for word, answer in answers.items():
        add(f"「{word}」" in answer and _REFUSED in answer,
            f"C: {word!r} is not named as the thing that cannot change: {answer[:80]}")
    add(all(band_owner("adventure") in answer for answer in answers.values()),
        "C: the answer does not name the axis this template does have")

    # --- (D) 「減らして」 is the same rule, not a different path ------------
    down = service.chat("さっきのゲームの宝石を減らして").get("answer") or ""
    add(_REFUSED in down, f"D: reducing took another route: {down[:80]}")

    # --- (E) the axis's own word still works, per template ----------------
    #     band_owner, not a literal: an eval that wrote 「敵」 here would pass
    #     a product whose labels had drifted from what it actually tunes.
    for template, request in TEMPLATE_REQUESTS:
        svc, home = _service(f"c1853-{template}-")
        svc.chat(request)
        owner = band_owner(template)
        label = AXIS_LABELS[template][1]
        got = svc.chat(f"さっきのゲームの{owner}を増やして").get("answer") or ""
        add(label in got and _REFUSED not in got,
            f"E: {template}: 「{owner}を増やして」 did not move {label}: {got[:80]}")
        # ...and the same wrong word is refused there too, naming that
        # template's own axis rather than the adventure's.
        wrong = svc.chat("さっきのゲームの宝石を増やして").get("answer") or ""
        add(_REFUSED in wrong and owner in wrong,
            f"E: {template}: the gems were not refused with its own axis: {wrong[:80]}")

    # --- (E2) the word a PERSON types works, not only the one the code
    #     derives. E above builds its request out of band_owner, so it agrees
    #     with whatever band_owner returns - a sabotage that made the owner
    #     the whole label 「敵の数」 scored full marks, because the eval then
    #     asked for 「敵の数を増やして」 and nobody types that. 「敵」 is written
    #     out here deliberately: it is the operator's vocabulary, not the
    #     product's table, and it is the side the derivation exists to serve.
    svc_h, _ = _service("c1853-human-")
    svc_h.chat("迷宮を冒険するゲームを作って")
    human = svc_h.chat("さっきのゲームの敵を増やして").get("answer") or ""
    add(_REFUSED not in human and "敵の数" in human,
        f"E2: the plain word a person types did not move the axis: {human[:90]}")

    # --- (F) naming nothing still moves the axis --------------------------
    svc, home = _service("c1853-bare-")
    svc.chat("迷宮を冒険するゲームを作って")
    bare = svc.chat("さっきのゲームをもっと増やして").get("answer") or ""
    add(_REFUSED not in bare, f"F: a bare request was refused: {bare[:80]}")

    # --- (G) the other axes are untouched ---------------------------------
    harder = svc.chat("さっきのゲームを難しくして").get("answer") or ""
    add("難易度" in harder and _REFUSED not in harder,
        f"G: difficulty stopped working: {harder[:80]}")
    accent = svc.chat("さっきのゲームの色を青にして").get("answer") or ""
    add("差し色" in accent, f"G: the accent stopped working: {accent[:80]}")

    # --- (H) both halves of a mixed request are reported ------------------
    svc2, _ = _service("c1853-mixed-")
    svc2.chat("迷宮を冒険するゲームを作って")
    mixed = svc2.chat("さっきのゲームの宝石を増やして、あと難しくして").get("answer") or ""
    add("難易度" in mixed and "「宝石」" in mixed,
        f"H: the mixed request reported only one half: {mixed[:100]}")

    # --- (H2) naming the AXIS rather than what it counts still moves it ---
    #     「帯」 is this product's own generic word for the row, and the only
    #     one that works on all ten templates. C-1710's sentinel is written
    #     with it for that reason, and it is what went red when the first
    #     version of this rule read 「帯」 as a thing the board is not.
    svc_b, _ = _service("c1853-band-")
    svc_b.chat("パズルゲームを作って")
    generic = svc_b.chat("そのゲームの帯を広くして").get("answer") or ""
    add(_REFUSED not in generic and AXIS_LABELS["puzzle"][1] in generic,
        f"H2: the axis's own name was refused: {generic[:90]}")

    # --- (I) every template has an axis owner to name ---------------------
    #     Read from AXIS_LABELS: a template added without a label would
    #     otherwise refuse every request while naming nothing.
    ownerless = [t for t in AXIS_LABELS if not band_owner(t)]
    add(not ownerless, f"I: templates whose axis has no name: {ownerless}")

    return RevisionNamedResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
    )
