#!/usr/bin/env python3
"""Generate the self-excluding V5 payload manifest deterministically."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import sys
import unicodedata


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "PAYLOAD_MANIFEST.json"
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
RELEASE_REQUIRED_PAYLOADS = {
    "LICENSE.txt",
    "evidence/receipts/official_working_note_mechanics_capture.json",
    "evidence/receipts/official_working_note_mechanics_receipt.json",
    "evidence/receipts/rendered_preview_receipt.json",
    "evidence/receipts/terminal_facts_receipt.json",
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


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


def payload_files() -> list[Path]:
    rows: list[Path] = []
    for path in ROOT.rglob("*"):
        require(not path.is_symlink() and not is_reparse(path),
                f"symlink/reparse point forbidden: {path}")
        if path.is_dir():
            continue
        name = relative_name(path)
        if name in DETACHED:
            continue
        require(path.suffix.lower() in ALLOWED_SUFFIXES,
                f"unsupported payload type: {name}")
        rows.append(path)
    rows.sort(key=relative_name)
    names = [relative_name(path) for path in rows]
    require(names == sorted(names), "payload rows not bytewise sorted")
    require(len(names) == len(set(names)), "duplicate payload path")
    require(len({name.casefold() for name in names}) == len(names),
            "case-folded payload collision")
    return rows


def build(status: str = "integration") -> dict[str, object]:
    require(status in {"integration", "release"}, "manifest build status")
    files = []
    for path in payload_files():
        body = path.read_bytes()
        files.append({
            "path": relative_name(path),
            "bytes": len(body),
            "sha256": hashlib.sha256(body).hexdigest(),
        })
    names = {row["path"] for row in files}
    if status == "release":
        require(RELEASE_REQUIRED_PAYLOADS <= names,
                f"release payload prerequisites missing: {sorted(RELEASE_REQUIRED_PAYLOADS-names)}")
    nonclaims = [
        "Content hashes establish identity, not authorship, correctness, or rights.",
        "The package does not identify the inaccessible competition private guardrail.",
    ]
    if status == "release":
        nonclaims.append(
            "Mechanical release verification proves internal consistency only; it does "
            "not prove human identity, agent independence, signed approval, publication "
            "authority, or that an out-of-band publication action occurred."
        )
    else:
        nonclaims.append(
            "The package is not licensed, publication-authorized, or a terminal release."
        )
    return {
        "schema": "jed-working-note-v5-payload-manifest-v1",
        "status": ("release-candidate" if status == "release" else
                   "integration-candidate-not-release-authorized"),
        "manifest_self_excluded": True,
        "detached_names_excluded": sorted(DETACHED - {"PAYLOAD_MANIFEST.json"}),
        "payload_file_count": len(files),
        "files": files,
        "nonclaims": nonclaims,
    }


def canonical(value: object) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=True) + "\n").encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--status", choices=("integration", "release"),
                        default="integration")
    args = parser.parse_args()
    rendered = canonical(build(args.status))
    if args.write:
        MANIFEST.write_bytes(rendered)
    sys.stdout.buffer.write(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
