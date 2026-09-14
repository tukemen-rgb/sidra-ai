"""Is there a record of an artifact made on its own, or only of a production?

C-1830. ``creation.records`` says it exists so that 「この game.html はいつ・何
から作られたか」 has an answer a week later. ``append_record`` was called from
exactly one place - the whole-production scaffold - so the ordinary request,
the common path through six generators, left nothing behind but the file.

Measured through the real API: 「猫のゲーム」「犬のゲーム」「忍者のゲーム」 list as
``game-fishing-….html``, ``…-2.html`` and ``…-3.html``. The listing is right to
carry no preview of its own (a deck's body is retrieved content, and a preview
in a listing puts that where it reads as metadata); what was missing is the
record beside it.

The record carries file name, time, title, source labels and parameters. Not
the text those labels pointed at - the module's own rule - and not the request
itself, which ``app.py`` decided the audit log never holds.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sidra_ai.api.service import SidraService
from sidra_ai.config.settings import Settings
from sidra_ai.creation.evidence import Fact
from sidra_ai.creation.records import (
    STANDALONE_LOG_NAME,
    format_record,
    read_records,
)
from sidra_ai.evals.scratch import scratch_dir
from sidra_ai.ingestion.state import StateStore


@dataclass(frozen=True)
class StandaloneRecordResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _service(data_dir: Path) -> SidraService:
    return SidraService(
        Settings(data_dir=str(data_dir), model_backend="echo"),
        state_store=StateStore(data_dir / "state.json"),
    )


def _log_text(root: Path) -> str:
    """The log, or "" when there is none.

    A missing log is what this eval is about, so reading one has to score a
    check rather than raise: an eval that crashes reports a broken section,
    not a low number, and the number is what the judge compares.
    """

    path = root / STANDALONE_LOG_NAME
    return path.read_text(encoding="utf-8") if path.is_file() else ""


def evaluate_standalone_artifact_has_a_record() -> StandaloneRecordResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    root = Path(scratch_dir("sidra-c1830-"))
    service = _service(root)
    for request in (
        "猫のゲームを作って",
        "犬のゲームを作って",
        "忍者のゲームを作って",
        "海のアートを作って",
        "魚のGIFを作って",
        "収益化のレポートを作って",
        "立方体の3Dモデルを作って",
        "新商品のスライドを作って",
    ):
        service.chat(request)
    before_greeting = len(read_records(root, log_name=STANDALONE_LOG_NAME))
    service.chat("こんにちは")
    records = read_records(root, log_name=STANDALONE_LOG_NAME)

    # --- (A) three games made from three subjects are told apart ----------
    subjects = {
        record.parameters.get("題")
        for record in records
        if record.parameters.get("kind") == "game"
    }
    add({"猫", "犬", "忍者"} <= subjects,
        f"A: the record does not say which game is which: {sorted(subjects)}")
    # --- (B) and every kind that writes a file gets one -------------------
    kinds = {record.parameters.get("kind") for record in records}
    missing = {"game", "art", "gif", "document", "model3d", "deck"} - kinds
    add(not missing, f"B: these kinds write a file and no record: {sorted(missing)}")
    # --- (C) a route that builds nothing writes no record -----------------
    #     The first version of this check sent a greeting, which never reaches
    #     the router at all - so it could not fail whatever the router did,
    #     and a destruction that recorded every route scored a perfect 8/8.
    #     This drives the router directly, with a kind nothing is registered
    #     for: handled is False and no artifact exists to record.
    from sidra_ai.creation.intent import CreationIntent, CreationKind
    from sidra_ai.creation.router import CreationOutcome, CreationRouter

    #     A router with nothing registered returns before the recorder runs,
    #     so it proves nothing either. These two stubs are the shapes that do
    #     reach it: a generator that declined, and one that made no file (the
    #     deck that fails validation and is discarded).
    def _declined(message, intent, facts=None):
        return CreationOutcome(kind=intent.kind, handled=False, summary="なし")

    def _no_file(message, intent, facts=None):
        return CreationOutcome(kind=intent.kind, handled=True, summary="破棄しました")

    quiet_root = Path(scratch_dir("sidra-c1830-quiet-"))
    intent = CreationIntent(is_creation=True, kind=CreationKind.GAME)
    for stub in (_declined, _no_file):
        router = CreationRouter(record_dir=quiet_root)
        router.register(CreationKind.GAME, stub)
        router.route("猫のゲームを作って", intent)
    add(not (quiet_root / STANDALONE_LOG_NAME).exists()
        and len(records) == before_greeting,
        "C: a route that made no file still wrote a record")
    # --- (D) the file named in the record is the file on disk -------------
    made = {name for record in records for name in record.made}
    on_disk = {path.name for path in (root / "artifacts").iterdir() if path.is_file()}
    add(made and made <= on_disk,
        f"D: the record names a file that is not there: {sorted(made - on_disk)}")
    # --- (E) the log is outside artifacts/, so the listing total is not
    #         changed by the act of recording ----------------------------
    add((root / STANDALONE_LOG_NAME).is_file()
        and not (root / "artifacts" / STANDALONE_LOG_NAME).exists(),
        "E: the log is not beside the artifacts, where it would be listed as one")

    # --- (F) no retrieved text reaches the record -------------------------
    #     Source labels are carried; the sentences they point at are not.
    secret = "四半期の解約率は 12.5% だった"
    facts = [Fact(text=secret, source="owner/alpha:docs/plan.md")]
    from sidra_ai.creation.intent import detect_creation_intent

    deck_request = "収益化のスライドを作って"
    outcome = service.creation_router.route(
        deck_request, detect_creation_intent(deck_request), facts
    )
    log_text = _log_text(root)
    add(outcome.handled and secret not in log_text
        and "owner/alpha:docs/plan.md" in log_text,
        "F: the record quotes retrieved text, or lost the source label")

    # --- (G) the production log still parses with the same reader ---------
    from sidra_ai.creation.projects import scaffold_project

    project = scaffold_project("犬のゲームを企画から作って", root / "proj")
    add(len(read_records(project.root)) == 1,
        "G: the whole-production record changed shape")

    # --- (H) a parameter value with a space survives the read-back --------
    #     It never did: the reader split on every space, so an English title
    #     dropped everything after its first word - silently, and only on
    #     read-back, because the line a person reads was always complete.
    line = format_record(
        made=["game-fishing.html"],
        evidence=[],
        parameters={"題": "cat game", "template": "fishing"},
        now=datetime(2026, 9, 14, tzinfo=timezone.utc),
    )
    scratch = Path(scratch_dir("sidra-c1830-read-"))
    # mkdir first: the log name is a relative path, and a check that crashes
    # while setting itself up reports a broken section instead of a number.
    (scratch / STANDALONE_LOG_NAME).parent.mkdir(parents=True, exist_ok=True)
    (scratch / STANDALONE_LOG_NAME).write_text(
        f"## 生成履歴\n\n{line}\n", encoding="utf-8"
    )
    read_back = read_records(scratch, log_name=STANDALONE_LOG_NAME)
    add(bool(read_back)
        and read_back[0].parameters.get("題") == "cat game"
        and read_back[0].parameters.get("template") == "fishing",
        "H: a parameter value with a space is still truncated on read-back")

    return StandaloneRecordResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
    )


__all__ = [
    "StandaloneRecordResult",
    "evaluate_standalone_artifact_has_a_record",
]
