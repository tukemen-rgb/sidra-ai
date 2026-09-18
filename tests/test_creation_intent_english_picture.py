"""The ordinary English words for a picture reach the art lane.

C-1948, and the mirror of C-1804. That item found the Japanese side of this
generator reachable only through 「アート」 and added 「絵」 and 「イラスト」,
the words people actually write. English was then left in exactly the state
Japanese had been in: "artwork", "wallpaper", "abstract art", "generative
art" and "digital art" routed here, and 「draw a picture of an owl」,
「make an image of an owl」, 「make an owl illustration」 and 「make a drawing
of an owl」 were all ``unknown`` - four phrasings of the one thing this
generator makes.

The second half of the item is the reason it was not one line. English
modifies the other way round from Japanese: the head noun comes **first**,
so 「a slide deck with pictures of owls」 puts the deck at the front and the
picture at the end, and the latest-wins rule - which is right for 「ゲームの
資料」 - handed the deck to the art lane. Four requests changed lane the
moment the words were added. So the five English picture words are weak:
any other kind named anywhere in the message wins, and they are used only
when nothing else matched.

Both halves are pinned here, in one table, with the requests that must NOT
become art next to the ones that must.
"""

from __future__ import annotations

import pytest

from sidra_ai.creation.intent import detect_creation_intent

#: request -> the kind it has to be read as.
CASES: tuple[tuple[str, str], ...] = (
    # the words this item added
    ("draw a picture of an owl", "art"),
    ("make an image of an owl", "art"),
    ("make an owl illustration", "art"),
    ("make a drawing of an owl", "art"),
    ("make a painting of an owl", "art"),
    # the words that already worked, kept so they cannot be lost quietly
    ("make artwork of an owl", "art"),
    ("make a wallpaper", "art"),
    ("make abstract art", "art"),
    ("絵を描いて", "art"),
    ("イラストを描いて", "art"),
    # a verb with no artifact noun is not a request, in either language:
    # 「ふくろうを描いて」 is unknown too, so this is parity and not a gap.
    ("draw an owl", "unknown"),
    ("ふくろうを描いて", "unknown"),
    # the four that changed lane when the words were added, and must not
    ("make a gif of a picture frame", "gif"),
    ("make a game where you draw pictures", "game"),
    ("make a slide deck with pictures of owls", "deck"),
    ("write a report about image processing", "document"),
    # and the lanes either language has always resolved by position
    ("make a gif of an owl", "gif"),
    ("make a slide deck about owls", "deck"),
    ("write a document about owls", "document"),
    ("make a game about an owl", "game"),
    ("make a 3d model of an owl", "model3d"),
    ("絵を描くゲームを作って", "game"),
    ("絵本のようなスライドを作って", "deck"),
    ("魚の絵柄のGIFを作って", "gif"),
    # a question about a picture is still a question
    ("what is a picture", "unknown"),
    ("how do I draw", "unknown"),
)


@pytest.mark.parametrize(("request_text", "expected"), CASES)
def test_the_request_reaches_the_lane_it_names(request_text: str, expected: str) -> None:
    assert detect_creation_intent(request_text).kind.value == expected
