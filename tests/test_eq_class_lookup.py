"""Game/Channel/Stream __eq__ must not depend on ``self.__class__``.

Production crashed 3 times (2026-11-01, 11-22, 11-23) with
``TypeError: Game.__init__() missing 1 required positional argument: 'data'``
(or ``Channel.__init__() missing ... 'twitch'``) raised straight out of
``isinstance(other, self.__class__)`` inside ``__eq__``. The bytecode in the
frozen build matched the source, so the ``self.__class__`` lookup itself went
wrong. ``__eq__`` now names the class directly. These tests make ``__class__``
hostile (its isinstance check tries to construct the class with no args) and
check ``==`` still works.
"""

from __future__ import annotations

from types import SimpleNamespace

from channel import Channel, Stream
from utils import Game


class _Boom(type):
    def __instancecheck__(cls, instance):
        cls()  # TypeError: missing required positional argument(s)
        return False


class _NeedsArgs(metaclass=_Boom):
    def __init__(self, required):
        pass


def _hostile(base):
    class Hostile(base):
        @property
        def __class__(self):
            return _NeedsArgs

    return Hostile


def test_game_eq_ignores_hostile_class_attr():
    hostile = _hostile(Game)({"id": "1", "name": "A"})
    other = Game({"id": "1", "name": "A"})
    assert hostile == other
    assert not (hostile == Game({"id": "2", "name": "B"}))


def test_channel_eq_ignores_hostile_class_attr():
    twitch = SimpleNamespace(
        settings=SimpleNamespace(available_drops_check=False),
        gui=SimpleNamespace(channels=None),
    )
    hostile = _hostile(Channel)(twitch, id=5, login="x", display_name="X")
    other = Channel(twitch, id=5, login="x", display_name="X")
    assert hostile == other
    assert not (hostile == Channel(twitch, id=6, login="y", display_name="Y"))


def test_stream_eq_ignores_hostile_class_attr():
    ch = SimpleNamespace(_twitch=SimpleNamespace(settings=SimpleNamespace(available_drops_check=False)), id=1)
    mk = lambda cls, bid: cls(ch, id=bid, game=None, viewers=1, title="t")
    hostile = mk(_hostile(Stream), 9)
    assert hostile == mk(Stream, 9)
    assert not (hostile == mk(Stream, 10))
