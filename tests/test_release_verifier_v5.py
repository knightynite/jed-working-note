from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "verify_release_v5.py"


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_module():
    spec = importlib.util.spec_from_file_location("jed_v5_release_verifier", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load verifier")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ReleaseVerifierNegativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.module = load_module()

    def test_exact_gate_requirements_pass(self) -> None:
        self.module.verify_publication_gates(sorted(self.module.REQUIRED_GATES))

    def test_gate_map_fails(self) -> None:
        with self.assertRaises(RuntimeError):
            self.module.verify_publication_gates({})

    def test_missing_gate_fails(self) -> None:
        gates = sorted(self.module.REQUIRED_GATES)[:-1]
        with self.assertRaises(RuntimeError):
            self.module.verify_publication_gates(gates)

    def test_integration_rejects_detached_artifact(self) -> None:
        files = {"PAYLOAD_MANIFEST.json": Path("manifest"),
                 "AUTHOR_ATTESTATION.json": Path("author")}
        with self.assertRaises(RuntimeError):
            self.module.verify_detached_mode(files, False)

    def test_release_requires_exact_detached_set(self) -> None:
        files = {"PAYLOAD_MANIFEST.json": Path("manifest")}
        with self.assertRaises(RuntimeError):
            self.module.verify_detached_mode(files, True)

    def test_python_attack_content_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "payload.py"
            path.write_bytes(b"x = '" + b"http" + b".post" + b"'\n")
            with self.assertRaises(RuntimeError):
                self.module.verify_safety({"payload.py": path})

    def test_forward_slash_personal_path_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "note.md"
            path.write_text("C:" + "/Users/" + "person/file", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                self.module.verify_safety({"note.md": path})

    def test_svg_event_handler_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "figure.svg"
            path.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg" on' +
                'click = "alert(1)"><rect width="1" height="1"/></svg>',
                encoding="utf-8",
            )
            with self.assertRaises(RuntimeError):
                self.module.verify_safety({"figure.svg": path})

    def test_svg_foreign_object_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "figure.svg"
            path.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg"><foreign' +
                'Object><div>bad</div></foreignObject></svg>',
                encoding="utf-8",
            )
            with self.assertRaises(RuntimeError):
                self.module.verify_safety({"figure.svg": path})

    def test_svg_external_css_url_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "figure.svg"
            path.write_text(
                '<svg xmlns="http://www.w3.org/2000/svg"><style>' +
                '.x{fill:url(' + 'https:' + '//' + 'example.invalid/x)}</style>' +
                '<rect class="x" width="1" height="1"/></svg>',
                encoding="utf-8",
            )
            with self.assertRaises(RuntimeError):
                self.module.verify_safety({"figure.svg": path})

    def test_invalid_calendar_timestamp_fails(self) -> None:
        with self.assertRaises(RuntimeError):
            self.module.utc_timestamp("2026-99-99T99:99:99Z", "timestamp")

    def test_duplicate_json_key_fails(self) -> None:
        with self.assertRaises(RuntimeError):
            self.module.unique_pairs([("status", "PASS"), ("status", "HOLD")])

    def test_empty_release_audit_receipt_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "audit.json"
            path.write_text("{}\n", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                self.module.verify_release_audit(
                    path, "Review Pass A", "0" * 64, "1" * 64
                )

    def test_campaign_recheck_wrong_hash_fails(self) -> None:
        terminal = {
            "campaign_expected_summary_sha256": digest(
                ROOT / "EXPECTED_CAMPAIGN_SUMMARY.json"
            ),
            "campaign_provenance_sha256": digest(
                ROOT / "evidence" / "campaign_provenance.json"
            ),
            "campaign_public_scores_sha256": "0" * 64,
        }
        with self.assertRaises(RuntimeError):
            self.module.verify_campaign_recheck_bindings(terminal)

    def test_preview_binding_includes_all_embedded_figures(self) -> None:
        self.assertEqual(
            set(self.module.expected_preview_figures()),
            {
                "figures/campaign_repeat_correction.svg",
                "figures/equal_score_different_decision.svg",
                "figures/error_first_flow.svg",
            },
        )

    def test_mechanics_capture_traversal_fails(self) -> None:
        with self.assertRaises(RuntimeError):
            self.module.resolve_payload_artifact("../capture.json", "test capture")

    def release_times(self):
        parse = lambda value: self.module.utc_timestamp(value, "test timestamp")
        payload = {
            "mechanics_capture": parse("2026-09-02T00:01:00Z"),
            "mechanics": parse("2026-09-02T00:01:00Z"),
            "preview": parse("2026-09-02T00:02:00Z"),
            "terminal": parse("2026-09-02T00:01:00Z"),
        }
        return payload, [
            parse("2026-09-02T00:03:00Z"),
            parse("2026-09-02T00:04:00Z"),
            parse("2026-09-02T00:04:00Z"),
            parse("2026-09-02T00:04:00Z"),
            parse("2026-09-02T00:05:00Z"),
            parse("2026-09-02T00:06:00Z"),
            parse("2026-09-02T00:07:00Z"),
        ]

    def test_valid_release_timestamp_chain_passes(self) -> None:
        payload, times = self.release_times()
        self.module.verify_release_timestamp_bounds(payload, *times)

    def test_preclose_terminal_timestamp_fails(self) -> None:
        payload, times = self.release_times()
        payload["terminal"] = self.module.utc_timestamp(
            "2026-09-01T10:10:00Z", "test preclose timestamp"
        )
        with self.assertRaises(RuntimeError):
            self.module.verify_release_timestamp_bounds(payload, *times)

    def test_preclose_mechanics_capture_timestamp_fails(self) -> None:
        payload, times = self.release_times()
        payload["mechanics_capture"] = self.module.utc_timestamp(
            "2026-09-01T10:10:00Z", "test stale mechanics capture timestamp"
        )
        with self.assertRaises(RuntimeError):
            self.module.verify_release_timestamp_bounds(payload, *times)

    def test_delayed_mechanics_receipt_fails(self) -> None:
        payload, times = self.release_times()
        payload["mechanics"] = self.module.utc_timestamp(
            "2026-09-02T00:20:00Z", "test delayed mechanics receipt"
        )
        payload["preview"] = self.module.utc_timestamp(
            "2026-09-02T00:21:00Z", "test post-mechanics preview"
        )
        times[6] = self.module.utc_timestamp(
            "2026-09-02T00:22:00Z", "test verification time"
        )
        with self.assertRaises(RuntimeError):
            self.module.verify_release_timestamp_bounds(payload, *times)

    def test_stale_mechanics_capture_at_approval_fails(self) -> None:
        payload, times = self.release_times()
        times[4] = self.module.utc_timestamp(
            "2026-09-08T00:00:00Z", "test stale-capture approval"
        )
        times[5] = self.module.utc_timestamp(
            "2026-09-08T00:01:00Z", "test stale-capture envelope"
        )
        times[6] = self.module.utc_timestamp(
            "2026-09-08T00:02:00Z", "test verification time"
        )
        with self.assertRaises(RuntimeError):
            self.module.verify_release_timestamp_bounds(payload, *times)

    def test_preterminal_preview_fails(self) -> None:
        payload, times = self.release_times()
        payload["preview"] = self.module.utc_timestamp(
            "2026-09-01T23:00:00Z", "test preterminal preview timestamp"
        )
        with self.assertRaises(RuntimeError):
            self.module.verify_release_timestamp_bounds(payload, *times)

    def test_premechanics_preview_fails(self) -> None:
        payload, times = self.release_times()
        payload["mechanics"] = self.module.utc_timestamp(
            "2026-09-02T00:02:00Z", "test mechanics receipt"
        )
        payload["preview"] = self.module.utc_timestamp(
            "2026-09-02T00:01:30Z", "test premechanics preview"
        )
        with self.assertRaises(RuntimeError):
            self.module.verify_release_timestamp_bounds(payload, *times)

    def test_post_deadline_envelope_fails(self) -> None:
        payload, times = self.release_times()
        times[4] = self.module.utc_timestamp(
            "2026-09-09T00:00:00Z", "test late approval"
        )
        times[5] = self.module.utc_timestamp(
            "2026-09-09T00:01:00Z", "test late envelope"
        )
        times[6] = self.module.utc_timestamp(
            "2026-09-09T00:02:00Z", "test verification time"
        )
        with self.assertRaises(RuntimeError):
            self.module.verify_release_timestamp_bounds(payload, *times)

    def test_stale_approval_envelope_fails(self) -> None:
        payload, times = self.release_times()
        times[5] = self.module.utc_timestamp(
            "2026-09-02T00:20:00Z", "test stale approval envelope"
        )
        times[6] = self.module.utc_timestamp(
            "2026-09-02T00:21:00Z", "test verification time"
        )
        with self.assertRaises(RuntimeError):
            self.module.verify_release_timestamp_bounds(payload, *times)

    def test_future_receipt_timestamp_fails(self) -> None:
        payload, times = self.release_times()
        times[6] = self.module.utc_timestamp(
            "2026-09-01T23:59:00Z", "test early verification time"
        )
        with self.assertRaises(RuntimeError):
            self.module.verify_release_timestamp_bounds(payload, *times)

    def test_complete_release_contract_passes(self) -> None:
        """Exercise the positive detached-record DAG without invoking the CLI recursively."""
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "release"
            shutil.copytree(ROOT, fixture)
            globals_to_rebind = (
                "ROOT", "MANIFEST", "WORKBENCH", "EXPECTED", "REPRODUCER", "TESTS",
                "BOUNDARY", "CLAIMS", "SOURCES", "RIGHTS", "NOTE", "RELATED",
                "CAMPAIGN_EXPECTED", "CAMPAIGN_REPRODUCER", "CAMPAIGN_PROVENANCE",
                "GENERATOR", "WORKBENCH_MANIFEST", "RELEASE_TESTS", "RECEIPTS",
            )
            original = {name: getattr(self.module, name) for name in globals_to_rebind}
            original_datetime = self.module.datetime
            try:
                self.module.ROOT = fixture
                self.module.MANIFEST = fixture / "PAYLOAD_MANIFEST.json"
                self.module.WORKBENCH = fixture / "synthetic_workbench"
                self.module.EXPECTED = fixture / "synthetic_workbench" / "EXPECTED_RESULTS.json"
                self.module.REPRODUCER = fixture / "synthetic_workbench" / "scripts" / "reproduce.py"
                self.module.TESTS = fixture / "synthetic_workbench" / "tests"
                self.module.BOUNDARY = fixture / "evidence" / "release_boundary.json"
                self.module.CLAIMS = fixture / "evidence" / "claim_ledger.json"
                self.module.SOURCES = fixture / "evidence" / "official_source_index.json"
                self.module.RIGHTS = fixture / "evidence" / "source_and_rights_register.json"
                self.module.NOTE = fixture / "publication" / "WORKING_NOTE_V5_DRAFT.md"
                self.module.RELATED = fixture / "publication" / "related_work.json"
                self.module.CAMPAIGN_EXPECTED = fixture / "EXPECTED_CAMPAIGN_SUMMARY.json"
                self.module.CAMPAIGN_REPRODUCER = fixture / "scripts" / "reproduce_campaign_correction.py"
                self.module.CAMPAIGN_PROVENANCE = fixture / "evidence" / "campaign_provenance.json"
                self.module.GENERATOR = fixture / "scripts" / "generate_payload_manifest_v5.py"
                self.module.WORKBENCH_MANIFEST = fixture / "synthetic_workbench" / "WORKBENCH_MANIFEST.json"
                self.module.RELEASE_TESTS = fixture / "tests"
                self.module.RECEIPTS = {
                    "independent_audit_a_sha256": fixture / "INDEPENDENT_AUDIT_A.json",
                    "payload_safety_receipt_sha256": fixture / "PAYLOAD_SAFETY_RECEIPT.json",
                    "official_mechanics_receipt_sha256": fixture / "evidence" / "receipts" / "official_working_note_mechanics_receipt.json",
                    "rendered_preview_receipt_sha256": fixture / "evidence" / "receipts" / "rendered_preview_receipt.json",
                    "independent_audit_b_sha256": fixture / "INDEPENDENT_AUDIT_B.json",
                    "terminal_facts_receipt_sha256": fixture / "evidence" / "receipts" / "terminal_facts_receipt.json",
                }

                boundary = json.loads(self.module.BOUNDARY.read_text(encoding="utf-8"))
                boundary["status"] = "release_candidate"
                boundary["synthetic_workbench"]["first_acceptance_disposition"] = "FIRE release audit"
                boundary["synthetic_workbench"]["second_acceptance_disposition"] = "FIRE release audit"
                write_json(self.module.BOUNDARY, boundary)

                claims = json.loads(self.module.CLAIMS.read_text(encoding="utf-8"))
                claims["status"] = "final"
                for row in claims["claims"]:
                    row["rights_status"] = row["rights_status"].replace(
                        "owner attestation and publication eligibility pending", "owner attested"
                    ).replace("owner attestation pending", "owner attested").replace(
                        "must be attested before release", "owner attested"
                    )
                write_json(self.module.CLAIMS, claims)

                rights = json.loads(self.module.RIGHTS.read_text(encoding="utf-8"))
                rights["release_status"] = "owner_attested"
                rights["required_before_release"] = []
                for row in rights["items"]:
                    row["rights_basis"] = row["rights_basis"].replace(
                        "must be attested before release", "is owner attested"
                    )
                write_json(self.module.RIGHTS, rights)

                related = json.loads(self.module.RELATED.read_text(encoding="utf-8"))
                related["status"] = "final_proposition_review_and_link_check_complete"
                for row in related["entries"]:
                    if row["id"] not in {
                        "CONSORT-2025", "JED-Xander", "JED-Radiant",
                        "JED-Pilkwang", "JED-Cleanor", "JED-oNanachii",
                    }:
                        row["review_status"] = "full_text_reviewed"
                write_json(self.module.RELATED, related)

                provenance = json.loads(
                    self.module.CAMPAIGN_PROVENANCE.read_text(encoding="utf-8")
                )
                provenance["status"] = "author_declared_source_hash_record_manifest_bound"
                provenance["assertion_basis"] = (
                    "participant-authored source identities and campaign record; "
                    "manifest-bound author declaration"
                )
                write_json(self.module.CAMPAIGN_PROVENANCE, provenance)

                note_text = self.module.NOTE.read_text(encoding="utf-8").replace(
                    "**Status:** integration candidate; competition closed 2026-09-01T23:59:00Z  ",
                    "**Status:** final release candidate  ",
                ).replace(
                    "**Author/team attribution:** AL Najafi (solo)  ",
                    "**Author:** Test Author  \n**Team:** Test Team  ",
                )
                self.module.NOTE.write_text(note_text, encoding="utf-8")
                (fixture / "README.md").write_text(
                    "# Final release fixture\n\nAll declared release evidence is bound.\n",
                    encoding="utf-8",
                )

                sources = {
                    row["id"]: row for row in
                    json.loads(self.module.SOURCES.read_text(encoding="utf-8"))["sources"]
                }
                mechanics_capture = (
                    fixture / "evidence" / "receipts" /
                    "official_working_note_mechanics_capture.json"
                )
                write_json(mechanics_capture, {
                    "capture_method": "signed_in_ui_plus_official_public_pages",
                    "captured_at_utc": "2026-09-02T00:01:00Z",
                    "nonclaims": self.module.MECHANICS_NONCLAIMS,
                    "observed_precedent_urls": [
                        "https://www.kaggle.com/writeups/canqiang/the-scored-attack-surface-collapses-to-a-single-pr",
                        "https://www.kaggle.com/competitions/ai-agent-security-multi-step-tool-attacks/discussion/727895",
                    ],
                    "official_observations": {
                        "award_count": 2,
                        "award_usd_each": 2500,
                        "criteria": self.module.WORKING_NOTE_CRITERIA,
                        "deadline_utc": self.module.WORKING_NOTE_DEADLINE_UTC,
                        "explicit_jed_submission_channel_present": False,
                    },
                    "official_urls": {
                        "competition": "https://www.kaggle.com/competitions/ai-agent-security-multi-step-tool-attacks",
                        "criteria": sources["Official-Working-Note-Criteria"]["url"],
                        "kaggle_competitions_documentation": "https://www.kaggle.com/docs/competitions",
                    },
                    "schema": "jed-working-note-v5-official-mechanics-live-capture-v2",
                    "selected_route": {
                        "eligibility_uncertainty_disclosed": True,
                        "official_channel_status": "UNSPECIFIED_IN_CURRENT_JED_MATERIAL",
                        "ordered_publication_actions": self.module.PUBLICATION_ACTIONS,
                        "organizer_confirmed_channel": False,
                        "partial_completion_policy": self.module.PARTIAL_COMPLETION_POLICY,
                        "publication_channel": "Public Kaggle Project Writeup, then the writeup link shared on the host award thread",
                        "redundant_self_contained_discussion": True,
                    },
                    "signed_in_ui_observations": {
                        "competition_new_writeup_action_present": False,
                        "competition_submit_writeup_control_present": False,
                        "competition_track_selector_present": False,
                        "competition_writeups_tab_present": False,
                        "discussion_new_topic_action_present": True,
                        "profile_new_project_writeup_action_present": True,
                        "signed_in": True,
                    },
                    "status": "PASS",
                })
                write_json(self.module.RECEIPTS["official_mechanics_receipt_sha256"], {
                    "capture_artifact": {
                        "bytes": mechanics_capture.stat().st_size,
                        "path": "evidence/receipts/official_working_note_mechanics_capture.json",
                        "sha256": digest(mechanics_capture),
                    },
                    "checked_at_utc": "2026-09-02T00:01:00Z",
                    "checker_public_name": "Test Checker",
                    "eligibility_uncertainty_disclosed": True,
                    "judging_criteria_verified": True,
                    "official_channel_status": "UNSPECIFIED_IN_CURRENT_JED_MATERIAL",
                    "official_source_id": "Official-Working-Note-Criteria",
                    "ordered_publication_actions": self.module.PUBLICATION_ACTIONS,
                    "partial_completion_policy": self.module.PARTIAL_COMPLETION_POLICY,
                    "schema": "jed-working-note-v5-official-mechanics-receipt-v3",
                    "selected_publication_route": "Public Kaggle Project Writeup, then the writeup link shared on the host award thread",
                    "status": "PASS",
                    "working_note_deadline_utc": self.module.WORKING_NOTE_DEADLINE_UTC,
                })
                write_json(self.module.RECEIPTS["terminal_facts_receipt_sha256"], {
                    "campaign_expected_summary_sha256": digest(
                        self.module.CAMPAIGN_EXPECTED
                    ),
                    "campaign_family_post_close_rechecked": True,
                    "campaign_family_recheck_summary": "No later same-family draw was omitted.",
                    "campaign_provenance_sha256": digest(
                        self.module.CAMPAIGN_PROVENANCE
                    ),
                    "campaign_public_scores_sha256": digest(
                        fixture / "data" / "campaign_public_scores.json"
                    ),
                    "captured_at_utc": "2026-09-02T00:01:00Z",
                    "capturer_public_name": "Test Capturer",
                    "competition_closed": True,
                    "final_submission_deadline_utc": self.module.FINAL_SUBMISSION_DEADLINE_UTC,
                    "live_capture_bytes": 1,
                    "live_capture_sha256": "2" * 64,
                    "live_url": sources["Official-Timeline"]["url"],
                    "official_source_id": "Official-Timeline",
                    "same_family_released_sequence_complete": True,
                    "schema": "jed-working-note-v5-terminal-facts-receipt-v1",
                    "status": "PASS",
                    "terminal_fact_summary": "Competition closed; final state captured.",
                    "terminal_facts_verified": True,
                })
                write_json(self.module.RECEIPTS["rendered_preview_receipt_sha256"], {
                    "accessibility_reviewed": True,
                    "figure_sha256": {
                        "figures/campaign_repeat_correction.svg": digest(fixture / "figures" / "campaign_repeat_correction.svg"),
                        "figures/equal_score_different_decision.svg": digest(fixture / "figures" / "equal_score_different_decision.svg"),
                        "figures/error_first_flow.svg": digest(fixture / "figures" / "error_first_flow.svg"),
                    },
                    "links_reviewed": True,
                    "partial_completion_policy": self.module.PARTIAL_COMPLETION_POLICY,
                    "previewed_publication_actions": self.module.PUBLICATION_ACTIONS,
                    "publication_channel": "Public Kaggle Project Writeup, then the writeup link shared on the host award thread",
                    "rendered_artifact_bytes": 1,
                    "rendered_artifact_sha256": "3" * 64,
                    "rendered_format": "pdf",
                    "rendered_surface_count": 2,
                    "reviewed_at_utc": "2026-09-02T00:02:00Z",
                    "reviewer_public_name": "Test Reviewer",
                    "schema": "jed-working-note-v5-rendered-preview-receipt-v2",
                    "source_note_sha256": digest(self.module.NOTE),
                    "status": "PASS",
                    "visual_review_passed": True,
                })

                license_text = self.module.MIT_TEMPLATE.replace("<YEAR>", "2026").replace(
                    "<COPYRIGHT_HOLDER>", "Test Author"
                )
                (fixture / "LICENSE.txt").write_text(license_text, encoding="utf-8")
                generated = subprocess.run(
                    [sys.executable, "-I", "-B", str(self.module.GENERATOR),
                     "--status", "release", "--write"],
                    cwd=fixture, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                self.assertEqual(generated.returncode, 0, generated.stderr.decode())
                manifest = json.loads(self.module.MANIFEST.read_text(encoding="utf-8"))
                self.assertEqual(manifest["status"], "release-candidate")
                manifest_digest = digest(self.module.MANIFEST)
                author = {
                    "attested_at_utc": "2026-09-02T00:03:00Z",
                    "contribution_statement": "Sole fixture author.",
                    "copyright_holder": "Test Author",
                    "license_path": "LICENSE.txt",
                    "license_sha256": digest(fixture / "LICENSE.txt"),
                    "license_spdx_id": "MIT",
                    "license_template_sha256": hashlib.sha256(
                        self.module.MIT_TEMPLATE.encode("utf-8")
                    ).hexdigest(),
                    "ownership_and_rights_attested": True,
                    "payload_manifest_sha256": manifest_digest,
                    "partial_completion_policy": self.module.PARTIAL_COMPLETION_POLICY,
                    "public_name": "Test Author",
                    "publication_actions": self.module.PUBLICATION_ACTIONS,
                    "publication_channel": "Public Kaggle Project Writeup, then the writeup link shared on the host award thread",
                    "schema": "jed-working-note-v5-author-attestation-v2",
                    "status": "final",
                    "team_attribution": "Test Team",
                    "typed_attestation": "I attest that the ownership, rights, contribution, and attribution statements in this record are true.",
                }
                write_json(fixture / "AUTHOR_ATTESTATION.json", author)
                author_digest = digest(fixture / "AUTHOR_ATTESTATION.json")
                verifier_digest = digest(SCRIPT)
                for auditor, field in (("Review Pass A", "independent_audit_a_sha256"),
                                       ("Review Pass B", "independent_audit_b_sha256")):
                    write_json(self.module.RECEIPTS[field], {
                        "audited_at_utc": "2026-09-02T00:04:00Z",
                        "auditor": auditor,
                        "author_attestation_sha256": author_digest,
                        "disposition": "FIRE",
                        "p0_findings": [],
                        "p1_findings": [],
                        "payload_manifest_sha256": manifest_digest,
                        "schema": "jed-working-note-v5-release-audit-v1",
                        "scope": "payload_manifest_and_release_contract",
                        "status": "PASS",
                        "verifier_sha256": verifier_digest,
                    })
                write_json(self.module.RECEIPTS["payload_safety_receipt_sha256"], {
                    "active_content_findings": [],
                    "credential_findings": [],
                    "manual_review_complete": True,
                    "manifest_file_count": manifest["payload_file_count"],
                    "manifested_bytes_scanned": sum(row["bytes"] for row in manifest["files"]),
                    "payload_manifest_sha256": manifest_digest,
                    "private_identifier_findings": [],
                    "reviewer_public_name": "Test Safety Reviewer",
                    "scanned_at_utc": "2026-09-02T00:04:00Z",
                    "schema": "jed-working-note-v5-payload-safety-receipt-v1",
                    "scope": "manifested_payload_only",
                    "status": "PASS",
                    "verifier_sha256": verifier_digest,
                })

                approval = {
                    "approved_at_utc": "2026-09-02T00:05:00Z",
                    "approved_for_one_release_transaction": True,
                    "approval_origin": "explicit_user_message_recorded_out_of_band",
                    "approver_public_name": "Test Owner",
                    "author_attestation_sha256": author_digest,
                    "authorized_publication_actions": self.module.PUBLICATION_ACTIONS,
                    "conversation_event_id": "test-event",
                    "license_sha256": digest(fixture / "LICENSE.txt"),
                    "partial_completion_policy": self.module.PARTIAL_COMPLETION_POLICY,
                    "payload_manifest_sha256": manifest_digest,
                    "publication_channel": "Public Kaggle Project Writeup, then the writeup link shared on the host award thread",
                    "schema": "jed-working-note-v5-owner-publication-approval-v2",
                    "single_use_nonce": "test_release_nonce_0001",
                    "status": "final",
                    "venue": "Kaggle",
                }
                for field, path in self.module.RECEIPTS.items():
                    approval[field] = digest(path)
                write_json(fixture / "OWNER_PUBLICATION_APPROVAL.json", approval)

                envelope = {
                    "authorized_publication_actions": self.module.PUBLICATION_ACTIONS,
                    "author_attestation_sha256": author_digest,
                    "created_at_utc": "2026-09-02T00:06:00Z",
                    "license_sha256": digest(fixture / "LICENSE.txt"),
                    "owner_approval_sha256": digest(fixture / "OWNER_PUBLICATION_APPROVAL.json"),
                    "partial_completion_policy": self.module.PARTIAL_COMPLETION_POLICY,
                    "payload_manifest_sha256": manifest_digest,
                    "publication_channel": "Public Kaggle Project Writeup, then the writeup link shared on the host award thread",
                    "schema": "jed-working-note-v5-release-envelope-v2",
                    "single_use_nonce": "test_release_nonce_0001",
                    "status": "final",
                }
                for field, path in self.module.RECEIPTS.items():
                    envelope[field] = digest(path)
                write_json(fixture / "RELEASE_ENVELOPE.json", envelope)

                class FixedDateTime(original_datetime):
                    @classmethod
                    def now(cls, tz=None):
                        value = cls(2026, 9, 2, 0, 7, 0,
                                    tzinfo=self.module.timezone.utc)
                        return value if tz is not None else value.replace(tzinfo=None)

                self.module.datetime = FixedDateTime
                files = self.module.actual_files()
                self.module.verify_detached_mode(files, True)
                self.module.verify_json_tree(files)
                validated_manifest = self.module.verify_manifest(files, True)
                self.module.verify_safety(files)
                self.module.verify_workbench(True)
                self.module.verify_campaign_correction(True)
                self.module.verify_evidence(files, True)
                result = self.module.verify_release_only(validated_manifest)
                self.assertEqual(result["release_envelope_sha256"], digest(
                    fixture / "RELEASE_ENVELOPE.json"
                ))
            finally:
                self.module.datetime = original_datetime
                for name, value in original.items():
                    setattr(self.module, name, value)


if __name__ == "__main__":
    unittest.main()
