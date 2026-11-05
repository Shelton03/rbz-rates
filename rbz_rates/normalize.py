"""Normalise RBZ rows into one unambiguous direction.

Why this exists: in the RBZ sheet the meaning of each row flips. For some
currencies the USD column is "USD per 1 unit" (GBP, EUR, XAU, BWP...), for
others it is "units per 1 USD" (ZAR, JPY, CHF...). The ZWG columns flip
independently: sometimes "ZWG per 1 unit" (GBP, CHF, XAU), sometimes
"units per 1 ZWG" (ZAR, NOK, CAD). The '*' marker does not reliably say which
(CAD and CYP are starred but behave like ZAR; XAU and BWP are not starred
but behave like GBP).

So we work it out from the numbers. With u = ZWG per USD (from the USD row),
the true ZWG-per-unit rate must be either idx*u or u/idx, and the published
ZWG figure is either that rate or its reciprocal. Exactly one of the four
combinations matches the published mid; that tells us the orientation.
"""
from __future__ import annotations

from .parse import ParsedDocument, RawRow

TOLERANCE = 0.01  # 1% relative error on mids


def _inv(bid: float, ask: float, mid: float) -> tuple[float, float, float]:
    # inverting a quote swaps the sides
    return (1 / ask, 1 / bid, 1 / mid)


def _orientation(row: RawRow, u: float) -> tuple[str, str, float]:
    """Return (index_orientation, local_orientation, relative_error)."""
    idx, pub = row.index[2], row.local[2]
    candidates = []
    for idx_o, per_unit in (("usd_per_unit", idx * u), ("units_per_usd", u / idx)):
        for loc_o, predicted in (("zwg_per_unit", per_unit), ("units_per_zwg", 1 / per_unit)):
            candidates.append((abs(predicted - pub) / pub, idx_o, loc_o, per_unit))
    candidates.sort()
    err, idx_o, loc_o, per_unit = candidates[0]
    # ambiguous only if another combo also fits AND implies a different rate
    for err2, _, _, per_unit2 in candidates[1:]:
        if err2 <= TOLERANCE and abs(per_unit2 - per_unit) / per_unit > TOLERANCE:
            return idx_o, loc_o, float("nan")
    return idx_o, loc_o, err


def normalise(doc: ParsedDocument) -> dict:
    usd = next(r for r in doc.rows if r.code == "USD")
    u = usd.local[2]
    rates, warnings = {}, []

    for row in doc.rows:
        idx_o, loc_o, err = _orientation(row, u)
        verified = err == err and err <= TOLERANCE  # nan-safe

        zwg = row.local if loc_o == "zwg_per_unit" else _inv(*row.local)
        usd_q = row.index if idx_o == "usd_per_unit" else _inv(*row.index)

        if not verified:
            warnings.append(f"{row.code}: published figures are not internally consistent "
                            f"(best fit error {err:.2%}); values kept as published")
        rates[row.code] = {
            "zwg_per_unit": _q(zwg),
            "usd_per_unit": _q(usd_q),
            "aliases": row.aliases,
            "verified": verified,
            "as_published": {
                "starred": row.starred,
                "index": _q(row.index),
                "index_orientation": idx_o,
                "zwg": _q(row.local),
                "zwg_orientation": loc_o,
            },
        }

    return {
        "date": doc.date.isoformat(),
        "base": doc.base,
        "parser": doc.parser,
        "rates": rates,
        "warnings": warnings,
    }


def _q(t: tuple[float, float, float]) -> dict:
    return {"bid": round(t[0], 10), "ask": round(t[1], 10), "mid": round(t[2], 10)}
