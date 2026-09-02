from __future__ import annotations

import importlib.util
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "reproduce.py"
EXPECTED = ROOT / "EXPECTED_RESULTS.json"
MANIFEST = ROOT / "WORKBENCH_MANIFEST.json"


def load_module():
    spec = importlib.util.spec_from_file_location("jed_v5_synthetic_reproduce", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load reproduction module")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class SyntheticWorkbenchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()
        cls.result = cls.module.build()

    def test_expected_bytes(self) -> None:
        self.assertEqual(self.module.canonical(self.result), EXPECTED.read_bytes())

    def test_manifest(self) -> None:
        value = json.loads(MANIFEST.read_text(encoding="utf-8"))
        self.assertTrue(value["manifest_self_excluded"])
        self.assertEqual(value["payload_file_count"], len(value["files"]))
        observed = []
        for row in value["files"]:
            path = ROOT / Path(row["path"])
            body = path.read_bytes()
            observed.append({
                "path": row["path"],
                "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
            })
        self.assertEqual(observed, value["files"])

    def test_three_case_studies(self) -> None:
        self.assertTrue(self.result["artifact_identity"]["observations"][0]["metric_admissible"])
        self.assertFalse(self.result["artifact_identity"]["observations"][1]["metric_admissible"])
        self.assertEqual(self.result["intention_to_treat"]["completion_only_delta"]["numerator"], 4)
        self.assertEqual(self.result["intention_to_treat"]["intention_to_treat_delta"]["numerator"], 0)
        policy = self.result["policy_nonidentification"]
        self.assertEqual(policy["policy_count"], 8)
        self.assertGreaterEqual(len(policy["aggregate_equivalence_groups"]), 2)
        self.assertEqual(policy["decision_kinds"], ["ALLOW", "CONFIRM", "DENY", "SANITIZE"])
        self.assertEqual(len(policy["pairwise_witnesses"]), 28)
        self.assertEqual(set(policy["semantic_controls"]), {
            "negative_no_publish_case", "positive_allow_case",
            "provenance_negative_case", "provenance_positive_case",
            "sanitize_effect_case",
        })
        self.assertEqual(set(policy["policy_traces"]), set(self.module.POLICIES))

    def test_order_and_state_reset(self) -> None:
        value = json.loads((ROOT / "data" / "policy_cases.json").read_text(encoding="utf-8"))
        cases = value["cases"]
        for policy in self.module.POLICIES:
            with self.subTest(policy=policy):
                forward = [self.module.run_case(policy, case) for case in cases]
                reverse = list(reversed([
                    self.module.run_case(policy, case) for case in reversed(cases)
                ]))
                self.assertEqual(forward, reverse)

    def test_confirmed_paths(self) -> None:
        state = {"inspected_external": False, "published": 0}
        tagged = {"operation":"publish", "source":"local", "payload":"tagged",
                  "recipient":"sandbox", "user_confirmed":True}
        other = {"operation":"publish", "source":"local", "payload":"plain",
                 "recipient":"other", "user_confirmed":True}
        self.assertEqual(self.module.decide("confirm_tagged", tagged, state)[0], "ALLOW")
        self.assertEqual(self.module.decide("confirm_other_recipient", other, state)[0], "ALLOW")

    def test_one_byte_fixture_mutation_fails_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            copy = Path(directory) / "workbench"
            shutil.copytree(ROOT, copy)
            path = copy / "data" / "artifact_identity.json"
            original = path.read_bytes()
            mutated = original.replace(b'"metric": 18', b'"metric": 19', 1)
            self.assertNotEqual(original, mutated)
            path.write_bytes(mutated)
            completed = subprocess.run(
                [sys.executable, "-I", "-B", str(copy / "scripts" / "reproduce.py"),
                 "--check", str(EXPECTED)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            self.assertNotEqual(completed.returncode, 0)

    def test_semantic_mutants_fail_closed(self) -> None:
        original_decide = self.module.decide

        def baseline_allow(policy, event, state):
            return "ALLOW", dict(event)

        def baseline_deny(policy, event, state):
            return "DENY", None

        def wrong_sanitize(policy, event, state):
            if policy == "sanitize_tagged" and event["operation"] == "publish" and event["payload"] == "tagged":
                return "SANITIZE", dict(event)
            return original_decide(policy, event, state)

        mutants = {
            "baseline_allow": mock.patch.object(self.module, "decide", baseline_allow),
            "baseline_deny": mock.patch.object(self.module, "decide", baseline_deny),
            "wrong_action": mock.patch.object(self.module, "decide", wrong_sanitize),
            "witness_noop": mock.patch.object(self.module, "case_signature", lambda result: "0" * 64),
        }
        for name, patcher in mutants.items():
            with self.subTest(mutant=name), patcher:
                with self.assertRaises(RuntimeError):
                    self.module.policy_case()

    def test_injected_state_leak_fails_closed(self) -> None:
        states = {policy: {"inspected_external": False, "published": 0}
                  for policy in self.module.POLICIES}

        def leaked(policy, case):
            return self.module._run_case_with_state(policy, case, states[policy])

        with mock.patch.object(self.module, "run_case", leaked):
            with self.assertRaises(RuntimeError):
                self.module.policy_case()

    def test_stale_expected_result_fails_check(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            stale = Path(directory) / "stale.json"
            body = EXPECTED.read_bytes().replace(b"synthetic_only\":true",
                                                 b"synthetic_only\":false", 1)
            self.assertNotEqual(body, EXPECTED.read_bytes())
            stale.write_bytes(body)
            completed = subprocess.run(
                [sys.executable, "-I", "-B", str(SCRIPT), "--check", str(stale)],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            self.assertNotEqual(completed.returncode, 0)

    def test_normal_and_optimized_cli(self) -> None:
        commands = [
            [sys.executable, "-I", "-B", str(SCRIPT), "--check", str(EXPECTED)],
            [sys.executable, "-I", "-B", "-O", str(SCRIPT), "--check", str(EXPECTED)],
        ]
        outputs = []
        for command in commands:
            completed = subprocess.run(command, check=True, stdout=subprocess.PIPE,
                                       stderr=subprocess.PIPE)
            self.assertEqual(completed.stderr, b"")
            outputs.append(completed.stdout)
        self.assertEqual(outputs[0], outputs[1])
        self.assertEqual(outputs[0], EXPECTED.read_bytes())

    def test_public_safety_lexicon(self) -> None:
        joined = b"\n".join(path.read_bytes() for path in [
            ROOT / "data" / "artifact_identity.json",
            ROOT / "data" / "itt_trials.csv",
            ROOT / "data" / "policy_cases.json",
            SCRIPT,
        ]).lower()
        forbidden = [b"token=", b"secret.txt", b"http.post", b"private guardrail implementation",
                     b"authorization: bearer", b"begin private key", b"/home/", b"/users/"]
        for value in forbidden:
            self.assertNotIn(value, joined)
        patterns = [
            re.compile(rb"\b" + b"KGA" + b"T" + rb"[A-Za-z0-9_-]{8,}\b"),
            re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
            re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b"),
            re.compile(rb"(?i)\b[A-Z]:\\"),
        ]
        for pattern in patterns:
            self.assertIsNone(pattern.search(joined))


if __name__ == "__main__":
    unittest.main()
