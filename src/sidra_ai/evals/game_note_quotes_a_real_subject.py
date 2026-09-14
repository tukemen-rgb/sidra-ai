"""Does the game's honesty note quote something that is actually a subject?

C-1825. 「「X」の題材を描く型はまだ無いため…」 is the game path's admission that
the page depicts something other than what was asked for. Measured across
twenty requests that named no genre, it fired nineteen times and its claim was
true three times: the other sixteen quoted an adjective (「面白い」「短い」),
a device (「スマホ」「ブラウザ」) or a count (「3面」「30秒」) back to the
operator as their subject.

The device case denied something the product does - the games are playable
one-handed on a phone, which ``creation_one_thumb_play`` measures across all
ten templates - so 「スマホで遊べるゲームを作って」 was answered with 「『スマホ』
の題材を描く型はまだ無い」.

``games.py`` already had the rule for one word class: a request naming only a
difficulty has no subject, and titling the page 「むずかしい」 and then saying
its subject cannot be drawn is one word playing both roles (C-1235). This eval
holds both sides - the sixteen that must stay silent and the ones that must
still speak - because a guard that silences everything would score the same on
the first half alone.
"""

from __future__ import annotations

from dataclasses import dataclass

from sidra_ai.creation.game_job import build_game_generator
from sidra_ai.creation.games import (
    TEMPLATES,
    choose_difficulty,
    generate_game,
    genre_fallback_note,
)
from sidra_ai.creation.intent import detect_creation_intent
from sidra_ai.evals.scratch import scratch_dir

#: The sixteen the note was wrong about, by class.
NOT_A_SUBJECT: tuple[str, ...] = (
    "面白いゲームを作って",
    "短いゲームを作って",
    "長いゲームを作って",
    "新しいゲームを作って",
    "かわいいゲームを作って",
    "かっこいいゲームを作って",
    "すごいゲームを作って",
    "楽しいゲームを作って",
    "シンプルなゲームを作って",
    "スマホで遊べるゲームを作って",
    "パソコンで遊べるゲームを作って",
    "ブラウザで遊べるゲームを作って",
    "3面のゲームを作って",
    "5ステージのゲームを作って",
    "2分で遊べるゲームを作って",
    "30秒のゲームを作って",
)

#: Requests that do name something the page does not draw. The note must keep
#: firing for these; they are the reason it exists (C-1205).
REAL_SUBJECT: tuple[str, ...] = (
    "猫のゲームを作って",
    "忍者のゲームを作って",
    "お寿司のゲームを作って",
    "海賊のゲームを作って",
)

_CAVEAT = "の題材を描く型はまだ無い"


@dataclass(frozen=True)
class GameSubjectNoteResult:
    passed: bool
    checks_passed: int
    checks_total: int
    failures: tuple[str, ...] = ()


def _note(request: str) -> str:
    game = generate_game(request)
    return genre_fallback_note(request, game.template, game.title)


def _summary(request: str) -> str:
    gen = build_game_generator(scratch_dir())
    outcome = gen(request, detect_creation_intent(request))
    return getattr(outcome, "summary", "") or ""


def evaluate_game_note_quotes_a_real_subject() -> GameSubjectNoteResult:
    checks = 0
    failures: list[str] = []

    def add(cond: bool, msg: str) -> None:
        nonlocal checks
        if cond:
            checks += 1
        else:
            failures.append(msg)

    # --- (A) not one of the sixteen draws the caveat ----------------------
    spoke = [request for request in NOT_A_SUBJECT if _note(request)]
    add(not spoke,
        f"A: the caveat still quotes a word that names no subject: {spoke[:4]}")
    # --- (B) and every real subject still draws it ------------------------
    silent = [request for request in REAL_SUBJECT if not _note(request)]
    add(not silent,
        f"B: the caveat went silent for a real subject: {silent}")
    # --- (C) such a request takes the template's own title ----------------
    #     The title and the caveat come from one place, so this is the same
    #     decision seen from the page side rather than a second one.
    phone = generate_game("スマホで遊べるゲームを作って")
    add(phone.title == TEMPLATES[phone.template].default_title,
        f"C: 「スマホで遊べる」 is still the page's title ({phone.title!r})")
    # --- (D) the caveat names the subject when there is one ---------------
    add("猫" in _note("猫のゲームを作って"),
        "D: the caveat no longer names 「猫」")
    # --- (E) C-1235's difficulty case is unchanged ------------------------
    hard = generate_game("難しいゲームを作って")
    add(not _note("難しいゲームを作って")
        and hard.title == TEMPLATES[hard.template].default_title
        and choose_difficulty("難しいゲームを作って") == "hard",
        "E: the difficulty-only request changed behaviour")
    # --- (F) a genre the product builds still draws no caveat -------------
    add(not _note("レースのゲームを作って"),
        "F: a request naming a genre we build drew a substitution caveat")
    # --- (G) the chat summary says the same as the page -------------------
    add(_CAVEAT not in _summary("スマホで遊べるゲームを作って")
        and _CAVEAT in _summary("猫のゲームを作って"),
        "G: the summary and the page disagree about whether a subject was named")
    # --- (H) an adjective in front of a subject is still a subject --------
    #     The guard removes words; removing too many would silence the note
    #     for 「かわいい猫」, which is the failure in the other direction.
    add(_CAVEAT in _note("かわいい猫のゲームを作って"),
        "H: an adjective in front of a real subject silenced the caveat")

    return GameSubjectNoteResult(
        passed=not failures,
        checks_passed=checks,
        # Derived, never written down: see sidra_ai/evals/__init__.py.
        checks_total=checks + len(failures),
        failures=tuple(failures),
    )


__all__ = [
    "GameSubjectNoteResult",
    "NOT_A_SUBJECT",
    "REAL_SUBJECT",
    "evaluate_game_note_quotes_a_real_subject",
]
