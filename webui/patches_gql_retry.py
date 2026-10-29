"""
Keep retrying Twitch's temporary "service error" GQL failures, as a webui-only
patch so no core file is edited.

The core retries a "service error" once and then raises GQLException, which
ends the whole app. Twitch itself marks the error as temporary, so here it is
retried a few more times with growing pauses (about 3.7 minutes in total)
before giving up.
"""

from __future__ import annotations

import asyncio
import logging

import twitch as _twitch
from exceptions import GQLException

logger = logging.getLogger("TwitchDrops")

RETRY_DELAYS = (10, 30, 60, 120)

_original_gql_request = _twitch.Twitch.gql_request


def _is_service_error(exc: GQLException) -> bool:
    # GQLException carries the error dicts as args[0]; its other raises pass a str
    errors = exc.args[0] if exc.args else None
    return (
        isinstance(errors, list)
        and bool(errors)
        and all(isinstance(e, dict) and e.get("message") == "service error" for e in errors)
    )


async def _gql_request(self, ops):
    for attempt, delay in enumerate(RETRY_DELAYS, start=1):
        try:
            return await _original_gql_request(self, ops)
        except GQLException as exc:
            if not _is_service_error(exc):
                raise
            logger.warning(
                f"Twitch GQL service error (retry {attempt}/{len(RETRY_DELAYS)} "
                f"in {delay}s): {exc.args[0]}"
            )
        await asyncio.sleep(delay)
    return await _original_gql_request(self, ops)


_twitch.Twitch.gql_request = _gql_request  # type: ignore[method-assign]
