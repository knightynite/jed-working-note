"""Deterministic, clean-room synthetic results for the JED Working Note V5.

This module models harmless fictional actions.  It does not import or emulate
the competition SDK and makes no claim about the inaccessible private policy.
"""

from __future__ import annotations

import argparse
import csv
from fractions import Fraction
import hashlib
import itertools
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data"
POLICIES = (
    "allow_all",
    "deny_tagged",
    "confirm_tagged",
    "sanitize_tagged",
    "provenance_gate",
    "recipient_gate",
    "confirm_other_recipient",
    "once_per_candidate",
)
DECISIONS = {"ALLOW", "DENY", "CONFIRM", "SANITIZE"}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def canonical(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, separators=(",", ":"),
                       sort_keys=True) + "\n").encode("utf-8")


def file_identity(path: Path) -> dict[str, Any]:
    body = path.read_bytes()
    return {"bytes": len(body), "sha256": hashlib.sha256(body).hexdigest()}


def load_json(path: Path) -> Any:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(type(value) in {dict, list}, f"unexpected JSON root: {path.name}")
    return value


def fraction_record(value: Fraction) -> dict[str, Any]:
    return {
        "denominator": value.denominator,
        "decimal": format(float(value), ".6f"),
        "numerator": value.numerator,
    }


def artifact_identity_case() -> dict[str, Any]:
    path = DATA / "artifact_identity.json"
    value = load_json(path)
    require(value["schema"] == "jed-v5-synthetic-artifact-identity-v1",
            "artifact schema")
    expected = value["expected_identity"]
    require(set(expected) == {"artifact_sha256", "parser_sha256", "fixture_sha256"},
            "artifact identity fields")
    observations = []
    for row in value["observations"]:
        observed = row["observed_identity"]
        mismatches = sorted(key for key in expected if observed.get(key) != expected[key])
        supported = not mismatches
        observations.append({
            "id": row["id"],
            "metric": row["metric"],
            "mismatched_identity_fields": mismatches,
            "metric_admissible": supported,
        })
    require([row["metric_admissible"] for row in observations] == [True, False],
            "artifact controls")
    require(observations[1]["metric"] > observations[0]["metric"],
            "drifted result must be superficially favorable")
    return {
        "fixture": file_identity(path),
        "observations": observations,
        "conclusion": (
            "The favorable synthetic metric is inadmissible after artifact identity drift."
        ),
    }


def itt_case() -> dict[str, Any]:
    path = DATA / "itt_trials.csv"
    with path.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    require(rows and set(rows[0]) == {"trial_id", "arm", "completed", "score"},
            "ITT columns")
    require(len(rows) == 16, "ITT trial count")
    parsed = [
        {
            "trial_id": row["trial_id"],
            "arm": row["arm"],
            "completed": int(row["completed"]),
            "score": int(row["score"]),
        }
        for row in rows
    ]
    require(len({row["trial_id"] for row in parsed}) == len(parsed), "ITT ids")
    require(all(row["completed"] in {0, 1} for row in parsed), "ITT completion")

    def mean(selected: list[dict[str, Any]]) -> Fraction:
        require(bool(selected), "empty ITT mean")
        return Fraction(sum(row["score"] for row in selected), len(selected))

    control = [row for row in parsed if row["arm"] == "control"]
    treatment = [row for row in parsed if row["arm"] == "treatment"]
    require(len(control) == len(treatment) == 8, "ITT arm balance")
    control_completed = [row for row in control if row["completed"]]
    treatment_completed = [row for row in treatment if row["completed"]]
    completion_delta = mean(treatment_completed) - mean(control_completed)
    itt_delta = mean(treatment) - mean(control)
    require(completion_delta == 4, "completion-only positive control")
    require(itt_delta == 0, "ITT null control")
    return {
        "fixture": file_identity(path),
        "trial_count": len(parsed),
        "completion_counts": {
            "control": len(control_completed),
            "treatment": len(treatment_completed),
        },
        "completion_only_delta": fraction_record(completion_delta),
        "intention_to_treat_delta": fraction_record(itt_delta),
        "conclusion": (
            "The synthetic completion-only gain disappears when every assigned trial is counted."
        ),
    }


def validate_event(event: dict[str, Any]) -> None:
    require(set(event) == {"operation", "source", "payload", "recipient", "user_confirmed"},
            "event fields")
    require(event["operation"] in {"inspect", "publish"}, "event operation")
    require(event["source"] in {"local", "external"}, "event source")
    require(event["payload"] in {"plain", "tagged"}, "event payload")
    require(event["recipient"] in {"sandbox", "other"}, "event recipient")
    require(type(event["user_confirmed"]) is bool, "event confirmation")


def decide(policy: str, event: dict[str, Any], state: dict[str, Any]) -> tuple[str, dict[str, Any] | None]:
    operation = event["operation"]
    if policy == "deny_tagged" and operation == "publish" and event["payload"] == "tagged":
        return "DENY", None
    if policy == "confirm_tagged" and operation == "publish" and event["payload"] == "tagged" and not event["user_confirmed"]:
        return "CONFIRM", None
    if policy == "sanitize_tagged" and operation == "publish" and event["payload"] == "tagged":
        executed = dict(event)
        executed["payload"] = "plain"
        return "SANITIZE", executed
    if policy == "provenance_gate" and operation == "publish" and not state["inspected_external"]:
        return "DENY", None
    if policy == "recipient_gate" and operation == "publish" and event["recipient"] != "sandbox":
        return "DENY", None
    if policy == "confirm_other_recipient" and operation == "publish" and event["recipient"] != "sandbox" and not event["user_confirmed"]:
        return "CONFIRM", None
    if policy == "once_per_candidate" and operation == "publish" and state["published"] >= 1:
        return "DENY", None
    return "ALLOW", dict(event)


def _run_case_with_state(policy: str, case: dict[str, Any],
                         state: dict[str, Any]) -> dict[str, Any]:
    trace = []
    points = 0
    cells: set[str] = set()
    for proposed in case["events"]:
        validate_event(proposed)
        decision, executed = decide(policy, proposed, state)
        require(decision in DECISIONS, "decision kind")
        if executed is not None:
            if executed["operation"] == "inspect" and executed["source"] == "external":
                state["inspected_external"] = True
            if executed["operation"] == "publish":
                state["published"] += 1
                points += 5 if executed["payload"] == "tagged" else 2
                cell = "|".join((executed["operation"], executed["payload"],
                                 executed["recipient"]))
                cells.add(cell)
                effect = f"published:{executed['payload']}:{executed['recipient']}"
            else:
                cell = None
                effect = f"inspected:{executed['source']}"
        else:
            cell = None
            effect = "not_executed"
        trace.append({
            "cell": cell,
            "decision": decision,
            "effect": effect,
            "executed": executed,
            "proposed": proposed,
        })
    return {
        "case_id": case["id"],
        "points": points,
        "cells": sorted(cells),
        "trace": trace,
    }


def run_case(policy: str, case: dict[str, Any]) -> dict[str, Any]:
    return _run_case_with_state(
        policy,
        case,
        {"inspected_external": False, "published": 0},
    )


def case_signature(result: dict[str, Any]) -> str:
    return hashlib.sha256(canonical(result)).hexdigest()


def minimal_distinguishing_cases(policy_results: dict[str, list[dict[str, Any]]],
                                 case_ids: list[str]) -> list[str]:
    for count in range(1, len(case_ids) + 1):
        for indexes in itertools.combinations(range(len(case_ids)), count):
            signatures = []
            for policy in POLICIES:
                signatures.append(tuple(case_signature(policy_results[policy][index])
                                        for index in indexes))
            if len(set(signatures)) == len(POLICIES):
                return [case_ids[index] for index in indexes]
    raise RuntimeError("declared policies are not pairwise distinguishable")


def policy_case() -> dict[str, Any]:
    path = DATA / "policy_cases.json"
    value = load_json(path)
    require(value["schema"] == "jed-v5-synthetic-policy-cases-v1", "policy schema")
    cases = value["cases"]
    case_ids = [case["id"] for case in cases]
    require(len(cases) >= 6 and len(case_ids) == len(set(case_ids)), "policy case ids")
    require(all(case["events"] for case in cases), "empty policy case")
    require(all(type(case.get("control")) is str and case["control"] for case in cases),
            "unlabeled semantic control")
    for case in cases:
        for event in case["events"]:
            validate_event(event)

    results = {policy: [run_case(policy, case) for case in cases] for policy in POLICIES}
    reverse_results = {
        policy: list(reversed([run_case(policy, case) for case in reversed(cases)]))
        for policy in POLICIES
    }
    require(results == reverse_results, "case order or policy state leakage")
    summaries = []
    score_groups: dict[int, list[str]] = {}
    decisions_seen: set[str] = set()
    for policy in POLICIES:
        rows = results[policy]
        points = sum(row["points"] for row in rows)
        cells = sorted({cell for row in rows for cell in row["cells"]})
        aggregate = points + len(cells)
        signature = hashlib.sha256(canonical([
            case_signature(row) for row in rows
        ])).hexdigest()
        decisions_seen.update(item["decision"] for row in rows for item in row["trace"])
        summaries.append({
            "aggregate_score": aggregate,
            "decision_trace_sha256": signature,
            "policy": policy,
            "unique_cell_count": len(cells),
        })
        score_groups.setdefault(aggregate, []).append(policy)

    equivalent = [
        {"aggregate_score": score, "policies": sorted(policies)}
        for score, policies in sorted(score_groups.items())
        if len(policies) > 1
    ]
    equivalent_sets = {frozenset(row["policies"]) for row in equivalent}
    require({
        frozenset(("confirm_tagged", "deny_tagged")),
        frozenset(("confirm_other_recipient", "recipient_gate")),
    } <= equivalent_sets, "required aggregate-equivalent policy pairs missing")
    require(decisions_seen == DECISIONS, "decision-kind coverage")
    require(len({row["decision_trace_sha256"] for row in summaries}) == len(POLICIES),
            "policy trace collision")
    minimal = minimal_distinguishing_cases(results, case_ids)

    by_id = {case_id: index for index, case_id in enumerate(case_ids)}
    positive = results["allow_all"][by_id["plain_local_publish"]]
    negative_rows = [results[policy][by_id["inspect_only"]] for policy in POLICIES]
    provenance_positive = results["provenance_gate"][by_id["inspect_then_publish"]]
    provenance_negative = results["provenance_gate"][by_id["plain_local_publish"]]
    sanitize_control = results["sanitize_tagged"][by_id["tagged_local_publish"]]
    require(positive["points"] == 2 and positive["trace"][0]["decision"] == "ALLOW",
            "positive allow control")
    require(all(row["points"] == 0 and row["cells"] == [] for row in negative_rows),
            "negative no-publish control")
    require(provenance_positive["points"] == 2 and
            provenance_positive["trace"][-1]["decision"] == "ALLOW",
            "provenance positive control")
    require(provenance_negative["points"] == 0 and
            provenance_negative["trace"][0]["decision"] == "DENY",
            "provenance negative control")
    require(sanitize_control["trace"][0]["decision"] == "SANITIZE" and
            sanitize_control["trace"][0]["executed"]["payload"] == "plain" and
            sanitize_control["trace"][0]["effect"] == "published:plain:sandbox",
            "sanitize effect control")

    witnesses = []
    for left_index, left in enumerate(POLICIES):
        for right in POLICIES[left_index + 1:]:
            differing = [case_ids[index] for index in range(len(cases))
                         if case_signature(results[left][index]) !=
                         case_signature(results[right][index])]
            require(bool(differing), f"no witness: {left}/{right}")
            witness_index = by_id[differing[0]]
            witnesses.append({
                "first_witness": differing[0],
                "left": left,
                "left_trace_sha256": case_signature(results[left][witness_index]),
                "right": right,
                "right_trace_sha256": case_signature(results[right][witness_index]),
            })

    return {
        "fixture": file_identity(path),
        "case_count": len(cases),
        "policy_count": len(POLICIES),
        "decision_kinds": sorted(decisions_seen),
        "semantic_controls": {
            "negative_no_publish_case": "inspect_only",
            "positive_allow_case": "plain_local_publish",
            "provenance_negative_case": "plain_local_publish",
            "provenance_positive_case": "inspect_then_publish",
            "sanitize_effect_case": "tagged_local_publish",
        },
        "policy_summaries": summaries,
        "policy_traces": results,
        "aggregate_equivalence_groups": equivalent,
        "minimal_distinguishing_case_ids": minimal,
        "pairwise_witnesses": witnesses,
        "conclusion": (
            "Within the declared toy family, aggregate equality does not imply policy or trace equality."
        ),
        "nonclaim": "No competition private policy is identified or approximated.",
    }


def build() -> dict[str, Any]:
    return {
        "schema": "jed-working-note-v5-synthetic-workbench-results-v1",
        "artifact_identity": artifact_identity_case(),
        "intention_to_treat": itt_case(),
        "policy_nonidentification": policy_case(),
        "scope": {
            "competition_data_records": 0,
            "competitor_records": 0,
            "private_policy_claims": 0,
            "real_system_instructions": 0,
            "synthetic_only": True,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", type=Path)
    mode.add_argument("--write-expected", type=Path)
    args = parser.parse_args()
    rendered = canonical(build())
    if args.check is not None:
        expected = args.check.resolve().read_bytes()
        require(rendered == expected, "expected synthetic result drift")
    if args.write_expected is not None:
        args.write_expected.resolve().write_bytes(rendered)
    sys.stdout.buffer.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
