# V5 synthetic reproducibility workbench

Status: **integrated synthetic component; release authority is held at the V5 root**.

This workbench develops three clean-room, harmless case studies for the JED
Working Note V5:

1. a favorable metric is rejected when its artifact identity drifts;
2. a completion-only treatment gain disappears under intention-to-treat;
3. distinct toy policies can have the same aggregate score while producing
   different decision traces even when immediate non-execution effects match.

The fixtures and implementation are synthetic. They contain no competition
prompts, attack payloads, SDK source, real endpoints, row-level submission
telemetry, private policy guesses, competitor content, credentials, or
real-system instructions. Results are conditional on the declared toy policies
and scoring rules and make no claim about the competition's inaccessible
private guardrail.

The V5 root manifest, rights register, license, and detached attestations govern
publication of this component.

Run from this directory with CPython 3.12:

```text
python -I -B scripts/reproduce.py
python -I -B scripts/reproduce.py --check EXPECTED_RESULTS.json
python -I -B -O scripts/reproduce.py --check EXPECTED_RESULTS.json
python -I -B -m unittest discover -s tests -v
python -I -B -O -m unittest discover -s tests -v
```

Every command is offline and standard-library-only.
