#!/usr/bin/env python3
"""Reproduce the bounded public repeat-family correction in the V5 note."""

from __future__ import annotations

import argparse
from decimal import Decimal, getcontext
from fractions import Fraction
import hashlib
import itertools
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "data" / "campaign_public_scores.json"


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def parse_scores(values: object) -> list[Fraction]:
    require(type(values) is list and values, "score list")
    result = []
    for value in values:
        require(type(value) is str, "score encoding")
        result.append(Fraction(Decimal(value)))
    return result


def mean(values: list[Fraction]) -> Fraction:
    return sum(values, Fraction(0)) / len(values)


def sample_variance(values: list[Fraction]) -> Fraction:
    center = mean(values)
    return sum((value - center) ** 2 for value in values) / (len(values) - 1)


def decimal_sqrt(value: Fraction) -> Decimal:
    getcontext().prec = 50
    return (Decimal(value.numerator) / Decimal(value.denominator)).sqrt()


def fixed(value: Fraction | Decimal, places: int = 6) -> str:
    if isinstance(value, Fraction):
        value = Decimal(value.numerator) / Decimal(value.denominator)
    return f"{value:.{places}f}"


def build() -> dict[str, object]:
    raw = json.loads(FIXTURE.read_text(encoding="utf-8"))
    require(raw["schema"] == "jed-working-note-v5-public-repeat-family-v1", "fixture schema")
    prior = parse_scores(raw["prior_scores"])
    fresh = parse_scores(raw["fresh_author_designated_batch"])
    require(len(prior) == 11 and len(fresh) == 4, "declared family sizes")
    combined = prior + fresh
    observed_mean = mean(fresh)
    combinations = list(itertools.combinations(combined, len(fresh)))
    lower_or_equal = sum(mean(list(group)) <= observed_mean for group in combinations)
    denominator = len(combinations)
    require((lower_or_equal, denominator) == (3, 1365), "exchangeability rank drift")

    leave_one_out = []
    for deleted_index in range(len(combined)):
        reduced = combined[:deleted_index] + combined[deleted_index + 1:]
        if deleted_index < len(prior):
            reduced_fresh = fresh
        else:
            fresh_index = deleted_index - len(prior)
            reduced_fresh = fresh[:fresh_index] + fresh[fresh_index + 1:]
        reduced_observed_mean = mean(reduced_fresh)
        reduced_combinations = itertools.combinations(reduced, len(reduced_fresh))
        reduced_favorable = sum(
            mean(list(group)) <= reduced_observed_mean for group in reduced_combinations
        )
        reduced_denominator = len(list(itertools.combinations(
            range(len(reduced)), len(reduced_fresh)
        )))
        leave_one_out.append(Fraction(reduced_favorable, reduced_denominator))
    minimum_loo = min(leave_one_out)
    maximum_loo = max(leave_one_out)
    require((minimum_loo, maximum_loo) == (Fraction(2, 1001), Fraction(3, 364)),
            "leave-one-out sensitivity drift")
    require(all(value < Fraction(1, 100) for value in leave_one_out),
            "leave-one-out threshold drift")
    return {
        "schema": "jed-working-note-v5-public-repeat-correction-result-v1",
        "fixture": {
            "bytes": FIXTURE.stat().st_size,
            "sha256": hashlib.sha256(FIXTURE.read_bytes()).hexdigest(),
        },
        "prior": {
            "n": len(prior),
            "mean": fixed(mean(prior)),
            "sample_sd": fixed(decimal_sqrt(sample_variance(prior))),
        },
        "fresh_author_designated_batch": {
            "n": len(fresh),
            "mean": fixed(observed_mean),
            "sample_sd": fixed(decimal_sqrt(sample_variance(fresh))),
        },
        "fresh_minus_prior_mean": fixed(observed_mean - mean(prior)),
        "exact_exchangeable_mean_rank": {
            "direction": "lower_or_equal",
            "favorable_allocations": lower_or_equal,
            "total_allocations": denominator,
            "fraction": f"{lower_or_equal}/{denominator}",
            "decimal": fixed(Fraction(lower_or_equal, denominator), 9),
        },
        "leave_one_out_descriptive_sensitivity": {
            "deletions": len(combined),
            "relabeling": "delete one observation and retain the surviving prior/fresh labels",
            "minimum_fraction": f"{minimum_loo.numerator}/{minimum_loo.denominator}",
            "maximum_fraction": f"{maximum_loo.numerator}/{maximum_loo.denominator}",
            "all_below_one_percent": True,
            "nonclaim": "Descriptive robustness only; this does not repair timing, multiplicity, dependence, heavy tails, or stationarity assumptions.",
        },
        "disposition": "Retire the stationary forecast; do not infer a causal mechanism.",
        "nonclaim": "This public repeat-family correction provides no private-policy or evaluator-change identification.",
    }


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True) + "\n").encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", type=Path)
    mode.add_argument("--write-expected", type=Path)
    args = parser.parse_args()
    rendered = canonical(build())
    if args.check is not None:
        require(args.check.resolve().read_bytes() == rendered, "campaign correction drift")
    if args.write_expected is not None:
        args.write_expected.resolve().write_bytes(rendered)
    sys.stdout.buffer.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
