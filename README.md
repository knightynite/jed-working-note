# Two Guardrails, Two Orders — reproducibility payload

This repository is the complete evidence and verification payload for the Working
Note *Two Guardrails, Two Orders: what it costs to make a benchmark score mean
something*, submitted to the Kaggle competition **AI Agent Security — Multi-Step Tool
Attacks**.

Everything here is standard-library Python. There are no third-party dependencies, no
network calls, no attack prompts, no private traces, and no credentials.

## The judge path

Download the release archive attached to this repository, extract it, and run one
command on CPython 3.12:

```text
python -I -B scripts/verify_release_v5.py
```

It checks the payload manifest against the files on disk, validates the evidence
records, reproduces both result sets, runs the synthetic and release-contract test
suites, resolves every claim anchor and citation, and prints one canonical receipt.

**Verify the archive, not a `git clone`.** The verifier is a whole-tree scan: it
requires that the directory contain exactly the manifested payload and nothing else,
so that no unlisted file can ride along unnoticed. A working clone carries `.git/`
and its VCS dotfiles, and the verifier correctly refuses to certify a tree it cannot
account for. The repository is here so the payload can be browsed and diffed; the
archive is the artifact the receipt describes.

## The expanded audit matrix

Each result is checked twice, once normally and once with assertions disabled, so
that optimization cannot silently remove a gate. The code raises rather than
asserting, so `-O` changes nothing:

```text
python -I -B    synthetic_workbench/scripts/reproduce.py --check synthetic_workbench/EXPECTED_RESULTS.json
python -I -B -O synthetic_workbench/scripts/reproduce.py --check synthetic_workbench/EXPECTED_RESULTS.json
python -I -B    -m unittest discover -s synthetic_workbench/tests -v
python -I -B -O -m unittest discover -s synthetic_workbench/tests -v
python -I -B    scripts/reproduce_campaign_correction.py --check EXPECTED_CAMPAIGN_SUMMARY.json
python -I -B -O scripts/reproduce_campaign_correction.py --check EXPECTED_CAMPAIGN_SUMMARY.json
```

Expected headline results emitted by those commands: 8 toy policies over 7 cases;
28/28 pairwise witnesses; a three-case minimum distinguishing suite; completion-only
delta `4` against a declared intention-to-treat delta `0`; and campaign exchangeable
rank `3/1365` under its stated null.

Two results discussed in the note are **derived rather than emitted** — the
label-free ablation and the uniqueness of the three-case suite. The note says so, and
both follow from the released fixtures in roughly fifteen lines.

## What is here

| Path | Contents |
|---|---|
| `publication/` | The note itself and its related-work register |
| `synthetic_workbench/` | Fixtures, reproducer, expected results, and mutation tests |
| `evidence/` | Claim ledger, release boundary, rights register, campaign provenance, post-close capture |
| `figures/` | The three figures embedded in the note |
| `scripts/` | The verifier, the manifest generator, the campaign reproducer |
| `tests/` | The release-contract test suite |
| `PAYLOAD_MANIFEST.json` | Per-file SHA-256 manifest; the manifest excludes itself |

## What the verifier does and does not establish

A mechanical pass proves internal consistency: that the files are the files the
manifest names, that every promoted claim resolves to an anchor and a source, that
the computations reproduce, and that the declared bindings hold.

It does not prove human identity, the independence of the two review passes, or
publication authority. Those are declarations, not machine-checked facts, and the
verifier says so in its own receipt rather than letting a green result imply more
than it establishes.

This archive is an **integration candidate**, and its manifest status says so. It
carries the payload, the evidence records, and the verifier; the attestation and
approval records that a final release binds are not part of it. The note is explicit
about the same boundary, and about the one result in it that a third party cannot
independently re-read.

## Licence

MIT. See `LICENSE.txt`. Copyright (c) 2026 AL Najafi.

The synthetic workbench is original work. The competition facts cited in the note are
drawn from dated captures of official pages, identified in
`evidence/official_source_index.json`. No competitor's non-public material is
reproduced.
