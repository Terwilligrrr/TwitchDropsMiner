"""
Treat a CurrentDrop answer with no user as "no current drop", as a webui-only
patch so no core file is edited.

Twitch sometimes answers the CurrentDrop query with ``currentUser`` set to null
(the core's gql_request also nulls the key a "server error" points to). The
core reads ``context["data"]["currentUser"]["dropCurrentSession"]`` in
``_watch_loop`` and ``process_drops``, so that answer raised a TypeError that
ended the whole app (production, 2026-11-25). Here such an answer becomes
``dropCurrentSession: None``, which both callers already handle.
"""

from __future__ import annotations

import logging

import twitch as _twitch
from constants import GQL_QUERIES

logger = logging.getLogger("TwitchDrops")

CURRENT_DROP_OPERATION: str = GQL_QUERIES["CurrentDrop"]["operationName"]

_wrapped_gql_request = _twitch.Twitch.gql_request


def _fill_missing_session(op, response) -> None:
    if not isinstance(op, dict) or op.get("operationName") != CURRENT_DROP_OPERATION:
        return
    if not isinstance(response, dict):
        return
    data = response.get("data")
    if not isinstance(data, dict):
        data = response["data"] = {}
    user = data.get("currentUser")
    if not isinstance(user, dict):
        logger.warning("Twitch sent no user for the current drop; treating it as no drop")
        data["currentUser"] = {"dropCurrentSession": None}
        return
    user.setdefault("dropCurrentSession", None)


async def _gql_request(self, ops):
    response = await _wrapped_gql_request(self, ops)
    if isinstance(ops, list):
        if isinstance(response, list):
            for op, single_response in zip(ops, response):
                _fill_missing_session(op, single_response)
    else:
        _fill_missing_session(ops, response)
    return response


_twitch.Twitch.gql_request = _gql_request  # type: ignore[method-assign]
