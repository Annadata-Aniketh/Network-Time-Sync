# Reproducible VM audit

Run `.venv/bin/python docs/build_results.py` from the repository root.
The script reads the preserved archive under `docs/evidence/`, extracts it into a
temporary directory, and recreates the files here:

- `raw_review.md`: counts by run and phase, including timeouts versus invalid replies.
- `trial_metrics.csv`: metrics for five comparisons, calculated with the plotting code.
- `phase_metrics.csv`: phase sample counts, failures, and mean post-correction error.
- `audit.json`: archive hash, server-log reconciliation, flow counters, impairment checks, and recovery checks.
- `environment.txt`: the original environment record captured in the VM at export.

The original supplied archive is kept unchanged. Incomplete runs are preserved
there but excluded from the quantitative comparison. The presentation's charts
use the per-run means in `audit.json`; the report records the measurement limits.
