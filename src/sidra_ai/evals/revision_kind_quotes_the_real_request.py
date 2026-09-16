"""When told to send the request again, is it *their* request being quoted?

C-1876. Revision is game-only, so 「さっきのレポートを直して」 is answered with
「同じ内容で作り直すには、作ったときの依頼をもう一度送ってください」 - correct
advice - beside a generic example, 「レポートを作って」. Following the example
literally does not do what the sentence promises: measured, 「犬のレポートを
作って」 then the example produced a *second* report with no dog in it. The
instruction was right and the example contradicted it.

Their own words are the only source. Documents and decks write no
``.meta.json`` - measured: after making a report the directory holds the
``.md`` and nothing beside it - so the sidecar route games use does not exist
here, and the conversation is all there is.

Four checks, and the last two are the ones worth having:

* **A** the reply quotes the request that was actually sent;
* **B** it no longer offers the generic stand-in as the thing to send;
* **C** with no such request in view it prints **no** example rather than an
  invented one - a fabricated quote is worse than the generic one it replaced;
* **D** the quote is a real turn from the conversation, not a sentence built
  to look like one.
"""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

_REPO = "tukemen-rgb/sidra-ai"

#: The stand-in the reply used to print. Its absence is the fix; its presence
#: beside 「もう一度送ってください」 is the defect.
_GENERIC = "「レポートを作って」"


@dataclass(frozen=True)
class QuotesRealRequestResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _service(home: str):
    from sidra_ai.api.service import SidraService
    from sidra_ai.config.settings import Settings
    from sidra_ai.documents import Document, Provenance, SourceType, TrustLevel
    from sidra_ai.ingestion.state import StateStore
    from sidra_ai.retrieval.store import DocumentStore
    from sidra_ai.security.gate import GatePolicy, SecurityGate

    gate = SecurityGate(GatePolicy(), allowed_repositories=[_REPO])
    store = DocumentStore(gate)
    for i in range(6):
        store.add(
            Document(
                content=f"第 {i} 章。収益化の方針について。" + "掲載順は売らない。" * 8,
                provenance=Provenance(
                    source="github",
                    repository=_REPO,
                    path=f"docs/p{i}.md",
                    commit_sha="0" * 40,
                    timestamp=datetime(2026, 9, 8, tzinfo=timezone.utc),
                    source_type=SourceType.DOCS,
                    trust_level=TrustLevel.INTERNAL_REPO,
                    license="proprietary",
                ),
            )
        )
    settings = Settings(
        data_dir=home, model_backend="echo", allowed_repositories=(_REPO,)
    )
    return SidraService(
        settings,
        store=store,
        gate=gate,
        state_store=StateStore(Path(home) / "state.json"),
    )


def _conversation(turns: list[str]) -> tuple[str, list[tuple[str, str]]]:
    """Play the turns in order; return the last answer and the history."""

    with tempfile.TemporaryDirectory() as home:
        service = _service(home)
        history: list[tuple[str, str]] = []
        answer = ""
        for message in turns:
            out = service.chat(message, history=list(history))
            answer = (out.get("answer") or "").replace("\n", " ")
            history.append((message, answer))
        return answer, history


def evaluate_revision_kind_quotes_the_real_request() -> QuotesRealRequestResult:
    failures: list[str] = []
    passed = 0

    made = "犬のレポートを作って"
    answer, history = _conversation([made, "さっきのレポートを直して"])

    # A: their request, quoted.
    if made not in answer:
        failures.append(f"the reply does not quote 「{made}」: {answer[:90]}")
    else:
        passed += 1

    # B: and the generic stand-in is gone.
    if _GENERIC in answer:
        failures.append(
            f"the reply still offers the generic {_GENERIC} as the thing to send"
        )
    else:
        passed += 1

    # C: nothing in view - and nothing invented. This is the half that a fix
    # aimed only at A would get wrong: quoting something is easy, quoting
    # nothing when there is nothing is the part that needs deciding.
    bare, _ = _conversation(["さっきのレポートを直して"])
    if "依頼:「" in bare or _GENERIC in bare:
        failures.append(
            f"with no request in view the reply still printed an example: {bare[:90]}"
        )
    elif "もう一度送ってください" not in bare:
        failures.append(f"the advice itself went missing: {bare[:90]}")
    else:
        passed += 1

    # D: what was quoted is a turn that happened, not a sentence assembled to
    # look like one.
    from sidra_ai.api.service import last_creation_request

    quoted = last_creation_request(history, "レポート")
    asked = [question for question, _ in history]
    if quoted is None:
        failures.append("nothing was quoted from a conversation that contains the request")
    elif quoted not in asked:
        failures.append(f"the quote 「{quoted}」 is not one of the messages sent: {asked}")
    else:
        passed += 1

    # E: a request for a *different* kind is not their report request. Added
    # after a probe that dropped the kind filter scored full marks: the
    # conversation above holds exactly one request, of the right kind, so
    # there was nothing for the wrong-kind case to go wrong on.
    other, other_history = _conversation(
        ["猫のスライドを作って", "さっきのレポートを直して"]
    )
    if "猫のスライドを作って" in other:
        failures.append(
            f"a スライド request was quoted as the レポート request: {other[:90]}"
        )
    elif "依頼:「" in other:
        failures.append(f"something was quoted that was never a レポート request: {other[:90]}")
    else:
        passed += 1

    # F: too long to quote, so not quoted. A truncated request is not the
    # request - sending half of it produces something else, which is the
    # defect this item is about, arriving by a different door. Added after a
    # probe that truncated instead of dropping scored full marks.
    # The kind word sits early on purpose: a truncation then still contains
    # 「レポート」 and still looks quotable, which is the state that has to be
    # refused. With the word at the end, truncating merely loses it and the
    # quote disappears for the wrong reason - measured, and it made a probe
    # that truncates score full marks.
    long_request = "レポートを作って。" + "犬と猫と鳥と魚と馬と牛と羊と鹿と熊と狐について、" * 3
    assert len(long_request) > 60 and "レポート" in long_request[:60]
    long_answer, long_history = _conversation([long_request, "さっきのレポートを直して"])
    sent = [question for question, _ in long_history]
    quoted_now = None
    if "依頼:「" in long_answer:
        quoted_now = long_answer.split("依頼:「", 1)[1].split("」", 1)[0]
    if quoted_now is not None and quoted_now not in sent:
        failures.append(
            f"a request was quoted in a form nobody sent: 「{quoted_now[:40]}…」"
        )
    else:
        passed += 1

    return QuotesRealRequestResult(
        passed=not failures,
        checks_passed=passed,
        checks_total=6,
        failures=tuple(failures),
    )
