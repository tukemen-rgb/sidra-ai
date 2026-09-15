"""Told which field to change, does the product say what that field takes?

C-1868. Naming a field without a value - 「さっきのゲームの配色を変えて」 - matched
no value table, so the adjustment came out empty and the reply was:

    「どれを変えるかは分かりましたが、何をどう変えるかが読み取れませんでした。
     いま変えられるのは 難易度・テーマ（配色）・…」

The refusal listed the field it was refusing. Measured across five fields, five
times out of five. This is C-1802's family - a refusal whose advice does not
work - in its shortest form: the answer was printed in the same sentence as the
refusal, and the reader had to notice that 配色 appearing in a list of what CAN
be changed contradicted the clause before it.

The branch's own note had already seen half of it: 「題名 IS in the list; what
was missing was the value」, and it chose wording true of both an unsupported
field and a supported one with no value. That is honest and one step short -
the detector knows WHICH field was named, so it can say what that field takes.

Values are read off the owning tables (``THEMES``, ``_ACCENT_WORDS``, the
template's difficulty ladder), so a colour or a theme added upstream joins the
sentence by existing.

The check that matters is (C): the advice is RUN. A sentence naming values the
product then refuses would be the same defect wearing a better coat.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.creation.revise import CHANGEABLE, field_values, names_a_field
from sidra_ai.creation.themes import THEMES
from sidra_ai.evals.scratch import scratch_dir
from sidra_ai.ingestion.state import StateStore

#: The field named, and a request that names it with no value.
FIELD_REQUESTS: dict[str, str] = {
    "theme": "さっきのゲームの配色を変えて",
    "accent": "さっきのゲームの差し色を変えて",
    "difficulty": "さっきのゲームの難易度を変えて",
    "title": "さっきのゲームのタイトルを変えて",
}

#: Said in the advice, and then actually sent. If the advice works, each of
#: these is a real revision rather than another refusal.
ADVICE_WORKS: tuple[str, ...] = (
    "さっきのゲームを紙のテーマにして",
    "さっきのゲームの差し色を青にして",
    "さっきのゲームを難しくして",
    "さっきのゲームのタイトルを「新しい名前」にして",
)

#: No field named: the general list is still the right answer.
NO_FIELD: tuple[str, ...] = (
    "さっきのゲームをいい感じにして",
    "さっきのゲームの音を消して",
)


@dataclass(frozen=True)
class FieldValuesResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def evaluate_revision_names_the_values_of_the_field() -> FieldValuesResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    root = Path(scratch_dir("c1868-"))
    service = SidraService(
        Settings(data_dir=str(root), model_backend="echo"),
        state_store=StateStore(root / "state.json"),
    )
    service.chat("迷宮を冒険するゲームを作って")
    labels = dict(CHANGEABLE)

    # --- (A) the field is named as changeable, not listed among others ----
    answers = {key: service.chat(req).get("answer") or ""
               for key, req in FIELD_REQUESTS.items()}
    for key, answer in answers.items():
        add(f"{labels[key]}は変えられます" in answer,
            f"A: {key}: the answer does not say the field can be changed: {answer[:70]}")
        add("いま変えられるのは" not in answer,
            f"A: {key}: still handed the list its own field is in")
        # ...and C-1802's guarantee survives: a refusal still names what CAN
        # be changed. Its sentinel caught the first version of this, which
        # answered the named field and dropped the list - so the case lives
        # here too now, not only in the item that caught it.
        add("ほかに変えられるのは" in answer,
            f"A: {key}: the rest of what can be changed is no longer named")
        add(labels[key] not in answer.split("ほかに変えられるのは", 1)[-1],
            f"A: {key}: the field they asked about is repeated in the rest")

    # --- (B) and it says what that field takes, from the owning table -----
    add(all(name in answers["theme"] for name in THEMES),
        f"B: the themes are not the catalogue's: {answers['theme'][:80]}")
    add("赤" in answers["accent"] and "白" in answers["accent"],
        f"B: the accents are not the colour table's: {answers['accent'][:80]}")
    add("easy" in answers["difficulty"] and "hard" in answers["difficulty"],
        f"B: the rungs are not the ladder's: {answers['difficulty'][:80]}")

    # --- (C) the advice WORKS ---------------------------------------------
    #     Run, not read. Advice that names values the product then refuses
    #     is this defect in better clothes.
    for request in ADVICE_WORKS:
        result = service.chat(request)
        add(result.get("refused") is False,
            f"C: the advised phrasing was refused: {request!r} -> "
            f"{(result.get('answer') or '')[:60]}")

    # --- (D) a request naming no field keeps the general list -------------
    for request in NO_FIELD:
        answer = service.chat(request).get("answer") or ""
        add("いま変えられるのは" in answer,
            f"D: {request!r} lost the list of what can be changed")

    # --- (E) the two tables cannot drift ----------------------------------
    #     Every field this knows how to describe must be one the product
    #     offers, or the sentence promises something nobody can set.
    unknown = [key for key in FIELD_REQUESTS if key not in labels]
    add(not unknown, f"E: described fields the product does not offer: {unknown}")
    add(all(field_values(key, "adventure") for key in FIELD_REQUESTS),
        "E: a described field has nothing to say about its values")
    add(names_a_field("さっきのゲームをいい感じにして") == "",
        "E: a request naming no field was read as naming one")

    return FieldValuesResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
    )
