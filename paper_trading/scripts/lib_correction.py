#!/usr/bin/env python3
"""
lib_correction.py  —  market-blend correction layer (Stage 3, v2)

WHY THIS EXISTS
---------------
The backtest verdict (technical_record §12.4) is blunt: the model claimed ~14c
mean edge but only realized a 43% win rate, and the 3c gate fires exactly where
the model most disagrees with the market -- precisely where history says the
market was closer to right. The live calibration table confirms the shape: in the
low-probability tail the model OVER-states the unlikely side
(model_p (0,0.4] -> realized ~0.23 vs claimed ~0.32).

So a raw "model edge" is not a tradeable edge. Before any edge number is allowed
to drive a position, the model probability is shrunk toward the market price. The
market is the better-calibrated estimator in the tails; blending toward it removes
most of the fictional edge and leaves only the part the market itself doesn't
already reflect.

This module is pure numpy (no model, no network) so it can be unit-tested
anywhere, including in the read-only Claude sandbox. Run `python lib_correction.py
--selftest` to verify.

PUBLIC API
----------
  devig_yes(yes_ask_c, no_ask_c)      -> clean market P(YES)  (0..1) or None
  blend(model_p, market_p, w)         -> corrected fair value  (0..1)
  corrected_edge(model_p, market_p, ask, fee_per_ct, w) -> dict with fv + edge
  fit_blend_weight(model_ps, market_ps, outcomes, grid) -> (w*, logloss table)

CONVENTION
----------
Kalshi quotes both legs as *asks* in cents. yes_ask is the cost to BUY YES;
no_ask is the cost to BUY NO, and no_ask = 1 - yes_bid. So the YES bid/ask
midpoint -- the cleanest single market estimate of P(YES) -- is
    yes_mid = (yes_ask + (1 - no_ask)) / 2 = (yes_ask - no_ask + 1) / 2
We use that when both sides are present, and fall back to a proportional de-vig
(yes_ask / (yes_ask + no_ask)) when only the two asks are available.
"""
from __future__ import annotations

import argparse
from typing import Iterable, Optional

import numpy as np

# Default blend weight on the MODEL. 0.5 = trust model and market equally.
# Lower => trust the market more (more conservative). Fit it with
# fit_blend_weight() once enough paired (model, market, outcome) rows exist;
# until then 0.5 is the honest prior given the backtest over-claim.
DEFAULT_BLEND_W = 0.5


def _to_prob(x) -> Optional[float]:
    """Accept cents (e.g. 45 or 0.45) and return a dollar probability in (0,1)."""
    if x is None:
        return None
    x = float(x)
    if x > 1.0:           # given in cents
        x = x / 100.0
    if not (0.0 <= x <= 1.0):
        return None
    return x


def devig_yes(yes_ask_c, no_ask_c) -> Optional[float]:
    """
    Clean market estimate of P(YES) from the two Kalshi asks.

    Both args are the ASK prices (cents or dollars). Returns a probability in
    (0,1), or None if neither side is usable.
    """
    ya = _to_prob(yes_ask_c)
    na = _to_prob(no_ask_c)
    if ya is not None and na is not None and 0 < ya < 1 and 0 < na < 1:
        # YES bid = 1 - no_ask; midpoint of YES bid/ask removes the spread.
        yes_mid = (ya + (1.0 - na)) / 2.0
        # Guard against crossed/locked books.
        return float(min(max(yes_mid, 1e-4), 1 - 1e-4))
    if ya is not None and na is not None and (ya + na) > 0:
        return float(min(max(ya / (ya + na), 1e-4), 1 - 1e-4))
    if ya is not None and 0 < ya < 1:
        return ya
    if na is not None and 0 < na < 1:
        return 1.0 - na
    return None


def blend(model_p: float, market_p: Optional[float], w: float = DEFAULT_BLEND_W) -> float:
    """
    Corrected fair value = w * model + (1 - w) * market.

    If market_p is None (no usable quote) we fall back to the raw model -- but
    callers should treat a no-market leg as un-tradeable, since we cannot correct
    what we cannot anchor.
    """
    m = float(model_p)
    if market_p is None:
        return float(min(max(m, 0.0), 1.0))
    p = w * m + (1.0 - w) * float(market_p)
    return float(min(max(p, 0.0), 1.0))


def corrected_edge(model_p: float, market_p: Optional[float], ask,
                   fee_per_ct: float = 0.0, w: float = DEFAULT_BLEND_W) -> dict:
    """
    Net edge per contract computed against the CORRECTED fair value, not the raw
    model. edge = blended_fv - ask - fee_per_ct.

    Returns the components so the caller can log both the raw and corrected edge
    and see how much "edge" the correction removed.
    """
    a = _to_prob(ask)
    fv = blend(model_p, market_p, w)
    raw_fv = float(min(max(model_p, 0.0), 1.0))
    if a is None:
        return {"fv": fv, "raw_fv": raw_fv, "market_p": market_p, "ask": None,
                "edge": None, "raw_edge": None, "shrunk_by": None}
    edge = fv - a - fee_per_ct
    raw_edge = raw_fv - a - fee_per_ct
    return {
        "fv": round(fv, 4), "raw_fv": round(raw_fv, 4),
        "market_p": None if market_p is None else round(float(market_p), 4),
        "ask": round(a, 4), "edge": round(edge, 4), "raw_edge": round(raw_edge, 4),
        "shrunk_by": round(raw_edge - edge, 4),  # how much the correction ate
    }


def _logloss(p: np.ndarray, y: np.ndarray) -> float:
    p = np.clip(p, 1e-9, 1 - 1e-9)
    return float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))


def fit_blend_weight(model_ps: Iterable[float], market_ps: Iterable[float],
                     outcomes: Iterable[int],
                     grid: Optional[Iterable[float]] = None) -> dict:
    """
    Pick the blend weight w in [0,1] that minimises out-of-sample log loss on
    paired (model_p, market_p, realized 0/1) rows. w=1 is pure model, w=0 pure
    market. Returns {'w_star', 'table': [(w, logloss)...], 'n'}.

    Use this once the live book + scorecard have accumulated enough settled,
    quoted legs (model fair value, market mid at entry, win/lose). Until then,
    keep DEFAULT_BLEND_W.
    """
    m = np.asarray(list(model_ps), dtype=float)
    k = np.asarray(list(market_ps), dtype=float)
    y = np.asarray(list(outcomes), dtype=float)
    if grid is None:
        grid = np.round(np.linspace(0.0, 1.0, 21), 3)
    table = []
    for w in grid:
        ll = _logloss(w * m + (1 - w) * k, y)
        table.append((float(w), round(ll, 5)))
    w_star = min(table, key=lambda t: t[1])[0]
    return {"w_star": w_star, "table": table, "n": int(len(y))}


def _selftest() -> int:
    ok = True

    # devig: symmetric spread around 0.50 -> 0.50
    d = devig_yes(52, 50)   # yes_ask .52, no_ask .50 => yes_bid .50, mid .51
    assert d is not None and abs(d - 0.51) < 1e-6, d

    # devig: one-sided fallback
    assert abs(devig_yes(45, None) - 0.45) < 1e-9
    assert abs(devig_yes(None, 70) - 0.30) < 1e-9

    # blend halves the gap to market
    assert abs(blend(0.60, 0.40, 0.5) - 0.50) < 1e-9
    assert abs(blend(0.60, 0.40, 1.0) - 0.60) < 1e-9   # pure model
    assert abs(blend(0.60, 0.40, 0.0) - 0.40) < 1e-9   # pure market

    # corrected_edge shrinks an over-claimed edge toward the market
    ce = corrected_edge(model_p=0.55, market_p=0.45, ask=0.45, fee_per_ct=0.0, w=0.5)
    assert ce["raw_edge"] > ce["edge"] > 0, ce        # model said +10c, corrected +5c
    assert abs(ce["shrunk_by"] - 0.05) < 1e-6, ce

    # fit_blend_weight recovers a market-favouring weight when the market is the
    # better-calibrated estimator (the documented tail failure).
    rng = np.random.default_rng(0)
    n = 4000
    true_p = rng.uniform(0.05, 0.95, n)
    y = (rng.uniform(size=n) < true_p).astype(int)
    market = np.clip(true_p + rng.normal(0, 0.03, n), 0.01, 0.99)   # nearly true
    # model overstates the unlikely tail: push low probs up, high probs down
    model = np.clip(true_p + 0.12 * (0.5 - true_p) * 2, 0.01, 0.99)
    fit = fit_blend_weight(model, market, y)
    assert fit["w_star"] <= 0.5, fit   # should lean on the market
    print(f"[selftest] fit w* = {fit['w_star']} (<=0.5, leans market)  n={fit['n']}")

    print("[selftest] all assertions passed" if ok else "[selftest] FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        raise SystemExit(_selftest())
    print(__doc__)
