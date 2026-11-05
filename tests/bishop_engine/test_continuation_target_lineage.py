"""Exact causal ownership evidence, not teacher-trade acceptance."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import random

from bishop.v2.structure import Range, _continuation_owners, analyze
from bishop.v2.types import Bar

T = datetime(2026, 1, 1, tzinfo=timezone.utc)


def row(ident="r", **changes):
    base = Range(ident, None, "BUY", "DEFINED", "origin", None,
                 "endpoint", None, 80, 120, T, T, ident + "v",
                 {"candidate_id": "candidate"})
    return replace(base, **changes)


def test_exact_turn_roles_and_all_ambiguous_owners_are_preserved():
    first, second = row(), row("child", protected_turn_id="endpoint", endpoint_turn_id="other")
    owners = _continuation_owners({"child": second, "r": first}, "endpoint", T)
    assert [o["range_id"] for o in owners] == ["child", "r"]
    assert owners[0]["reference_roles"] == ("protected_turn",)
    assert owners[1]["reference_roles"] == ("endpoint_turn",)
    assert owners[1]["range_version_id"] == "rv"
    assert _continuation_owners({"r": first}, "candidate", T)[0]["reference_roles"] == ("candidate_turn",)


def test_unrelated_future_and_broken_ranges_do_not_supply_ownership():
    active = {"r": row(), "future": row("future", available_at=T+timedelta(hours=1)),
              "broken": row("broken", status="BROKEN")}
    assert _continuation_owners(active, "unrelated", T) == ()
    assert [o["range_id"] for o in _continuation_owners(active, "endpoint", T)] == ["r"]


def test_emitted_ownership_is_causal_and_prefix_invariant():
    rng = random.Random(17)
    bars, price = [], 1000
    for i in range(100):
        close = price + rng.choice((-30, -20, -10, 10, 20, 30))
        bars.append(Bar("X", "H1", T+timedelta(hours=i), T+timedelta(hours=i+1),
                        price, max(price, close)+5, min(price, close)-5, close))
        price = close
    full = analyze(bars)
    owned = [e for e in full.events if e.details.get("continuation_range_owners")]
    assert owned
    for event in owned:
        assert event.scope_id is None
        prefix = analyze([b for b in bars if b.available_at <= event.available_at])
        same = next(e for e in prefix.events if e.id == event.id)
        assert same == event
        for owner in event.details["continuation_range_owners"]:
            version = next(r for r in prefix.ranges if r.version_id == owner["range_version_id"])
            assert version.available_at <= event.available_at
            assert event.reference_id in (version.protected_turn_id, version.endpoint_turn_id,
                                          version.details.get("candidate_id"))
            assert owner["reference_turn_id"] == event.reference_id


def test_initial_seed_does_not_claim_a_range_created_after_its_event():
    prices = (100, 120, 110, 115, 130)
    bars = [Bar("X", "H1", T+timedelta(hours=i), T+timedelta(hours=i+1),
                prices[max(0, i-1)], max(prices[max(0, i-1)], p)+1,
                min(prices[max(0, i-1)], p)-1, p) for i, p in enumerate(prices)]
    result = analyze(bars)
    assert result.ranges
    seed = next(e for e in result.events if e.id == result.ranges[0].details["seed_break_event_id"])
    assert seed.details["continuation_range_owners"] == ()
