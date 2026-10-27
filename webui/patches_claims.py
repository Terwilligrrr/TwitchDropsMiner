"""
Claim each drop once per run, done as webui-only patches so no core file is edited.

For campaigns the account isn't linked to, Twitch accepts the claim but keeps
reporting ``isClaimed: false`` in the inventory. The core loop then re-sent
every such claim on each inventory fetch (hourly, on each channel switch and
on each restart) and printed "Claimed drop" every time. Here the claim IDs
Twitch accepted are remembered, and a drop with such an ID is treated as
claimed when the inventory is rebuilt.
"""

from __future__ import annotations

import inventory as _inventory

_accepted_claim_ids: set[str] = set()


def forget_claims() -> None:
    _accepted_claim_ids.clear()


_original_init = _inventory.BaseDrop.__init__
_original_claim_inner = _inventory.BaseDrop._claim


def _init(self, campaign, data, claimed_benefits) -> None:
    _original_init(self, campaign, data, claimed_benefits)
    if self.claim_id in _accepted_claim_ids:
        self.is_claimed = True


async def _claim_inner(self) -> bool:
    claim_id = self.claim_id
    result = await _original_claim_inner(self)
    if result and claim_id is not None:
        _accepted_claim_ids.add(claim_id)
    return result


_inventory.BaseDrop.__init__ = _init  # type: ignore[method-assign]
_inventory.BaseDrop._claim = _claim_inner  # type: ignore[method-assign]
