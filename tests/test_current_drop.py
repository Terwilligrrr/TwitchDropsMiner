"""A CurrentDrop answer with no user must not crash the miner (webui/patches_current_drop.py).

Production crashed on 2026-11-25 with ``TypeError: 'NoneType' object is not
subscriptable`` at twitch.py:1003 in ``_watch_loop``: Twitch answered the
CurrentDrop query with ``currentUser`` set to null (the core's own "server
error" handling also nulls the key an error points to), and the core reads
``context["data"]["currentUser"]["dropCurrentSession"]`` there and in
``process_drops``. The patch turns such an answer into "no current drop
session", which both callers already handle.
"""

from __future__ import annotations

import asyncio
import sys
import types
from pathlib import Path
from types import SimpleNamespace

import pytest


def _import_twitch_module() -> None:
    """Import twitch.py the way main_webui.py does, despite conftest's stubs."""
    if "twitch" in sys.modules:
        return
    saved = {name: sys.modules.get(name) for name in ("gui", "websocket")}
    gui_stub = types.ModuleType("gui")
    gui_stub.GUIManager = object  # type: ignore[attr-defined]
    sys.modules["gui"] = gui_stub
    sys.modules.pop("websocket", None)
    try:
        import twitch  # noqa: F401
    finally:
        for name, module in saved.items():
            if module is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = module


_import_twitch_module()
import webui.patches_current_drop as pcd  # noqa: E402
from constants import GQL_QUERIES  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def _current_drop_op():
    return GQL_QUERIES["CurrentDrop"].with_variables({"channelID": "123"})


def _other_op():
    return GQL_QUERIES["Inventory"]


def _request(monkeypatch, ops, response):
    async def original(self, ops):
        return response

    monkeypatch.setattr(pcd, "_wrapped_gql_request", original)
    return asyncio.run(pcd._gql_request(SimpleNamespace(), ops))


def _core_read(context):
    # exactly what twitch.py does at both CurrentDrop call sites
    return context["data"]["currentUser"]["dropCurrentSession"]


@pytest.mark.parametrize(
    "response",
    [
        {"data": {"currentUser": None}},
        {"data": None},
        {},
        {"data": {"currentUser": {}}},
    ],
    ids=["null-user", "null-data", "no-data", "user-without-session"],
)
def test_missing_user_reads_as_no_current_drop(monkeypatch, response):
    result = _request(monkeypatch, _current_drop_op(), response)
    assert _core_read(result) is None


def test_real_session_is_left_alone(monkeypatch):
    session = {"dropID": "abc", "currentMinutesWatched": 7}
    result = _request(
        monkeypatch, _current_drop_op(), {"data": {"currentUser": {"dropCurrentSession": session}}}
    )
    assert _core_read(result) == session


def test_other_operations_are_left_alone(monkeypatch):
    response = {"data": {"currentUser": None}}
    result = _request(monkeypatch, _other_op(), response)
    assert result == {"data": {"currentUser": None}}


def test_batched_requests_fix_only_the_current_drop_answer(monkeypatch):
    responses = [{"data": {"currentUser": None}}, {"data": {"currentUser": None}}]
    result = _request(monkeypatch, [_other_op(), _current_drop_op()], responses)
    assert result[0] == {"data": {"currentUser": None}}
    assert _core_read(result[1]) is None


def test_patch_is_installed_on_twitch_and_loaded_by_webui():
    from twitch import Twitch

    # the patch wraps whatever gql_request was there, so walk the chain of wrappers
    assert pcd._gql_request is Twitch.gql_request or any(
        getattr(module, "_original_gql_request", None) is pcd._gql_request
        for module in list(sys.modules.values())
        if module is not None and getattr(module, "__name__", "").startswith("webui.")
    )
    patches_source = (PROJECT_ROOT / "webui" / "patches.py").read_text(encoding="utf-8")
    assert "import webui.patches_current_drop" in patches_source
