"""Normalise RBZ rows into one unambiguous direction.

Why this exists: in the RBZ sheet the meaning of each row flips. For some
currencies the USD column is "USD per 1 unit" (GBP, EUR, XAU, BWP...), for
others it is "units per 1 USD" (ZAR, JPY, CHF...). The local-currency columns
flip independently: sometimes "ZWG per 1 unit" (GBP, CHF, XAU), sometimes
"units per 1 ZWG" (ZAR, NOK, CAD). The '*' marker does not reliably say which
(CAD and CYP are starred but behave like ZAR; XAU and BWP are not starred
but behave like GBP).

So we work it out from the numbers. With u = local per USD (from the USD row),
the true local-per-unit rate must be either idx*u or u/idx, and the published
local figure is either that rate or its reciprocal. Exactly one of the four
combinations matches the published mid; that tells us the orientation.

The local currency is whatever the sheet is in: ZWG since April 2024, ZWL (and
RTGS$) before. Fields are named after it (zwg_per_unit, zwl_per_unit, ...), so a
ZWL figure can never be mistaken for a ZWG one.

Some late-ZWL sheets print the local column too coarsely to check: RBZ rounds
bid and ask to 4 decimals and averages them, so ZAR shows as 0.0009 ZWL (~6% off).
When a row misses the 1% check by no more than one unit of its last printed
digit, its local rate is derived from RBZ's precise USD figures and marked
"derived_from": "usd". If that unit is itself over 15% of the value (0.0001,
0.0005), the printed figure can't confirm anything: the row is still derived but
left unverified with a warning. The printed numbers always stay in as_published.
"""
from __future__ import annotations

from .parse import ParsedDocument, RawRow, ShapeError

TOLERANCE = 0.01          # 1% relative error on mids
MAX_UNRECONCILED = 0.2    # more inconsistent rows than this: the columns were probably misread
MAX_CHECKABLE_UNIT = 0.15 # a printed figure whose last digit is worth more than this can't confirm a rate


def _inv(bid: float, ask: float, mid: float) -> tuple[float, float, float]:
    # inverting a quote swaps the sides
    return (1 / ask, 1 / bid, 1 / mid)


def _orientation(row: RawRow, u: float, base: str) -> tuple[str, str, float]:
    """Return (index_orientation, local_orientation, relative_error)."""
    idx, pub = row.index[2], row.local[2]
    if pub <= 0 or idx <= 0:
        return "usd_per_unit", f"{base}_per_unit", float("nan")
    candidates = []
    for idx_o, per_unit in (("usd_per_unit", idx * u), ("units_per_usd", u / idx)):
        for loc_o, predicted in ((f"{base}_per_unit", per_unit), (f"units_per_{base}", 1 / per_unit)):
            candidates.append((abs(predicted - pub) / pub, idx_o, loc_o, per_unit))
    candidates.sort()
    err, idx_o, loc_o, per_unit = candidates[0]
    # ambiguous only if another combo also fits AND implies a different rate
    for err2, _, _, per_unit2 in candidates[1:]:
        if err2 <= TOLERANCE and abs(per_unit2 - per_unit) / per_unit > TOLERANCE:
            return idx_o, loc_o, float("nan")
    return idx_o, loc_o, err


def _printed_unit(row: RawRow) -> float:
    """One unit of the local figures' last printed digit, relative to the mid."""
    return 10 ** -row.local_decimals / row.local[2] if row.local[2] > 0 else 0.0


def _implied_usd_rate(row: RawRow, u: float, base: str) -> float | None:
    """The local-per-USD rate this row's cross figures imply (the reading closest to u)."""
    idx, pub = row.index[2], row.local[2]
    if idx <= 0 or pub <= 0:
        return None
    options = []
    for per_unit in (pub, 1 / pub):            # local figure as printed, or its reciprocal
        options += [per_unit / idx, per_unit * idx]  # index as USD per unit, or units per USD
    return min(options, key=lambda v: abs(v - u) / u)


def normalise(doc: ParsedDocument) -> dict:
    out = _normalise(doc)
    if out is not None:
        return out
    # Most rows disagree with the USD row. If they agree with *each other* on one USD rate,
    # the columns were read correctly and RBZ's USD row is out of step with its own crosses
    # (seen in 2019); publish as printed, unverified, with a note. Otherwise refuse.
    u = next(r for r in doc.rows if r.code == "USD").local[2]
    implied = sorted(v for r in doc.rows if r.code != "USD" and (v := _implied_usd_rate(r, u, doc.base.lower())))
    if implied:
        mid = implied[len(implied) // 2]
        agree = sum(abs(v - mid) / mid <= TOLERANCE for v in implied)
        if agree >= (1 - MAX_UNRECONCILED) * len(implied):
            out = _normalise(doc, usd_rate=mid, strict=False)
            out["warnings"].insert(0, f"The cross rates on this sheet imply 1 USD = {mid:.4f} {doc.base}, "
                                      f"but its USD row shows {u:.4f} ({abs(mid - u) / u:.1%} apart); "
                                      "figures are kept as printed and marked unverified")
            for r in out["rates"].values():
                r["verified"] = False
            return out
    unreconciled = sum(1 for w in _normalise(doc, strict=False)["warnings"] if "not internally consistent" in w)
    raise ShapeError(f"{unreconciled} of {len(doc.rows)} rows don't reconcile with the USD rate or with each other; "
                     "the columns were probably misread, so the sheet isn't published", doc.layout)


def _normalise(doc: ParsedDocument, usd_rate: float | None = None, strict: bool = True) -> dict | None:
    """Normalise against the USD row's rate (or usd_rate). With strict, None if too many rows don't reconcile."""
    base = doc.base.lower()
    key = f"{base}_per_unit"
    usd = next(r for r in doc.rows if r.code == "USD")
    u_q = usd.local  # local per USD: bid, ask, mid
    if usd_rate is not None:
        scale = usd_rate / u_q[2]
        u_q = (u_q[0] * scale, u_q[1] * scale, usd_rate)
    rates, warnings = {}, list(doc.warnings)
    unreconciled = 0

    for row in doc.rows:
        idx_o, loc_o, err = _orientation(row, u_q[2], base)
        usd_q = row.index if idx_o == "usd_per_unit" else _inv(*row.index)
        verified = err == err and err <= TOLERANCE  # nan-safe
        unit = _printed_unit(row)
        derived = (not verified and err == err and row.code != "USD" and err <= unit * 1.05)
        if derived:
            # printed too coarsely to check at 1%: compute from RBZ's precise USD figures
            local_q = (usd_q[0] * u_q[0], usd_q[1] * u_q[1], usd_q[2] * u_q[2])
            verified = unit <= MAX_CHECKABLE_UNIT
            if not verified:
                warnings.append(f"{row.code}: printed too coarsely to confirm ({row.local[2]}); "
                                "rate derived from the USD column")
        elif loc_o != key and min(row.local) <= 0:
            # printed with a zero (e.g. 0.0000 0.0001 0.0001): can't be inverted, so derive it
            local_q = (usd_q[0] * u_q[0], usd_q[1] * u_q[1], usd_q[2] * u_q[2])
            derived, verified = True, False
            warnings.append(f"{row.code}: printed with a zero ({' '.join(map(str, row.local))}); "
                            "rate derived from the USD column")
        else:
            local_q = row.local if loc_o == key else _inv(*row.local)
            if not verified:
                unreconciled += 1
                warnings.append(f"{row.code}: published figures are not internally consistent "
                                f"(best fit error {err:.2%}); values kept as published")

        entry = {
            key: _q(local_q),
            "usd_per_unit": _q(usd_q),
            "aliases": row.aliases,
            "verified": verified,
            "as_published": {
                "starred": row.starred,
                "index": _q(row.index),
                "index_orientation": idx_o,
                base: _q(row.local),
                f"{base}_orientation": loc_o,
            },
        }
        if derived:
            entry["derived_from"] = "usd"
        rates[row.code] = entry

    if strict and unreconciled > MAX_UNRECONCILED * len(doc.rows):
        return None

    return {
        "date": doc.date.isoformat(),
        "base": doc.base,
        "parser": doc.parser,
        "rates": rates,
        "warnings": warnings,
    }


def _q(t: tuple[float, float, float]) -> dict:
    return {"bid": round(t[0], 10), "ask": round(t[1], 10), "mid": round(t[2], 10)}
