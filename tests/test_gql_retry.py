"""Tests for retrying temporary GQL "service error" failures (webui/patches_gql_retry.py).

One brief "service error" from Twitch used to crash the whole miner: the core
retries it once, then raises GQLException, which ends the app.
"""

from __future__ import annotations

import asyncio
import logging
import sys
import types
from types import SimpleNamespace

import pytest

def _import_twitch_module() -> None:
    """Import twitch.py the way main_webui.py does, despite conftest's stubs.

    twitch.py does ``from gui import GUIManager`` (the tkinter GUI, replaced by a
    stub in main_webui.py) and ``from websocket import ...`` (this project's
    websocket.py, which conftest shadows with a stub for engineio's sake).
    """
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
import webui.patches_gql_retry as gql_retry  # importing it patches Twitch.gql_request
from exceptions import GQLException
from twitch import Twitch

SERVICE_ERROR = {"message": "service error", "path": ["channel", "viewerDropCampaigns"]}
OTHER_ERROR = {"message": "PersistedQueryNotFound", "path": ["channel"]}


@pytest.fixture
def sleeps(monkeypatch) -> list[float]:
    delays: list[float] = []

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)
    return delays


def _fake_original(monkeypatch, outcomes: list):
    """Replace the real request with one that raises/returns each outcome in turn."""
    calls: list[tuple] = []

    async def original(self, ops):
        calls.append((self, ops))
        outcome = outcomes.pop(0) if len(outcomes) > 1 else outcomes[0]
        if isinstance(outcome, Exception):
            raise outcome
        return outcome

    monkeypatch.setattr(gql_retry, "_original_gql_request", original)
    return calls


def _request(ops="op"):
    return asyncio.run(Twitch.gql_request(SimpleNamespace(), ops))


def test_service_error_then_success_returns_result(monkeypatch, sleeps, caplog):
    calls = _fake_original(monkeypatch, [GQLException([SERVICE_ERROR]), {"data": 1}])
    with caplog.at_level(logging.WARNING, logger="TwitchDrops"):
        assert _request() == {"data": 1}
    assert len(calls) == 2
    assert sleeps == [10]
    assert "service error" in caplog.text


def test_non_transient_error_raises_at_once(monkeypatch, sleeps):
    calls = _fake_original(monkeypatch, [GQLException([OTHER_ERROR])])
    with pytest.raises(GQLException):
        _request()
    assert len(calls) == 1
    assert sleeps == []


def test_mixed_errors_raise_at_once(monkeypatch, sleeps):
    calls = _fake_original(monkeypatch, [GQLException([SERVICE_ERROR, OTHER_ERROR])])
    with pytest.raises(GQLException):
        _request()
    assert len(calls) == 1
    assert sleeps == []


def test_service_error_every_time_raises_after_four_retries(monkeypatch, sleeps):
    error = GQLException([SERVICE_ERROR])
    calls = _fake_original(monkeypatch, [error])
    with pytest.raises(GQLException) as excinfo:
        _request()
    assert excinfo.value is error
    assert len(calls) == 5
    assert sleeps == [10, 30, 60, 120]


def test_string_message_raises_at_once(monkeypatch, sleeps):
    calls = _fake_original(monkeypatch, [GQLException("Unauthorized: bad token")])
    with pytest.raises(GQLException, match="Unauthorized"):
        _request()
    assert len(calls) == 1
    assert sleeps == []
