# VM validation record

Raw archive supplied by the user on 2026-11-01 and audited locally. The original
archive is preserved as `evidence/vm-results-20261101-195256.tar.gz`.

| Check | Evidence reviewed | Result |
| --- | --- | --- |
| UDP clients and host connectivity | Connectivity logs and client/server records | All normal samples succeed; all six hosts reachable |
| Comparison repeatability | Five completed comparisons with 60 seconds per mode | All stored summaries match recomputation |
| Application failures | CSV status counts and server sequence logs | Baseline: 393 timeouts, zero invalid; optimized: zero failures |
| Dynamic rerouting | Phase-2 s1 flow counters and controller logs for each run | Path B requests observed in every optimized comparison |
| Automatic recovery | Run 194117 raw flow dumps and client CSV | PASS on independent re-evaluation |
| Load and impairment | iperf logs, OVS queue records, and qdisc snapshots | Offered UDP load, queue rate settings, 50 ms / 15 ms netem present |
| Runtime | environment.txt | Linux Mint 22.3; Python 3.12.3; OS-Ken 2.11.2; Mininet 2.3.0 |
| Automated tests | Local Python 3.12 suite | 53 tests passed before documentation/deck work; VM suite output not supplied |

Comparisons: 190534, 191520, 192057, 192459, 193256. Recovery: 194117.
Four incomplete attempts are excluded from quantitative comparisons but retained
in the original archive. The environment was recorded at export, not before each
individual run. No packet captures establish the exact location of request loss.

Run `docs/build_results.py` to reproduce the review. Full findings and limits are
in [the project report](project_report.md); machine-readable evidence is in
[the audit](results/audit.json).
