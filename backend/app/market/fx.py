"""Reference exchange rates used only to put award values from different datasets on one scale.

Package sizes and "similar work" thresholds are compared in ₹ crore. These are fixed reference
rates (override with TS_FX_<CUR>=<INR per unit>), not live quotes, so cross-currency comparisons
are indicative. Values are always stored in their original currency as well.
"""

from __future__ import annotations

import os

DEFAULT_INR_PER_UNIT = {"INR": 1.0, "USD": 88.0, "EUR": 102.0, "GBP": 118.0, "UAH": 2.1, "XDR": 120.0}
CRORE = 1e7


def inr_per_unit(currency: str | None) -> float | None:
    cur = (currency or "").upper().strip()
    if not cur:
        return None
    env = os.environ.get(f"TS_FX_{cur}")
    if env:
        return float(env)
    return DEFAULT_INR_PER_UNIT.get(cur)


def to_inr_cr(amount: float | None, currency: str | None) -> float | None:
    if amount is None:
        return None
    rate = inr_per_unit(currency)
    return None if rate is None else round(amount * rate / CRORE, 6)


def rates() -> dict[str, float]:
    return {cur: inr_per_unit(cur) for cur in DEFAULT_INR_PER_UNIT}  # type: ignore[misc]
