# Recorded VM evidence

`vm-results.tar.gz` is the unchanged archive of five completed comparisons, one
recovery test, and four incomplete attempts from 1 November 2026. `audit.json`
contains the recalculated metrics and checks; `environment.txt` records VM versions.

Reproduce the audit with `.venv/bin/python -m evaluation.audit_results`.
Generated audit tables go to the ignored `evaluation/runs/audit/` directory.
The website's recorded results come from this evidence, not from its animations.
