#!/usr/bin/env python3
"""Fail-closed verifier for the JED Working Note V5 staging or release tree."""

from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any
import unicodedata
from urllib.parse import urlparse
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "PAYLOAD_MANIFEST.json"
WORKBENCH = ROOT / "synthetic_workbench"
EXPECTED = WORKBENCH / "EXPECTED_RESULTS.json"
REPRODUCER = WORKBENCH / "scripts" / "reproduce.py"
TESTS = WORKBENCH / "tests"
BOUNDARY = ROOT / "evidence" / "release_boundary.json"
CLAIMS = ROOT / "evidence" / "claim_ledger.json"
SOURCES = ROOT / "evidence" / "official_source_index.json"
RIGHTS = ROOT / "evidence" / "source_and_rights_register.json"
NOTE = ROOT / "publication" / "WORKING_NOTE_V5_DRAFT.md"
RELATED = ROOT / "publication" / "related_work.json"
CAMPAIGN_EXPECTED = ROOT / "EXPECTED_CAMPAIGN_SUMMARY.json"
CAMPAIGN_REPRODUCER = ROOT / "scripts" / "reproduce_campaign_correction.py"
CAMPAIGN_PROVENANCE = ROOT / "evidence" / "campaign_provenance.json"
GENERATOR = ROOT / "scripts" / "generate_payload_manifest_v5.py"
WORKBENCH_MANIFEST = WORKBENCH / "WORKBENCH_MANIFEST.json"
RELEASE_TESTS = ROOT / "tests"
DETACHED = {
    "PAYLOAD_MANIFEST.json",
    "RELEASE_ENVELOPE.json",
    "AUTHOR_ATTESTATION.json",
    "INDEPENDENT_AUDIT_A.json",
    "PAYLOAD_SAFETY_RECEIPT.json",
    "OWNER_PUBLICATION_APPROVAL.json",
    "INDEPENDENT_AUDIT_B.json",
}
ALLOWED_SUFFIXES = {".csv", ".json", ".md", ".py", ".svg", ".txt"}
ALLOWED_WEB_HOSTS = {
    "arxiv.org", "www.arxiv.org", "kaggle.com", "www.kaggle.com",
    "bmj.com", "www.bmj.com", "doi.org", "www.doi.org", "www.w3.org",
    "github.com", "www.github.com",
}
REQUIRED_GATES = {
    "author_team_contribution_approved",
    "current_working_note_mechanics_and_uncertainty_recorded",
    "independent_exact_release_audits_passed",
    "license_and_copyright_holder_selected",
    "owner_publication_approval_received",
    "payload_safety_scan_passed",
    "rendered_preview_reviewed",
    "rights_attestation_bound",
    "terminal_competition_facts_captured",
}
RECEIPTS = {
    "independent_audit_a_sha256": ROOT / "INDEPENDENT_AUDIT_A.json",
    "payload_safety_receipt_sha256": ROOT / "PAYLOAD_SAFETY_RECEIPT.json",
    "official_mechanics_receipt_sha256": ROOT / "evidence" / "receipts" / "official_working_note_mechanics_receipt.json",
    "rendered_preview_receipt_sha256": ROOT / "evidence" / "receipts" / "rendered_preview_receipt.json",
    "independent_audit_b_sha256": ROOT / "INDEPENDENT_AUDIT_B.json",
    "terminal_facts_receipt_sha256": ROOT / "evidence" / "receipts" / "terminal_facts_receipt.json",
}
MANIFEST_COMMON_NONCLAIMS = [
    "Content hashes establish identity, not authorship, correctness, or rights.",
    "The package does not identify the inaccessible competition private guardrail.",
]
MANIFEST_INTEGRATION_NONCLAIM = (
    "The package is not licensed, publication-authorized, or a terminal release."
)
MANIFEST_RELEASE_NONCLAIM = (
    "Mechanical release verification proves internal consistency only; it does not prove "
    "human identity, agent independence, signed approval, publication authority, or that "
    "an out-of-band publication action occurred."
)

MECHANICS_CAPTURE_RELATIVE = (
    "evidence/receipts/official_working_note_mechanics_capture.json"
)
WORKING_NOTE_CRITERIA = [
    "technical_clarity_and_reproducibility",
    "methodological_contribution",
    "security_insight",
    "usefulness_to_the_benchmark_community",
    "responsible_communication",
]
MECHANICS_NONCLAIMS = [
    "The JED official material may specify criteria and a deadline without specifying a dedicated submission channel.",
    "Observed participant practice and visible UI controls do not constitute organizer confirmation of eligibility.",
    "This capture records visible state and selected delivery mechanics; it does not prove organizer adjudication or award eligibility.",
]
# Official sources citable in the note body. Official-Evaluation is a dated local
# capture in the source index; Official-Evaluator-FAQ is a live host post cited by
# URL, quoted verbatim, and deliberately not presented as a local capture.
OFFICIAL_BODY_CITATIONS = {"Official-Evaluation", "Official-Evaluator-FAQ"}

PUBLICATION_ACTIONS = [
    "PUBLISH_PUBLIC_PROJECT_WRITEUP",
    "SHARE_WRITEUP_LINK_ON_HOST_AWARD_THREAD",
]
PUBLICATION_CHANNEL = (
    "Public Kaggle Project Writeup, then the writeup link shared on the host award thread"
)
PARTIAL_COMPLETION_POLICY = (
    "STOP_TRANSACTION_AFTER_FIRST_FAILED_OR_AMBIGUOUS_ACTION; "
    "NEVER_RETRY_OR_DUPLICATE_ANY_ATTEMPTED_ACTION; "
    "DO_NOT_EXECUTE_REMAINING_ACTIONS_UNDER_THIS_CONTRACT"
)
ACCEPTED_SEED_MANIFEST = {
    "bytes": 1547,
    "sha256": "57971eec6c8ee639af3f32190e38c28486110b67022ddc42ce95149dbb0a4a83",
}
ACCEPTED_WORKBENCH_CORE = {
    "EXPECTED_RESULTS.json": (36594, "8183055d5ae37a2ca5ae209aaa3b59dc31b9abd60a0ebeff5e0f0a2e28c2157b"),
    "data/artifact_identity.json": (1150, "20eb773bb3eb4ba7d062adb39300a095fc94e88cdae7b6b82c6181794814da44"),
    "data/itt_trials.csv": (285, "1d8cd4d3a96043a69387a3b308677a9d0816f865c6e2cc72790ad0f6942ac298"),
    "data/policy_cases.json": (1956, "9fb059ccd75d4081924953068afe7f60cdd53a33f010d6812ce94170bbf13c67"),
    "scripts/reproduce.py": (15738, "c8e8616739e76fccbd93c4138dabb52620ef8d458654ab0db76106a6a9b142aa"),
    "tests/test_reproduce.py": (8535, "3a45f7ebacd8dabd9699c9dab9415b41625ac608efc6d5a36d0a6fe4bd5ea54f"),
}
SVG_NS = "http://www.w3.org/2000/svg"
SVG_ALLOWED_ATTRIBUTES = {
    "svg": {"aria-labelledby", "height", "role", "viewBox", "width"},
    "title": {"id"},
    "desc": {"id"},
    "rect": {"class", "fill", "height", "rx", "stroke", "stroke-width", "width", "x", "y"},
    "style": set(),
    "defs": set(),
    "marker": {"id", "markerHeight", "markerUnits", "markerWidth", "orient", "refX", "refY"},
    "path": {"class", "d", "fill", "stroke", "stroke-width"},
    "text": {"class", "fill", "font-family", "font-size", "font-weight", "text-anchor", "x", "y"},
    "g": {"aria-label", "class", "id", "role", "transform"},
    "line": {"class", "stroke", "stroke-width", "x1", "x2", "y1", "y2"},
    "polyline": {"class", "fill", "points", "stroke", "stroke-width"},
    "polygon": {"class", "fill", "points", "stroke", "stroke-width"},
    "circle": {"class", "cx", "cy", "fill", "r", "stroke", "stroke-width"},
}
SVG_CSS_PROPERTIES = {
    "fill", "font-family", "font-size", "font-weight", "marker-end", "rx",
    "stroke", "stroke-width", "text-anchor",
}
MIT_TEMPLATE = """MIT License

Copyright (c) <YEAR> <COPYRIGHT_HOLDER>

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""
LICENSE_TEMPLATES = {"MIT": MIT_TEMPLATE}
FINAL_SUBMISSION_DEADLINE_UTC = "2026-09-01T23:59:00Z"
WORKING_NOTE_DEADLINE_UTC = "2026-09-08T23:59:00Z"
MAX_FUTURE_CLOCK_SKEW = timedelta(minutes=5)
MAX_MECHANICS_CAPTURE_RECEIPT_LAG = timedelta(minutes=10)
MAX_MECHANICS_CAPTURE_APPROVAL_AGE = timedelta(hours=2)
MAX_APPROVAL_ENVELOPE_LAG = timedelta(minutes=10)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        require(key not in result, f"duplicate JSON key: {key}")
        result[key] = value
    return result


def read_json(path: Path) -> Any:
    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique_pairs)
    require(type(value) in {dict, list}, f"unexpected JSON root: {path}")
    return value


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_json(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True) + "\n").encode("utf-8")


def exact_keys(value: object, keys: set[str], label: str) -> dict[str, Any]:
    require(type(value) is dict and set(value) == keys, f"{label} keys")
    return value


def nonempty_string(value: object, label: str) -> str:
    require(type(value) is str and value.strip() == value and bool(value), label)
    return value


def single_line_string(value: object, label: str) -> str:
    text = nonempty_string(value, label)
    require(not any(char in text for char in "\r\n\t"), label)
    return text


def digest_string(value: object, label: str) -> str:
    require(type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value) is not None,
            label)
    return value


def utc_timestamp(value: object, label: str) -> datetime:
    nonempty_string(value, label)
    require(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", value) is not None,
            label)
    try:
        parsed = datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    except ValueError as error:
        raise RuntimeError(label) from error
    require(parsed.strftime("%Y-%m-%dT%H:%M:%SZ") == value, label)
    return parsed


def is_reparse(path: Path) -> bool:
    attributes = getattr(path.lstat(), "st_file_attributes", 0)
    return bool(attributes & 0x400)


def relative_name(path: Path) -> str:
    name = path.relative_to(ROOT).as_posix()
    pure = PurePosixPath(name)
    require(name == pure.as_posix(), f"non-canonical path: {name}")
    require(not pure.is_absolute() and ".." not in pure.parts, f"unsafe path: {name}")
    require("\\" not in name, f"backslash path: {name}")
    require(":" not in name, f"colon/alternate stream path: {name}")
    require(unicodedata.normalize("NFC", name) == name, f"non-NFC path: {name}")
    return name


def no_follow_files(root: Path) -> list[Path]:
    result: list[Path] = []

    def visit(directory: Path) -> None:
        with os.scandir(directory) as iterator:
            entries = sorted(iterator, key=lambda item: (item.name.casefold(), item.name))
        for entry in entries:
            path = Path(entry.path)
            require(not entry.is_symlink() and not is_reparse(path),
                    f"symlink/reparse point forbidden: {path}")
            if entry.is_dir(follow_symlinks=False):
                visit(path)
            else:
                require(entry.is_file(follow_symlinks=False),
                        f"non-regular filesystem entry forbidden: {path}")
                result.append(path)

    visit(root)
    return result


def actual_files() -> dict[str, Path]:
    result: dict[str, Path] = {}
    for path in no_follow_files(ROOT):
        name = relative_name(path)
        require(path.suffix.lower() in ALLOWED_SUFFIXES,
                f"unsupported file type: {name}")
        require(name not in result and name.casefold() not in
                {existing.casefold() for existing in result}, f"path collision: {name}")
        require(path.stat().st_size <= 1_000_000, f"oversized release file: {name}")
        result[name] = path
    return result


def verify_detached_mode(files: dict[str, Path], release: bool) -> None:
    expected = DETACHED - {"PAYLOAD_MANIFEST.json"}
    present = set(files) & expected
    if release:
        require(present == expected,
                f"release detached set mismatch: missing={sorted(expected-present)}, extra={sorted(present-expected)}")
    else:
        require(not present,
                f"detached release artifacts forbidden in integration mode: {sorted(present)}")


def verify_publication_gates(gates: object) -> None:
    """Validate declared requirements; completion is proved by release receipts."""
    require(type(gates) is list and gates == sorted(REQUIRED_GATES),
            "publication gate requirements")


def verify_manifest(files: dict[str, Path], release: bool) -> dict[str, Any]:
    manifest = read_json(MANIFEST)
    require(set(manifest) == {
        "detached_names_excluded", "files", "manifest_self_excluded", "nonclaims",
        "payload_file_count", "schema", "status",
    }, "manifest schema keys")
    require(manifest["schema"] == "jed-working-note-v5-payload-manifest-v1",
            "manifest schema")
    require(manifest["manifest_self_excluded"] is True, "manifest self exclusion")
    expected_status = ("release-candidate" if release else
                       "integration-candidate-not-release-authorized")
    require(manifest["status"] == expected_status, "manifest status")
    expected_nonclaims = MANIFEST_COMMON_NONCLAIMS + [
        MANIFEST_RELEASE_NONCLAIM if release else MANIFEST_INTEGRATION_NONCLAIM
    ]
    require(manifest["nonclaims"] == expected_nonclaims, "manifest mode-aware nonclaims")
    require(manifest["detached_names_excluded"] == sorted(DETACHED - {"PAYLOAD_MANIFEST.json"}),
            "detached-name declaration")
    rows = manifest["files"]
    require(type(rows) is list and manifest["payload_file_count"] == len(rows),
            "manifest count")
    names = []
    for row in rows:
        require(type(row) is dict and set(row) == {"bytes", "path", "sha256"},
                "manifest row keys")
        name = row["path"]
        require(type(name) is str and name == PurePosixPath(name).as_posix(),
                f"manifest path normalization: {name!r}")
        require(not PurePosixPath(name).is_absolute() and ".." not in PurePosixPath(name).parts,
                f"manifest traversal: {name}")
        require(name not in DETACHED, f"detached file manifested: {name}")
        require(type(row["bytes"]) is int and row["bytes"] >= 0, "manifest bytes")
        require(type(row["sha256"]) is str and re.fullmatch(r"[0-9a-f]{64}", row["sha256"]),
                "manifest sha256")
        names.append(name)
    require(names == sorted(names), "manifest rows not sorted")
    require(len(names) == len(set(names)) == len({name.casefold() for name in names}),
            "manifest duplicate/case collision")
    observed = set(files) - ({"PAYLOAD_MANIFEST.json"} | (DETACHED - {"PAYLOAD_MANIFEST.json"}))
    require(set(names) == observed,
            f"manifest/actual payload mismatch: missing={sorted(observed-set(names))}, extra={sorted(set(names)-observed)}")
    for row in rows:
        path = files[row["path"]]
        require(path.stat().st_size == row["bytes"], f"byte drift: {row['path']}")
        require(sha256(path) == row["sha256"], f"hash drift: {row['path']}")
    generated = subprocess.run(
        [sys.executable, "-I", "-B", str(GENERATOR), "--status",
         "release" if release else "integration"],
        cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    require(generated.returncode == 0,
            f"manifest generator failed: {generated.stderr.decode(errors='replace')}")
    require(generated.stdout == MANIFEST.read_bytes(), "stored/generated manifest drift")
    return manifest


def verify_json_tree(files: dict[str, Path]) -> None:
    for name, path in files.items():
        if path.suffix.lower() == ".json":
            read_json(path)


def verify_svg_css(text: str, name: str, fragment_references: set[str]) -> None:
    require("/*" not in text and "*/" not in text and "@" not in text and
            "\\" not in text, f"unsafe SVG CSS syntax in {name}")
    blocks = list(re.finditer(r"([^{}]+)\{([^{}]*)\}", text))
    residue = re.sub(r"([^{}]+)\{([^{}]*)\}", "", text)
    require(residue.strip() == "" and bool(blocks), f"unparsed SVG CSS in {name}")
    for block in blocks:
        selector = block.group(1).strip()
        require(re.fullmatch(r"(?:text|\.[A-Za-z][A-Za-z0-9_-]*)(?:\s*,\s*(?:text|\.[A-Za-z][A-Za-z0-9_-]*))*",
                             selector) is not None, f"unsafe SVG selector in {name}")
        declarations = [item.strip() for item in block.group(2).split(";") if item.strip()]
        require(bool(declarations), f"empty SVG CSS rule in {name}")
        for declaration in declarations:
            require(declaration.count(":") == 1, f"invalid SVG CSS declaration in {name}")
            prop, value = (part.strip() for part in declaration.split(":", 1))
            require(prop in SVG_CSS_PROPERTIES, f"unsafe SVG CSS property in {name}: {prop}")
            require(re.fullmatch(r"[A-Za-z0-9#().,% '\"_-]+", value) is not None,
                    f"unsafe SVG CSS value in {name}: {value}")
            lowered = value.casefold()
            require(not any(token in lowered for token in
                            ("javascript", "expression", "data:", "http:", "https:", "file:")),
                    f"active SVG CSS in {name}")
            if "url(" in lowered:
                match = re.fullmatch(r"url\(#[A-Za-z][A-Za-z0-9_.:-]*\)", value)
                require(prop == "marker-end" and match is not None,
                        f"non-fragment SVG CSS reference in {name}")
                fragment_references.add(value[5:-1])


def verify_svg(body: bytes, name: str) -> None:
    lowered = body.lower()
    for marker in (b"<!doctype", b"<!entity", b"<?xml-stylesheet"):
        require(marker not in lowered, f"active SVG declaration in {name}")
    root = ET.fromstring(body)
    require(root.tag == f"{{{SVG_NS}}}svg", f"SVG root: {name}")
    ids: set[str] = set()
    fragment_references: set[str] = set()
    for element in root.iter():
        require(type(element.tag) is str and element.tag.startswith(f"{{{SVG_NS}}}"),
                f"foreign SVG namespace in {name}")
        local = element.tag.split("}", 1)[1]
        require(local in SVG_ALLOWED_ATTRIBUTES, f"unsafe SVG element in {name}: {local}")
        allowed = SVG_ALLOWED_ATTRIBUTES[local]
        for key, value in element.attrib.items():
            require("}" not in key, f"namespaced SVG attribute in {name}: {key}")
            require(not key.casefold().startswith("on") and key in allowed,
                    f"unsafe SVG attribute in {name}: {key}")
            require(type(value) is str and re.fullmatch(r"[^\x00-\x1f\x7f<>`]+", value) is not None,
                    f"unsafe SVG attribute value in {name}: {key}")
            lowered_value = value.casefold()
            require(not any(token in lowered_value for token in
                            ("javascript:", "data:", "http:", "https:", "file:", "//")),
                    f"external/active SVG attribute in {name}: {key}")
            if key == "id":
                require(re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]*", value) is not None and
                        value not in ids, f"invalid/duplicate SVG id in {name}")
                ids.add(value)
            if key.casefold().endswith("href") or "url(" in lowered_value:
                if key.casefold().endswith("href"):
                    require(re.fullmatch(r"#[A-Za-z][A-Za-z0-9_.:-]*", value) is not None,
                            f"non-fragment SVG reference in {name}")
                    fragment_references.add(value[1:])
                else:
                    match = re.fullmatch(r"url\(#[A-Za-z][A-Za-z0-9_.:-]*\)", value)
                    require(match is not None, f"non-fragment SVG reference in {name}")
                    fragment_references.add(value[5:-1])
        if local == "style":
            verify_svg_css(element.text or "", name, fragment_references)
    require(fragment_references <= ids,
            f"unresolved SVG fragments in {name}: {sorted(fragment_references-ids)}")


def verify_safety(files: dict[str, Path]) -> None:
    decoded: dict[str, str] = {}
    bidi = {chr(value) for value in (0x202A, 0x202B, 0x202D, 0x202E, 0x202C,
                                     0x2066, 0x2067, 0x2068, 0x2069)}
    invisible = {chr(value) for value in (0x200B, 0x200C, 0x200D, 0x2060, 0xFEFF)}
    credential_patterns = [
        re.compile((r"\b" + "KGA" + "T_" + r"[A-Za-z0-9_-]{8,}\b").encode()),
        re.compile(rb"\bAKIA[0-9A-Z]{16}\b"),
        re.compile(rb"\bsk-[A-Za-z0-9_-]{20,}\b"),
        re.compile(rb"\bghp_[A-Za-z0-9]{20,}\b"),
        re.compile(rb"\bgithub_pat_[A-Za-z0-9_]{20,}\b"),
        re.compile(rb"(?i)authorization\s*:\s*bearer\s+[A-Za-z0-9._~-]{8,}"),
        re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ]
    absolute_path_patterns = [
        re.compile(rb"(?i)\b[A-Z]:\\(?:Users|Documents and Settings)\\"),
        re.compile(rb"(?i)\b[A-Z]:/(?:Users|Documents and Settings)/"),
        re.compile(rb"/(?:home|Users)/[A-Za-z0-9._-]+/"),
    ]
    identifier_patterns = [
        re.compile(rb"(?i)\bSVID\s*[:=#]?\s*\d{6,}\b"),
        re.compile(rb"(?i)\bref\s*[:=#]?\s*\d{7,}\b"),
    ]
    prose_needles = [
        b"http" + b".post", b"secret" + b".txt", b"token" + b"=admin123",
    ]
    for name, path in files.items():
        body = path.read_bytes()
        require(b"\x00" not in body, f"NUL byte: {name}")
        for pattern in credential_patterns + absolute_path_patterns + identifier_patterns:
            require(pattern.search(body) is None, f"sensitive pattern in {name}")
        text = body.decode("utf-8")
        require(not any(char in text for char in bidi), f"bidi control in {name}")
        require(not any(char in text for char in invisible), f"zero-width control in {name}")
        require(not any(0xE0000 <= ord(char) <= 0xE007F for char in text),
                f"Unicode tag character in {name}")
        require("\x1b" not in text, f"ANSI escape in {name}")
        decoded[name] = text
        lowered = body.lower()
        if name == "synthetic_workbench/tests/test_reproduce.py":
            for needle in prose_needles:
                for quote in (b'"', b"'"):
                    lowered = lowered.replace(b"b" + quote + needle + quote, b"")
        for needle in prose_needles:
            require(needle not in lowered, f"attack-specific content in {name}")
        if path.suffix.lower() == ".svg":
            verify_svg(body, name)
    url_pattern = re.compile(r"https?://[^\s)>,]+")
    for name, text in decoded.items():
        for url in url_pattern.findall(text):
            host = (urlparse(url.rstrip(".\"'")).hostname or "").casefold()
            require(host in ALLOWED_WEB_HOSTS, f"unapproved web host in {name}: {host}")


def run_completed(command: list[str]) -> subprocess.CompletedProcess[bytes]:
    completed = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE)
    require(completed.returncode == 0,
            f"command failed ({completed.returncode}): {' '.join(command)}\n{completed.stderr.decode(errors='replace')}")
    return completed


def run(command: list[str]) -> bytes:
    return run_completed(command).stdout


def canonical_nested_name(value: object) -> str:
    name = nonempty_string(value, "nested manifest path")
    pure = PurePosixPath(name)
    require(name == pure.as_posix() and not pure.is_absolute() and ".." not in pure.parts and
            "\\" not in name and ":" not in name and
            unicodedata.normalize("NFC", name) == name, f"unsafe nested path: {name}")
    return name


def verify_workbench(release: bool) -> dict[str, Any]:
    require(sys.version_info[:2] == (3, 12), "verification requires CPython 3.12")
    boundary = read_json(BOUNDARY)
    exact_keys(boundary, {"excluded", "in_scope", "publication_gate_requirements", "schema",
                          "status", "synthetic_workbench"}, "release boundary")
    require(boundary["schema"] == "jed-working-note-v5-release-boundary-v1",
            "release boundary schema")
    require(boundary["status"] ==
            ("release_candidate" if release else "local_integration_candidate_not_release_authorized"),
            "release boundary mode")
    verify_publication_gates(boundary["publication_gate_requirements"])
    declared = boundary["synthetic_workbench"]
    exact_keys(declared, {
        "accepted_seed_manifest_bytes", "accepted_seed_manifest_sha256",
        "first_acceptance_disposition", "integration_change", "manifest_bytes",
        "manifest_sha256", "relative_path", "second_acceptance_disposition",
    }, "workbench boundary")
    require(declared["relative_path"] == "synthetic_workbench", "workbench relative path")
    require(declared["accepted_seed_manifest_bytes"] == ACCEPTED_SEED_MANIFEST["bytes"] and
            declared["accepted_seed_manifest_sha256"] == ACCEPTED_SEED_MANIFEST["sha256"],
            "accepted seed manifest identity")
    require(WORKBENCH_MANIFEST.stat().st_size == declared["manifest_bytes"],
            "boundary/workbench manifest bytes")
    require(sha256(WORKBENCH_MANIFEST) == declared["manifest_sha256"],
            "boundary/workbench manifest hash")
    nested = read_json(WORKBENCH_MANIFEST)
    exact_keys(nested, {"files", "manifest_self_excluded", "nonclaims", "payload_file_count",
                        "schema", "status"}, "nested manifest")
    require(nested["schema"] == "jed-working-note-v5-synthetic-workbench-manifest-v1" and
            nested["status"] == "integrated-component" and
            nested["manifest_self_excluded"] is True, "nested manifest schema/status")
    require(nested["nonclaims"] == [
        "This manifest proves self-consistency, not authorship or external authenticity.",
        "This workbench makes no claim about the inaccessible competition private policy.",
        "Publication authority, licensing, and rights attestations are governed by the V5 root.",
    ], "nested manifest nonclaims")
    require(type(nested["files"]) is list and
            nested["payload_file_count"] == len(nested["files"]), "nested manifest count")
    nested_names: list[str] = []
    nested_rows: dict[str, tuple[int, str]] = {}
    for row in nested["files"]:
        exact_keys(row, {"bytes", "path", "sha256"}, "nested manifest row")
        name = canonical_nested_name(row["path"])
        require(type(row["bytes"]) is int and row["bytes"] >= 0, "nested manifest bytes")
        digest = digest_string(row["sha256"], "nested manifest sha256")
        nested_names.append(name)
        nested_rows[name] = (row["bytes"], digest)
    require(nested_names == sorted(nested_names, key=lambda item: (item.casefold(), item)),
            "nested manifest rows not sorted")
    require(len(nested_names) == len(set(nested_names)) ==
            len({name.casefold() for name in nested_names}),
            "nested manifest duplicate/case collision")
    actual_nested = {
        path.relative_to(WORKBENCH).as_posix() for path in no_follow_files(WORKBENCH)
        if path != WORKBENCH_MANIFEST
    }
    require(set(nested_names) == actual_nested, "nested manifest set incomplete")
    for row in nested["files"]:
        path = WORKBENCH / row["path"]
        require(path.stat().st_size == row["bytes"] and sha256(path) == row["sha256"],
                f"nested workbench drift: {row['path']}")
    for name, accepted in ACCEPTED_WORKBENCH_CORE.items():
        require(nested_rows.get(name) == accepted,
                f"accepted workbench core drift: {name}")
    expected = EXPECTED.read_bytes()
    normal = run([sys.executable, "-I", "-B", str(REPRODUCER), "--check", str(EXPECTED)])
    optimized = run([sys.executable, "-I", "-B", "-O", str(REPRODUCER),
                     "--check", str(EXPECTED)])
    require(normal == optimized == expected, "workbench canonical output drift")
    normal_tests = run_completed([sys.executable, "-I", "-B", "-m", "unittest", "discover",
                                  "-s", str(TESTS), "-v"])
    optimized_tests = run_completed([sys.executable, "-I", "-B", "-O", "-m", "unittest",
                                     "discover", "-s", str(TESTS), "-v"])
    require(normal_tests.stdout == optimized_tests.stdout == b"", "unexpected unittest stdout")
    for completed in (normal_tests, optimized_tests):
        match = re.search(rb"Ran (\d+) tests", completed.stderr)
        require(match is not None and int(match.group(1)) == 11, "unit-test count")
        require(b"\nOK" in completed.stderr, "unit-test terminal status")
    result = read_json(EXPECTED)
    policy = result["policy_nonidentification"]
    require(result["scope"]["synthetic_only"] is True, "synthetic scope")
    require(result["scope"]["private_policy_claims"] == 0, "private-policy nonclaim")
    require(policy["policy_count"] == 8 and len(policy["pairwise_witnesses"]) == 28,
            "policy witness coverage")
    require(len(policy["aggregate_equivalence_groups"]) >= 2, "equivalence coverage")
    require(policy["minimal_distinguishing_case_ids"] == [
        "tagged_local_publish", "other_recipient", "two_publishes"
    ], "minimal-suite drift")
    return result


def verify_campaign_correction(release: bool) -> dict[str, Any]:
    expected = CAMPAIGN_EXPECTED.read_bytes()
    normal = run([sys.executable, "-I", "-B", str(CAMPAIGN_REPRODUCER),
                  "--check", str(CAMPAIGN_EXPECTED)])
    optimized = run([sys.executable, "-I", "-B", "-O", str(CAMPAIGN_REPRODUCER),
                     "--check", str(CAMPAIGN_EXPECTED)])
    require(normal == optimized == expected, "campaign correction canonical drift")
    result = read_json(CAMPAIGN_EXPECTED)
    require(result["prior"] == {"mean": "119.606364", "n": 11, "sample_sd": "1.618804"},
            "campaign prior drift")
    require(result["fresh_author_designated_batch"] == {
        "mean": "114.406250", "n": 4, "sample_sd": "2.744122"
    }, "campaign fresh drift")
    require(result["exact_exchangeable_mean_rank"]["fraction"] == "3/1365",
            "campaign rank drift")
    provenance = read_json(CAMPAIGN_PROVENANCE)
    exact_keys(provenance, {
        "assertion_basis", "baseline_score_bank", "fresh_batch_preregistration", "nonclaims",
        "record_created_utc", "released_values_fixture", "schema", "scope", "selection_rule",
        "status",
    }, "campaign provenance")
    require(provenance["schema"] == "jed-working-note-v5-campaign-provenance-v1",
            "campaign provenance schema")
    require(provenance["status"] ==
            ("author_declared_source_hash_record_manifest_bound" if release else
             "author_declared_source_hash_record_pending_owner_attestation"),
            "campaign provenance status")
    utc_timestamp(provenance["record_created_utc"], "campaign provenance timestamp")
    require(provenance["scope"] == "deidentified public repeat-family correction only",
            "campaign provenance scope")
    held_sources = {
        "baseline_score_bank": (98070, "ec42a33fa86e906390ea2893f2bc43f643dfb3aba93f31042131dbe46b96d827"),
        "fresh_batch_preregistration": (6288, "02d256037d7463ad4de01485c95a77688a2f93364ec2cc30d7da7487ad645508"),
    }
    for key, (size, digest) in held_sources.items():
        row = exact_keys(provenance[key], {"body_in_release", "bytes", "sha256"},
                         f"campaign provenance {key}")
        require(row == {"body_in_release": False, "bytes": size, "sha256": digest},
                f"campaign provenance source identity: {key}")
    fixture = exact_keys(provenance["released_values_fixture"],
                         {"bytes", "path", "sha256"}, "campaign released fixture")
    fixture_path = ROOT / "data" / "campaign_public_scores.json"
    require(fixture == {
        "path": "data/campaign_public_scores.json",
        "bytes": fixture_path.stat().st_size,
        "sha256": sha256(fixture_path),
    }, "campaign released fixture binding")
    nonempty_string(provenance["selection_rule"], "campaign selection rule")
    nonempty_string(provenance["assertion_basis"], "campaign assertion basis")
    require(provenance["nonclaims"] == [
        "This record is author-declared provenance, not independent proof of source creation time.",
        "The author-held source bodies are excluded because they contain operational identifiers outside the Working Note scope.",
        "The released values identify no private row, evaluator change, parser, model, runtime, or private policy.",
    ], "campaign provenance nonclaims")
    if release:
        require("pending" not in provenance["assertion_basis"].casefold(),
                "campaign provenance owner attestation pending")
    return result


def resolve_json_anchor(value: object, anchor: str, label: str) -> object:
    current = value
    require(anchor != "", f"empty JSON anchor: {label}")
    for segment in anchor.split("."):
        match = re.fullmatch(r"([A-Za-z0-9_-]+)((?:\[[^\]]+\])*)", segment)
        require(match is not None, f"invalid JSON anchor syntax: {label}")
        key, selectors = match.groups()
        require(type(current) is dict and key in current, f"unknown JSON anchor: {label}")
        current = current[key]
        for selector in re.findall(r"\[([^\]]+)\]", selectors):
            require(type(current) is list, f"selector on non-list JSON anchor: {label}")
            if re.fullmatch(r"\d+", selector):
                index = int(selector)
                require(index < len(current), f"JSON anchor index out of range: {label}")
                current = current[index]
            else:
                field, separator, expected = selector.partition("=")
                require(separator == "=" and field and expected,
                        f"invalid JSON anchor selector: {label}")
                matches = [item for item in current if type(item) is dict and
                           str(item.get(field)) == expected]
                require(len(matches) == 1, f"non-unique JSON anchor selector: {label}")
                current = matches[0]
    return current


def resolve_file_json_anchor(path: Path, anchor: str, label: str) -> object:
    value = read_json(path)
    first = anchor.split(".", 1)[0]
    prefixes = {path.stem, path.name.rsplit(".", 1)[0]}
    if type(value) is dict and first not in value and first in prefixes and "." in anchor:
        anchor = anchor.split(".", 1)[1]
    return resolve_json_anchor(value, anchor, label)


def normalized_literal_present(path: Path, literal: str) -> bool:
    body = " ".join(path.read_text(encoding="utf-8").split())
    needle = " ".join(literal.split())
    return bool(needle) and needle in body


def validate_claim_anchors(row: dict[str, Any], files: dict[str, Path],
                           official: dict[str, Any]) -> None:
    candidates: list[Path] = []
    for source_id in row["source_ids"]:
        if source_id.startswith("file:"):
            reference = source_id[5:]
            name, separator, anchor = reference.partition("#")
            require(name in files, f"unknown claim file source: {source_id}")
            path = files[name]
            candidates.append(path)
            if separator:
                require(path.suffix.casefold() == ".json",
                        f"JSON fragment on non-JSON source: {source_id}")
                resolve_file_json_anchor(path, anchor, source_id)
        else:
            require(source_id in official, f"unknown official source: {source_id}")
            candidates.append(SOURCES)
    unique_candidates = list(dict.fromkeys(candidates))
    require(bool(unique_candidates), f"claim has no source candidates: {row['id']}")
    for anchor in row["data_anchors"]:
        explicit = re.fullmatch(r"([^#]+\.[A-Za-z0-9]+)#(.+)", anchor)
        if explicit is not None:
            prefix, nested_anchor = explicit.groups()
            matching = [path for path in unique_candidates
                        if relative_name(path) == prefix or path.name == prefix]
            require(len(matching) == 1 and matching[0].suffix.casefold() == ".json",
                    f"unknown/ambiguous anchored source: {row['id']}/{anchor}")
            resolve_file_json_anchor(matching[0], nested_anchor,
                                     f"{row['id']}/{anchor}")
            continue
        resolved = False
        for path in unique_candidates:
            if path.suffix.casefold() == ".json" and " " not in anchor:
                try:
                    resolve_file_json_anchor(path, anchor, f"{row['id']}/{anchor}")
                    resolved = True
                    break
                except RuntimeError:
                    continue
            if normalized_literal_present(path, anchor):
                resolved = True
                break
        require(resolved, f"unresolved claim data anchor: {row['id']}/{anchor}")


def verify_evidence(files: dict[str, Path], release: bool) -> None:
    claims = read_json(CLAIMS)
    exact_keys(claims, {"claims", "schema", "status"}, "claim ledger")
    require(claims["schema"] == "jed-working-note-v5-claim-ledger-v2", "claim schema")
    require(claims["status"] == ("final" if release else "integration_draft"),
            "claim-ledger status")
    ids = [row["id"] for row in claims["claims"]]
    require(len(ids) == len(set(ids)) and len(ids) >= 12, "claim ids")
    required_claim_keys = {
        "class", "data_anchors", "falsifier", "id", "reproduction",
        "reviewer_disposition", "rights_status", "scope", "source_ids",
        "temporal_scope", "text_anchor",
    }
    sources = read_json(SOURCES)
    exact_keys(sources, {"capture_manifest", "nonclaim", "schema", "sources", "status"},
               "official source index")
    require(sources["schema"] == "jed-working-note-v5-official-source-index-v1",
            "source-index schema")
    exact_keys(sources["capture_manifest"], {"bytes", "sha256"},
               "official source capture manifest")
    require(type(sources["sources"]) is list, "official sources list")
    official = {row["id"]: row for row in sources["sources"]}
    require(len(official) == len(sources["sources"]) and len(official) >= 5,
            "official source ids")
    for row in sources["sources"]:
        exact_keys(row, {"body_in_release", "capture_bytes", "capture_scope", "capture_sha256",
                         "captured_on", "id", "title", "url"},
                   f"official source row: {row.get('id')}")
        require(re.fullmatch(r"[0-9a-f]{64}", row["capture_sha256"]), "source hash")
        require(row["capture_bytes"] > 0 and row["url"].startswith("https://www.kaggle.com/"),
                "source identity")
    require(official["Official-Evaluation"]["capture_sha256"] ==
            "3c85656c0d37fb50946f867e68965aafcdfbcfdfcde1fc86921396480909e931",
            "official Evaluation capture identity")

    note = NOTE.read_text(encoding="utf-8")
    allowed_classes = {
        "author_protocol", "illustrative_decision_model", "non_claim", "observation",
        "official_fact", "recommendation", "released_computation",
    }
    for row in claims["claims"]:
        require(set(row) == required_claim_keys, f"claim row keys: {row.get('id')}")
        scalar_keys = required_claim_keys - {"data_anchors", "reproduction", "source_ids"}
        require(all(type(row[key]) is str and row[key].strip() for key in scalar_keys),
                f"empty claim field: {row.get('id')}")
        for key in ("data_anchors", "reproduction", "source_ids"):
            require(type(row[key]) is list and row[key] and
                    all(type(value) is str and value.strip() for value in row[key]),
                    f"empty claim list: {row.get('id')}/{key}")
        require(row["class"] in allowed_classes, f"claim class: {row['id']}")
        require(note.count(f"<!-- {row['text_anchor']} -->") == 1,
                f"missing/non-unique note anchor: {row['id']}")
        validate_claim_anchors(row, files, official)
        if release:
            require("pending" not in row["rights_status"].casefold() and
                    "must be attested" not in row["rights_status"].casefold(),
                    f"release claim rights unresolved: {row['id']}")
            stale_temporal = row["temporal_scope"].casefold()
            require("must be rechecked" not in stale_temporal and
                    "requires post-close review" not in stale_temporal,
                    f"release claim temporal scope unresolved: {row['id']}")
    note_claim_anchors = re.findall(r"<!-- (claim:[A-Za-z0-9-]+) -->", note)
    ledger_claim_anchors = [row["text_anchor"] for row in claims["claims"]]
    require(sorted(note_claim_anchors) == sorted(ledger_claim_anchors),
            "note/ledger claim-anchor bijection")
    require({"C-NONCLAIM-PRIVATE-001", "C-NONCLAIM-REDUCER-001",
             "C-NONCLAIM-COMPETITOR-001", "C-NONCLAIM-DEPLOYMENT-001",
             "C-NONCLAIM-TRANSFER-001", "C-CAMPAIGN-CORRECTION-001",
             "C-METHOD-NOISY-MAX-001", "C-SYNTH-MUTATION-001"} <= set(ids),
            "required claims/nonclaims")

    rights = read_json(RIGHTS)
    exact_keys(rights, {"items", "release_status", "required_before_release", "schema"},
               "rights register")
    require(rights["schema"] == "jed-working-note-v5-source-rights-register-v1",
            "rights schema")
    require(type(rights["items"]) is list and type(rights["required_before_release"]) is list,
            "rights register lists")
    for item in rights["items"]:
        exact_keys(item, {"class", "included", "paths", "rights_basis"},
                   f"rights row: {item.get('class')}")
        single_line_string(item["class"], "rights class")
        require(type(item["included"]) is bool and type(item["paths"]) is list and
                all(type(path) is str and path for path in item["paths"]), "rights row values")
        nonempty_string(item["rights_basis"], "rights basis")
    require(rights["release_status"] ==
            ("owner_attested" if release else "owner_attestation_pending"),
            "rights status")
    if release:
        require(rights["required_before_release"] == [],
                "rights requirements remain open")
        for item in rights["items"]:
            require("pending" not in item["rights_basis"].casefold() and
                    "must be attested" not in item["rights_basis"].casefold(),
                    f"release rights basis unresolved: {item.get('class')}")
    patterns = [path for item in rights["items"] if item["included"] is True
                for path in item["paths"]]
    require(all(type(pattern) is str and pattern for pattern in patterns), "rights paths")
    uncovered = []
    for name in files:
        covered = any(name.startswith(pattern) if pattern.endswith("/") else name == pattern
                      for pattern in patterns)
        if not covered:
            uncovered.append(name)
    require(not uncovered, f"rights-register uncovered paths: {sorted(uncovered)}")

    related = read_json(RELATED)
    exact_keys(related, {"entries", "policy", "required_topics", "schema", "status"},
               "related work")
    require(type(related["entries"]) is list and type(related["required_topics"]) is list,
            "related-work lists")
    for row in related["entries"]:
        base = {"authors", "id", "proposition_used", "review_status", "title",
                "url", "year"}
        # Pages that can be revised under a stable URL must pin what was read and when;
        # versioned publications must not, being pinned already by year and identifier.
        live_page = "//www.kaggle.com/" in row.get("url", "")
        pin = {"observed_revision", "observed_on"}
        expected = base | pin if live_page else base
        exact_keys(row, expected, f"related-work row: {row.get('id')}")
        require(type(row["year"]) is int and 1900 <= row["year"] <= 2100 and
                all(type(row[key]) is str and row[key].strip() for key in
                    ("authors", "id", "proposition_used", "review_status", "title", "url")),
                f"related-work row values: {row.get('id')}")
        if live_page:
            require(all(type(row[key]) is str and row[key].strip() for key in sorted(pin)),
                    f"related-work revision pin: {row.get('id')}")
            require(re.fullmatch(r"\d{4}-\d{2}-\d{2}", row["observed_on"]) is not None,
                    f"related-work observed_on format: {row.get('id')}")
            require(re.fullmatch(r"\d{4}-\d{2}-\d{2}|none_observed", row["observed_revision"])
                    is not None,
                    f"related-work observed_revision format: {row.get('id')}")
    require(related["status"] == ("final_proposition_review_and_link_check_complete" if release else
                                  "initial_proposition_review_complete_final_link_check_pending"),
            "related-work status")
    if release:
        expected_reviews = {
            "AgentDojo": "full_text_reviewed",
            "InjecAgent": "full_text_reviewed",
            "Generic-Holdout": "full_text_reviewed",
            "Ladder": "full_text_reviewed",
            "Reusable-Holdout": "full_text_reviewed",
            "CONSORT-2025": "statement_and_explanation_reviewed",
            "Small-Test-Suites": "full_text_reviewed",
            "JED-Xander": "public_note_proposition_reviewed",
            "JED-Radiant": "public_note_proposition_reviewed",
            "JED-Pilkwang": "public_notebook_proposition_reviewed",
            "JED-Cleanor": "public_note_proposition_reviewed",
            "JED-oNanachii": "public_note_proposition_reviewed",
        }
        require({row["id"]: row["review_status"] for row in related["entries"]} ==
                expected_reviews, "related-work entry review incomplete")
    related_ids = [row["id"] for row in related["entries"]]
    require(set(related_ids) == {"AgentDojo", "InjecAgent", "Generic-Holdout",
                                 "Ladder", "Reusable-Holdout", "CONSORT-2025",
                                 "Small-Test-Suites", "JED-Xander", "JED-Radiant",
                                 "JED-Pilkwang", "JED-Cleanor", "JED-oNanachii"},
            "related-work set")
    body = note.split("## References", 1)[0]
    for identifier in related_ids:
        require(f"[{identifier}]" in body, f"unused/missing body citation: {identifier}")
    require("[Official-Evaluation]" in body, "official Evaluation citation missing")
    body_citations = set(re.findall(r"\[([A-Za-z][A-Za-z0-9-]+)\]", body))
    require(body_citations == set(related_ids) | OFFICIAL_BODY_CITATIONS,
            "note/registry citation bijection")
    for heading in ("## Abstract", "## 1. The correction",
                    "## 10. Responsible disclosure boundary", "## 11. Limitations",
                    "## References"):
        require(heading in note, f"missing note section: {heading}")


def verify_license(author: dict[str, Any]) -> str:
    license_path = ROOT / "LICENSE.txt"
    require(author["license_path"] == "LICENSE.txt" and license_path.is_file(),
            "author license path")
    actual_digest = sha256(license_path)
    require(author["license_sha256"] == actual_digest, "author license binding")
    spdx = author["license_spdx_id"]
    require(spdx in LICENSE_TEMPLATES, "unapproved license SPDX identifier")
    template = LICENSE_TEMPLATES[spdx]
    template_digest = hashlib.sha256(template.encode("utf-8")).hexdigest()
    require(author["license_template_sha256"] == template_digest,
            "license template hash")
    holder = re.escape(author["copyright_holder"])
    pattern = re.escape(template)
    pattern = pattern.replace(re.escape("<YEAR>"), r"\d{4}")
    pattern = pattern.replace(re.escape("<COPYRIGHT_HOLDER>"), holder)
    license_text = license_path.read_text(encoding="utf-8")
    require(re.fullmatch(pattern, license_text) is not None,
            "license is not the approved canonical template")
    return actual_digest


def verify_campaign_recheck_bindings(terminal: dict[str, Any]) -> None:
    expected = {
        "campaign_expected_summary_sha256": sha256(CAMPAIGN_EXPECTED),
        "campaign_provenance_sha256": sha256(CAMPAIGN_PROVENANCE),
        "campaign_public_scores_sha256": sha256(
            ROOT / "data" / "campaign_public_scores.json"
        ),
    }
    for field, digest in expected.items():
        digest_string(terminal[field], f"terminal campaign binding: {field}")
        require(terminal[field] == digest,
                f"terminal campaign binding mismatch: {field}")


def resolve_payload_artifact(name: object, label: str) -> Path:
    value = canonical_nested_name(name)
    path = ROOT.joinpath(*PurePosixPath(value).parts)
    require(path.is_file() and not path.is_symlink() and not is_reparse(path),
            f"{label} missing or unsafe")
    require(relative_name(path) == value, f"{label} path drift")
    return path


def verify_mechanics_capture(path: Path) -> dict[str, Any]:
    capture = exact_keys(read_json(path), {
        "capture_method", "captured_at_utc", "nonclaims", "observed_precedent_urls",
        "official_observations", "official_urls", "schema", "selected_route",
        "signed_in_ui_observations", "status",
    }, "official mechanics capture")
    require(capture["schema"] ==
            "jed-working-note-v5-official-mechanics-live-capture-v2" and
            capture["status"] == "PASS", "official mechanics capture schema/status")
    require(capture["capture_method"] == "signed_in_ui_plus_official_public_pages",
            "official mechanics capture method")
    utc_timestamp(capture["captured_at_utc"], "official mechanics capture timestamp")
    require(capture["nonclaims"] == MECHANICS_NONCLAIMS,
            "official mechanics capture nonclaims")

    urls = exact_keys(capture["official_urls"], {
        "competition", "criteria", "kaggle_competitions_documentation",
    }, "official mechanics URLs")
    require(urls == {
        "competition": "https://www.kaggle.com/competitions/ai-agent-security-multi-step-tool-attacks",
        "criteria": "https://www.kaggle.com/competitions/ai-agent-security-multi-step-tool-attacks/overview/evaluation",
        "kaggle_competitions_documentation": "https://www.kaggle.com/docs/competitions",
    }, "official mechanics URL values")

    official = exact_keys(capture["official_observations"], {
        "award_count", "award_usd_each", "criteria", "deadline_utc",
        "explicit_jed_submission_channel_present",
    }, "official mechanics observations")
    require(official["award_count"] == 2 and official["award_usd_each"] == 2500 and
            official["criteria"] == WORKING_NOTE_CRITERIA and
            official["deadline_utc"] == WORKING_NOTE_DEADLINE_UTC and
            type(official["explicit_jed_submission_channel_present"]) is bool,
            "official mechanics observation values")

    ui = exact_keys(capture["signed_in_ui_observations"], {
        "competition_new_writeup_action_present", "competition_submit_writeup_control_present",
        "competition_track_selector_present", "competition_writeups_tab_present",
        "discussion_new_topic_action_present", "profile_new_project_writeup_action_present",
        "signed_in",
    }, "signed-in mechanics observations")
    require(all(type(value) is bool for value in ui.values()) and ui["signed_in"] is True,
            "signed-in mechanics observation values")

    precedents = capture["observed_precedent_urls"]
    require(type(precedents) is list and len(precedents) >= 2 and
            len(precedents) == len(set(precedents)), "mechanics precedent URLs")
    precedent_paths = []
    for url in precedents:
        nonempty_string(url, "mechanics precedent URL")
        parsed = urlparse(url)
        require(parsed.scheme == "https" and (parsed.hostname or "").casefold() in
                {"kaggle.com", "www.kaggle.com"}, "mechanics precedent host")
        precedent_paths.append(parsed.path)
    require(any(path.startswith("/writeups/") for path in precedent_paths) and
            any(path.startswith(
                "/competitions/ai-agent-security-multi-step-tool-attacks/discussion/"
            ) for path in precedent_paths), "mechanics route precedent coverage")

    route = exact_keys(capture["selected_route"], {
        "eligibility_uncertainty_disclosed", "official_channel_status",
        "ordered_publication_actions", "organizer_confirmed_channel",
        "partial_completion_policy", "publication_channel",
        "redundant_self_contained_discussion",
    }, "selected Working Note route")
    require(route["publication_channel"] == PUBLICATION_CHANNEL,
            "selected publication channel")
    require(route["eligibility_uncertainty_disclosed"] is True and
            route["redundant_self_contained_discussion"] is True and
            route["ordered_publication_actions"] == PUBLICATION_ACTIONS and
            route["partial_completion_policy"] == PARTIAL_COMPLETION_POLICY and
            ui["discussion_new_topic_action_present"] is True,
            "selected route disclosure/transaction semantics")
    if official["explicit_jed_submission_channel_present"]:
        require(route["official_channel_status"] == "EXPLICIT_IN_CURRENT_JED_MATERIAL" and
                route["organizer_confirmed_channel"] is True,
                "explicit official Working Note route")
    else:
        require(route["official_channel_status"] == "UNSPECIFIED_IN_CURRENT_JED_MATERIAL" and
                route["organizer_confirmed_channel"] is False,
                "unspecified official Working Note route")
    if "Project Writeup" in route["publication_channel"]:
        require(ui["profile_new_project_writeup_action_present"] is True or
                ui["competition_new_writeup_action_present"] is True,
                "selected Project Writeup route unavailable")
    return capture


def expected_preview_figures() -> dict[str, str]:
    return {
        "figures/campaign_repeat_correction.svg": sha256(
            ROOT / "figures" / "campaign_repeat_correction.svg"
        ),
        "figures/equal_score_different_decision.svg": sha256(
            ROOT / "figures" / "equal_score_different_decision.svg"
        ),
        "figures/error_first_flow.svg": sha256(
            ROOT / "figures" / "error_first_flow.svg"
        ),
    }


def verify_payload_receipts() -> tuple[dict[str, dict[str, Any]], dict[str, datetime]]:
    sources = {row["id"]: row for row in read_json(SOURCES)["sources"]}
    mechanics_path = RECEIPTS["official_mechanics_receipt_sha256"]
    preview_path = RECEIPTS["rendered_preview_receipt_sha256"]
    terminal_path = RECEIPTS["terminal_facts_receipt_sha256"]
    mechanics = exact_keys(read_json(mechanics_path), {
        "capture_artifact", "checked_at_utc", "checker_public_name",
        "eligibility_uncertainty_disclosed", "judging_criteria_verified",
        "official_channel_status", "official_source_id", "ordered_publication_actions",
        "partial_completion_policy", "schema", "selected_publication_route", "status",
        "working_note_deadline_utc",
    }, "official mechanics receipt")
    require(mechanics["schema"] == "jed-working-note-v5-official-mechanics-receipt-v3" and
            mechanics["status"] == "PASS", "official mechanics receipt schema/status")
    require(mechanics["official_source_id"] == "Official-Working-Note-Criteria",
            "official mechanics source")
    require(mechanics["judging_criteria_verified"] is True and
            mechanics["eligibility_uncertainty_disclosed"] is True,
            "official mechanics/disclosure incomplete")
    require(mechanics["working_note_deadline_utc"] == WORKING_NOTE_DEADLINE_UTC,
            "official mechanics deadline binding")
    artifact = exact_keys(mechanics["capture_artifact"], {"bytes", "path", "sha256"},
                          "official mechanics capture artifact")
    require(artifact["path"] == MECHANICS_CAPTURE_RELATIVE and
            type(artifact["bytes"]) is int and artifact["bytes"] > 0,
            "official mechanics capture artifact identity")
    digest_string(artifact["sha256"], "official mechanics capture artifact hash")
    capture_path = resolve_payload_artifact(artifact["path"],
                                            "official mechanics capture artifact")
    require(artifact["bytes"] == capture_path.stat().st_size and
            artifact["sha256"] == sha256(capture_path),
            "official mechanics capture artifact binding")
    capture = verify_mechanics_capture(capture_path)
    require(capture["official_urls"]["criteria"] ==
            sources["Official-Working-Note-Criteria"]["url"],
            "official mechanics criteria URL binding")
    route = capture["selected_route"]
    require(mechanics["selected_publication_route"] == route["publication_channel"] and
            mechanics["official_channel_status"] == route["official_channel_status"] and
            mechanics["ordered_publication_actions"] ==
            route["ordered_publication_actions"] == PUBLICATION_ACTIONS and
            mechanics["partial_completion_policy"] ==
            route["partial_completion_policy"] == PARTIAL_COMPLETION_POLICY,
            "official mechanics selected-route binding")
    single_line_string(mechanics["checker_public_name"], "official mechanics checker")
    single_line_string(mechanics["selected_publication_route"],
                       "official mechanics selected route")

    terminal = exact_keys(read_json(terminal_path), {
        "campaign_expected_summary_sha256", "campaign_family_post_close_rechecked",
        "campaign_family_recheck_summary", "campaign_provenance_sha256",
        "campaign_public_scores_sha256",
        "captured_at_utc", "capturer_public_name", "competition_closed", "live_capture_bytes",
        "final_submission_deadline_utc", "live_capture_sha256", "live_url",
        "official_source_id", "same_family_released_sequence_complete", "schema", "status",
        "terminal_fact_summary", "terminal_facts_verified",
    }, "terminal facts receipt")
    require(terminal["schema"] == "jed-working-note-v5-terminal-facts-receipt-v1" and
            terminal["status"] == "PASS", "terminal facts receipt schema/status")
    require(terminal["official_source_id"] == "Official-Timeline" and
            terminal["live_url"] == sources["Official-Timeline"]["url"],
            "terminal facts source")
    require(terminal["competition_closed"] is True and
            terminal["terminal_facts_verified"] is True, "terminal facts incomplete")
    require(terminal["campaign_family_post_close_rechecked"] is True and
            terminal["same_family_released_sequence_complete"] is True,
            "campaign family post-close recheck incomplete")
    verify_campaign_recheck_bindings(terminal)
    require(terminal["final_submission_deadline_utc"] == FINAL_SUBMISSION_DEADLINE_UTC,
            "terminal deadline binding")
    require(type(terminal["live_capture_bytes"]) is int and terminal["live_capture_bytes"] > 0,
            "terminal facts capture bytes")
    digest_string(terminal["live_capture_sha256"], "terminal facts capture hash")
    single_line_string(terminal["capturer_public_name"], "terminal facts capturer")
    nonempty_string(terminal["campaign_family_recheck_summary"],
                    "campaign family recheck summary")
    nonempty_string(terminal["terminal_fact_summary"], "terminal fact summary")

    preview = exact_keys(read_json(preview_path), {
        "accessibility_reviewed", "figure_sha256", "links_reviewed", "publication_channel",
        "partial_completion_policy", "previewed_publication_actions",
        "rendered_artifact_bytes", "rendered_artifact_sha256", "rendered_format",
        "rendered_surface_count", "reviewed_at_utc", "reviewer_public_name", "schema",
        "source_note_sha256", "status", "visual_review_passed",
    }, "rendered preview receipt")
    require(preview["schema"] == "jed-working-note-v5-rendered-preview-receipt-v2" and
            preview["status"] == "PASS", "rendered preview receipt schema/status")
    require(preview["visual_review_passed"] is True and preview["links_reviewed"] is True and
            preview["accessibility_reviewed"] is True, "rendered preview incomplete")
    require(preview["source_note_sha256"] == sha256(NOTE), "preview/note binding")
    require(preview["figure_sha256"] == expected_preview_figures(),
            "preview/figure binding")
    require(preview["rendered_format"] == "pdf" and
            type(preview["rendered_artifact_bytes"]) is int and
            preview["rendered_artifact_bytes"] > 0 and
            preview["rendered_surface_count"] == len(PUBLICATION_ACTIONS),
            "rendered artifact identity")
    require(preview["publication_channel"] == route["publication_channel"] and
            preview["previewed_publication_actions"] == PUBLICATION_ACTIONS and
            preview["partial_completion_policy"] == PARTIAL_COMPLETION_POLICY,
            "preview/selected-route transaction binding")
    digest_string(preview["rendered_artifact_sha256"], "rendered artifact hash")
    single_line_string(preview["reviewer_public_name"], "preview reviewer")
    single_line_string(preview["publication_channel"], "preview channel")

    timestamps = {
        "mechanics_capture": utc_timestamp(
            capture["captured_at_utc"], "mechanics capture timestamp"
        ),
        "mechanics": utc_timestamp(mechanics["checked_at_utc"], "mechanics timestamp"),
        "preview": utc_timestamp(preview["reviewed_at_utc"], "preview timestamp"),
        "terminal": utc_timestamp(terminal["captured_at_utc"], "terminal timestamp"),
    }
    return {"mechanics": mechanics, "preview": preview, "terminal": terminal}, timestamps


def verify_release_timestamp_bounds(
        payload_times: dict[str, datetime], author_time: datetime,
        audit_a_time: datetime, audit_b_time: datetime, safety_time: datetime,
        approval_time: datetime, envelope_time: datetime,
        verification_time: datetime | None = None) -> None:
    """Bind the release chain to the official close and Working Note window."""
    final_deadline = utc_timestamp(FINAL_SUBMISSION_DEADLINE_UTC,
                                   "final submission deadline constant")
    note_deadline = utc_timestamp(WORKING_NOTE_DEADLINE_UTC,
                                  "Working Note deadline constant")
    require(payload_times["terminal"] >= final_deadline,
            "terminal facts captured before competition close")
    require(payload_times["mechanics_capture"] >= final_deadline,
            "official mechanics capture predates competition close")
    require(payload_times["mechanics"] >= final_deadline,
            "official mechanics not rechecked after competition close")
    require(payload_times["mechanics_capture"] <= payload_times["mechanics"],
            "official mechanics receipt predates its live capture")
    require(payload_times["mechanics"] - payload_times["mechanics_capture"] <=
            MAX_MECHANICS_CAPTURE_RECEIPT_LAG,
            "official mechanics receipt is stale relative to its live capture")
    require(payload_times["preview"] >=
            max(payload_times["terminal"], payload_times["mechanics"]),
            "rendered preview predates terminal/mechanics evidence")
    require(approval_time - payload_times["mechanics_capture"] <=
            MAX_MECHANICS_CAPTURE_APPROVAL_AGE,
            "official mechanics capture is stale at owner approval")
    require(approval_time <= note_deadline and envelope_time <= note_deadline,
            "release chain exceeds Working Note deadline")
    require(envelope_time - approval_time <= MAX_APPROVAL_ENVELOPE_LAG,
            "release envelope is stale relative to owner approval")
    observed_times = list(payload_times.values()) + [
        author_time, audit_a_time, audit_b_time, safety_time, approval_time, envelope_time,
    ]
    now = verification_time or datetime.now(timezone.utc)
    require(now.tzinfo is not None and now.utcoffset() == timedelta(0),
            "verification time must be UTC aware")
    require(max(observed_times) <= now + MAX_FUTURE_CLOCK_SKEW,
            "release receipt timestamp is in the future")


def verify_release_audit(path: Path, auditor: str, manifest_digest: str,
                         author_digest: str) -> tuple[dict[str, Any], datetime]:
    audit = exact_keys(read_json(path), {
        "audited_at_utc", "auditor", "author_attestation_sha256", "disposition",
        "p0_findings", "p1_findings", "payload_manifest_sha256", "schema", "scope",
        "status", "verifier_sha256",
    }, f"{auditor} release audit")
    require(audit["schema"] == "jed-working-note-v5-release-audit-v1" and
            audit["status"] == "PASS" and audit["disposition"] == "FIRE",
            f"{auditor} release audit schema/status")
    require(audit["auditor"] == auditor and
            audit["scope"] == "payload_manifest_and_release_contract",
            f"{auditor} audit identity/scope")
    require(audit["p0_findings"] == [] and audit["p1_findings"] == [],
            f"{auditor} audit findings remain")
    require(audit["payload_manifest_sha256"] == manifest_digest and
            audit["author_attestation_sha256"] == author_digest and
            audit["verifier_sha256"] == sha256(Path(__file__)),
            f"{auditor} audit bindings")
    return audit, utc_timestamp(audit["audited_at_utc"], f"{auditor} audit timestamp")


def verify_payload_safety(manifest: dict[str, Any], manifest_digest: str) -> tuple[dict[str, Any], datetime]:
    safety = exact_keys(read_json(RECEIPTS["payload_safety_receipt_sha256"]), {
        "active_content_findings", "credential_findings", "manual_review_complete",
        "manifest_file_count", "manifested_bytes_scanned", "payload_manifest_sha256",
        "private_identifier_findings", "reviewer_public_name", "scanned_at_utc", "schema",
        "scope", "status", "verifier_sha256",
    }, "payload safety receipt")
    require(safety["schema"] == "jed-working-note-v5-payload-safety-receipt-v1" and
            safety["status"] == "PASS" and safety["scope"] == "manifested_payload_only",
            "payload safety schema/status/scope")
    require(safety["manual_review_complete"] is True and
            safety["active_content_findings"] == [] and
            safety["credential_findings"] == [] and
            safety["private_identifier_findings"] == [], "payload safety findings")
    require(safety["payload_manifest_sha256"] == manifest_digest and
            safety["verifier_sha256"] == sha256(Path(__file__)),
            "payload safety bindings")
    require(safety["manifest_file_count"] == manifest["payload_file_count"] and
            safety["manifested_bytes_scanned"] == sum(row["bytes"] for row in manifest["files"]),
            "payload safety scan coverage")
    single_line_string(safety["reviewer_public_name"], "payload safety reviewer")
    return safety, utc_timestamp(safety["scanned_at_utc"], "payload safety timestamp")


def verify_release_only(manifest: dict[str, Any]) -> dict[str, str]:
    require(manifest["status"] == "release-candidate", "manifest not release-candidate")
    manifest_digest = sha256(MANIFEST)
    required = [
        ROOT / "AUTHOR_ATTESTATION.json",
        ROOT / "OWNER_PUBLICATION_APPROVAL.json",
        ROOT / "RELEASE_ENVELOPE.json",
        ROOT / "LICENSE.txt",
    ]
    require(all(path.is_file() for path in required) and
            all(path.is_file() for path in RECEIPTS.values()),
            "release artifacts/receipts missing")
    payload_receipts, payload_times = verify_payload_receipts()
    author = exact_keys(read_json(required[0]), {
        "attested_at_utc", "contribution_statement", "copyright_holder", "license_path",
        "license_sha256", "license_spdx_id", "license_template_sha256",
        "ownership_and_rights_attested", "payload_manifest_sha256", "public_name",
        "partial_completion_policy", "publication_actions", "publication_channel", "schema",
        "status", "team_attribution", "typed_attestation",
    }, "author attestation")
    require(author["schema"] == "jed-working-note-v5-author-attestation-v2" and
            author["status"] == "final", "author attestation schema/status")
    require(author["ownership_and_rights_attested"] is True, "author rights not attested")
    for key in ("public_name", "team_attribution", "contribution_statement",
                "copyright_holder", "publication_channel"):
        single_line_string(author[key], f"author field: {key}")
    require(author["typed_attestation"] ==
            "I attest that the ownership, rights, contribution, and attribution statements in this record are true.",
            "author typed attestation")
    require(author["payload_manifest_sha256"] == manifest_digest, "author manifest binding")
    require(author["publication_actions"] == PUBLICATION_ACTIONS and
            author["partial_completion_policy"] == PARTIAL_COMPLETION_POLICY,
            "author publication transaction semantics")
    license_digest = verify_license(author)
    author_time = utc_timestamp(author["attested_at_utc"], "author attestation timestamp")
    provenance_time = utc_timestamp(read_json(CAMPAIGN_PROVENANCE)["record_created_utc"],
                                    "campaign provenance timestamp")
    require(max(payload_times.values()) <= author_time,
            "payload receipts must precede author attestation")
    require(provenance_time <= author_time, "campaign provenance must precede author attestation")
    require(payload_receipts["preview"]["publication_channel"] == author["publication_channel"],
            "preview/author publication channel")
    require(payload_receipts["mechanics"]["selected_publication_route"] ==
            author["publication_channel"], "mechanics/author publication channel")
    require(payload_receipts["mechanics"]["ordered_publication_actions"] ==
            payload_receipts["preview"]["previewed_publication_actions"] ==
            author["publication_actions"] == PUBLICATION_ACTIONS and
            payload_receipts["mechanics"]["partial_completion_policy"] ==
            payload_receipts["preview"]["partial_completion_policy"] ==
            author["partial_completion_policy"] == PARTIAL_COMPLETION_POLICY,
            "payload/author publication transaction binding")
    note_text = NOTE.read_text(encoding="utf-8")
    require(author["public_name"] in note_text and author["team_attribution"] in note_text,
            "publication note missing final author/team attribution")

    author_digest = sha256(required[0])
    _, audit_a_time = verify_release_audit(RECEIPTS["independent_audit_a_sha256"],
                                            "Review Pass A", manifest_digest, author_digest)
    _, audit_b_time = verify_release_audit(RECEIPTS["independent_audit_b_sha256"],
                                       "Review Pass B", manifest_digest, author_digest)
    _, safety_time = verify_payload_safety(manifest, manifest_digest)
    require(author_time <= min(audit_a_time, audit_b_time, safety_time),
            "audits/safety must follow author attestation")

    approval = exact_keys(read_json(required[1]), {
        "approved_at_utc", "approved_for_one_release_transaction", "approval_origin",
        "approver_public_name", "author_attestation_sha256",
        "authorized_publication_actions", "conversation_event_id",
        "independent_audit_a_sha256", "license_sha256", "official_mechanics_receipt_sha256",
        "partial_completion_policy", "payload_manifest_sha256",
        "payload_safety_receipt_sha256", "publication_channel",
        "rendered_preview_receipt_sha256", "schema", "single_use_nonce",
        "independent_audit_b_sha256", "status", "terminal_facts_receipt_sha256", "venue",
    }, "owner approval")
    require(approval["schema"] == "jed-working-note-v5-owner-publication-approval-v2" and
            approval["status"] == "final" and
            approval["approved_for_one_release_transaction"] is True,
            "owner approval schema/status")
    require(approval["approval_origin"] == "explicit_user_message_recorded_out_of_band",
            "owner approval origin")
    for key in ("approver_public_name", "conversation_event_id", "publication_channel", "venue"):
        single_line_string(approval[key], f"owner approval field: {key}")
    nonce = nonempty_string(approval["single_use_nonce"], "single-use nonce")
    require(re.fullmatch(r"[A-Za-z0-9_-]{16,128}", nonce) is not None,
            "single-use nonce strength")
    require(approval["payload_manifest_sha256"] == manifest_digest and
            approval["author_attestation_sha256"] == author_digest and
            approval["license_sha256"] == license_digest,
            "owner approval primary bindings")
    require(approval["authorized_publication_actions"] ==
            author["publication_actions"] == PUBLICATION_ACTIONS and
            approval["partial_completion_policy"] ==
            author["partial_completion_policy"] == PARTIAL_COMPLETION_POLICY,
            "owner approval publication transaction semantics")
    for field, path in RECEIPTS.items():
        require(approval[field] == sha256(path), f"owner approval receipt binding: {field}")
    approval_time = utc_timestamp(approval["approved_at_utc"], "owner approval timestamp")
    require(max(audit_a_time, audit_b_time, safety_time) <= approval_time,
            "owner approval must follow audits/safety")

    envelope = exact_keys(read_json(required[2]), {
        "authorized_publication_actions",
        "author_attestation_sha256", "created_at_utc", "independent_audit_a_sha256",
        "license_sha256", "official_mechanics_receipt_sha256", "owner_approval_sha256",
        "partial_completion_policy", "payload_manifest_sha256",
        "payload_safety_receipt_sha256", "publication_channel",
        "rendered_preview_receipt_sha256", "schema", "single_use_nonce",
        "independent_audit_b_sha256", "status", "terminal_facts_receipt_sha256",
    }, "release envelope")
    require(envelope["schema"] == "jed-working-note-v5-release-envelope-v2" and
            envelope["status"] == "final", "release envelope schema/status")
    require(envelope["payload_manifest_sha256"] == manifest_digest and
            envelope["author_attestation_sha256"] == author_digest and
            envelope["owner_approval_sha256"] == sha256(required[1]) and
            envelope["license_sha256"] == license_digest,
            "release envelope primary bindings")
    require(envelope["single_use_nonce"] == nonce and
            envelope["publication_channel"] == approval["publication_channel"] ==
            author["publication_channel"], "release scope/nonce binding")
    require(envelope["authorized_publication_actions"] ==
            approval["authorized_publication_actions"] ==
            author["publication_actions"] == PUBLICATION_ACTIONS and
            envelope["partial_completion_policy"] ==
            approval["partial_completion_policy"] ==
            author["partial_completion_policy"] == PARTIAL_COMPLETION_POLICY,
            "release transaction scope binding")
    for field, path in RECEIPTS.items():
        require(envelope[field] == approval[field] == sha256(path),
                f"release envelope receipt binding: {field}")
    envelope_time = utc_timestamp(envelope["created_at_utc"], "release envelope timestamp")
    require(approval_time <= envelope_time, "release envelope must follow owner approval")
    verify_release_timestamp_bounds(
        payload_times, author_time, audit_a_time, audit_b_time, safety_time,
        approval_time, envelope_time,
    )

    status_files = [
        ROOT / "README.md", NOTE, MANIFEST, BOUNDARY, CLAIMS, RIGHTS, RELATED,
        CAMPAIGN_PROVENANCE, WORKBENCH / "README.md", WORKBENCH_MANIFEST,
    ]
    pending = re.compile(
        r"pre[-_ ]?close|not[-_ ]?(?:a[-_ ]?)?release|integration_draft|"
        r"publication[^\n]{0,40}pending|owner[^\n]{0,30}attestation[^\n]{0,20}pending|"
        r"must be supplied|do not publish|still requires|final hashes will be inserted|"
        r"abstract_reviewed|final_link_check_pending|\bhold\b[^\n]{0,20}\bpublication\b|"
        r"not[^\n]{0,20}publication[-_ ]authorized|\bunpublished\b|\bstaging\b",
        re.IGNORECASE,
    )
    for path in status_files:
        require(pending.search(path.read_text(encoding="utf-8")) is None,
                f"unresolved release marker: {relative_name(path)}")
    return {
        "author_attestation_sha256": author_digest,
        "independent_audit_a_sha256": sha256(RECEIPTS["independent_audit_a_sha256"]),
        "official_mechanics_receipt_sha256": sha256(RECEIPTS["official_mechanics_receipt_sha256"]),
        "owner_approval_sha256": sha256(required[1]),
        "payload_safety_receipt_sha256": sha256(RECEIPTS["payload_safety_receipt_sha256"]),
        "release_envelope_sha256": sha256(required[2]),
        "rendered_preview_receipt_sha256": sha256(RECEIPTS["rendered_preview_receipt_sha256"]),
        "independent_audit_b_sha256": sha256(RECEIPTS["independent_audit_b_sha256"]),
        "terminal_facts_receipt_sha256": sha256(RECEIPTS["terminal_facts_receipt_sha256"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", action="store_true",
                        help="also require all human, rights, terminal, and publication gates")
    args = parser.parse_args()
    files = actual_files()
    require("PAYLOAD_MANIFEST.json" in files, "payload manifest missing")
    verify_detached_mode(files, args.release)
    verify_json_tree(files)
    manifest = verify_manifest(files, args.release)
    verify_safety(files)
    result = verify_workbench(args.release)
    campaign = verify_campaign_correction(args.release)
    release_tests = run_completed([sys.executable, "-I", "-B", "-m", "unittest",
                                   "discover", "-s", str(RELEASE_TESTS), "-v"])
    release_tests_optimized = run_completed([sys.executable, "-I", "-B", "-O", "-m",
                                             "unittest", "discover", "-s",
                                             str(RELEASE_TESTS), "-v"])
    for completed in (release_tests, release_tests_optimized):
        match = re.search(rb"Ran (\d+) tests", completed.stderr)
        require(match is not None and int(match.group(1)) == 27, "release-verifier test count")
        require(b"\nOK" in completed.stderr and completed.stdout == b"",
                "release-verifier tests")
    verify_evidence(files, args.release)
    completion_evidence: dict[str, str] = {}
    if args.release:
        completion_evidence = verify_release_only(manifest)
    boundary = read_json(BOUNDARY)
    inventory = [
        {"path": name, "bytes": path.stat().st_size, "sha256": sha256(path)}
        for name, path in sorted(files.items())
    ]
    receipt = {
        "schema": "jed-working-note-v5-verification-receipt-v4",
        "mode": "release" if args.release else "integration",
        "python": f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}",
        "verifier_sha256": sha256(Path(__file__)),
        "boundary_status": boundary["status"],
        "publication_gate_requirements": boundary["publication_gate_requirements"],
        "release_completion_evidence": completion_evidence,
        "verification_nonclaims": [
            "Mechanical PASS proves payload integrity and internal consistency only. It does not prove human identity, review independence, signed approval, publication authority, or an out-of-band publication action. It also does not prove that any number in the release is true or self-consistent, that any figure depicts its data, that any citation supports the proposition attributed to it, that a claim's anchor supports the claim, or that a declared non-claim holds. The manifest is recomputed from the tree, so a PASS is evidence against unintended edits, not against an author who regenerates it.",
            "Publication authority remains an out-of-band owner decision bound by the recorded approval artifacts.",
        ],
        "release_envelope_sha256": completion_evidence.get("release_envelope_sha256"),
        "payload_file_count": manifest["payload_file_count"],
        "payload_manifest_sha256": sha256(MANIFEST),
        "synthetic_result_sha256": sha256(EXPECTED),
        "campaign_result_sha256": sha256(CAMPAIGN_EXPECTED),
        "campaign_exchangeable_rank": campaign["exact_exchangeable_mean_rank"]["fraction"],
        "policy_count": result["policy_nonidentification"]["policy_count"],
        "pairwise_witness_count": len(result["policy_nonidentification"]["pairwise_witnesses"]),
        "whole_tree_file_count": len(inventory),
        "whole_tree_inventory": inventory,
        "whole_tree_inventory_sha256": hashlib.sha256(canonical_json(inventory)).hexdigest(),
        "whole_tree_total_bytes": sum(row["bytes"] for row in inventory),
        "status": "PASS",
    }
    sys.stdout.write(json.dumps(receipt, sort_keys=True, separators=(",", ":")) + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
