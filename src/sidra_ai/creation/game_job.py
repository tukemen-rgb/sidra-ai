"""The game generator as the router sees it.

Kept apart from :mod:`sidra_ai.creation.games` for the same reason the deck
job is: the builder stays a library with no opinion about HTTP or artifact
directories, and this file holds the one callable the router needs.

The summary reports the validator's verdict rather than the fact that a file
was written. "作りました" about a page whose script never parsed is exactly
the claim this project keeps refusing to make elsewhere, and a generator is
the last place it should start.
"""

from __future__ import annotations

from pathlib import Path

from sidra_ai.creation.games import (
    TEMPLATES,
    detect_genre,
    generate_game,
    save_game,
    validate_game_html,
)
from sidra_ai.creation.evidence import Fact
from sidra_ai.creation.intent import CreationIntent
from sidra_ai.creation.router import CreationOutcome


def build_game_generator(data_dir: str | Path):
    def generate(
        message: str,
        intent: CreationIntent,
        retrieved: list[Fact] | None = None,
    ) -> CreationOutcome:
        # Retrieved evidence becomes the page's citation line, not its
        # contents: a game's rules are the template's, and pulling text from
        # the corpus into a playable page would put DATA somewhere no guard
        # looks. What it earns is an honest footer - "this is where the
        # colours came from" - instead of the hardcoded default.
        # ``Fact.source`` is already the "repository path" label; the fields
        # this line first reached for do not exist on it, and a footer that
        # raised would have taken the whole game down for a citation line.
        evidence = [fact.source for fact in (retrieved or []) if fact.source]
        game = generate_game(message, evidence=evidence or None)
        verdict = validate_game_html(game.html)
        path = save_game(game, data_dir)
        # A request that names a genre we have no template for still gets a
        # playable page - but calling that page a シューティング because the
        # operator asked for one is the cheapest lie this generator could
        # tell, and the one hardest to notice: the artifact opens and runs.
        # So the mismatch is said out loud, and it is said *only* when there
        # is one. A caveat on a request we did satisfy is its own dishonesty.
        requested = detect_genre(message)
        substituted = requested is not None and not requested.supported
        if verdict["playable"] and substituted and requested is not None:
            summary = (
                f"{requested.genre}型はまだ作れないため、いちばん近い"
                f"「{TEMPLATES[game.template].default_title}」型で作りました"
                f"（難易度 {game.difficulty}）。"
                "ブラウザで開けばそのまま遊べます。"
            )
        elif verdict["playable"]:
            summary = (
                f"「{game.title}」を作りました（難易度 {game.difficulty}）。"
                "ブラウザで開けばそのまま遊べます。"
            )
        else:
            # Still saved: a broken artifact an operator can open and read is
            # more useful than a deletion they cannot inspect.
            summary = (
                f"「{game.title}」を作りましたが、遊べる状態ではありません: "
                + "、".join(str(f) for f in verdict["failures"])
            )
        return CreationOutcome(
            kind=intent.kind,
            handled=True,
            summary=summary,
            artifact_path=str(path),
            details={
                "template": game.template,
                "difficulty": game.difficulty,
                "playable": verdict["playable"],
                "js_checker": verdict["js_checker"],
                # Present on every game, not only the substituted ones: a
                # field that appears exactly when something went wrong is a
                # field no caller writes a check against.
                "requested_genre": requested.genre if requested else "",
                "built_template": game.template,
                "genre_substituted": substituted,
            },
        )

    return generate


__all__ = ["build_game_generator"]
