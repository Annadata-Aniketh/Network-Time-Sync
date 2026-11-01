# VM validation record

Evidence supplied by the user on 2026-11-01. Screenshots are saved in `evidence/`.
Raw files remain in the VM and have not been independently inspected here.

| Check | Current evidence | Status |
| --- | --- | --- |
| Host connectivity | VM console reports 30/30 pairs reachable | Observed in screenshots |
| UDP clients | Completed benchmark summaries; reply counters for three clients | Observed; raw logs pending |
| Repeated comparison | Runs 191520, 192057, 192459 with generated summaries | Observed; raw CSV audit pending |
| Dynamic rerouting | Run 190534: 6.01 Mbps trigger, 102 requests via port 6 | Observed in saved flow screenshot |
| Automatic recovery | Run 194117: all four packet/rule/client checks PASS | Observed; raw dumps pending |
| Automated tests | 53 local Python 3.12 tests passed, including the results review | Local result; VM suite output not supplied |
| Runtime versions | Python 3.12 shown during setup; other exact installed versions not captured | Export required |
| Actual offered/delivered traffic and qdiscs | Snapshots collected by runner | Raw file audit pending |
| Timeout versus invalid samples | Summary only shows combined failures | Raw file audit pending |

The original comparison run 190534 is additional evidence; the three repeated
runs in the report are 191520, 192057, and 192459. Recovery is a separate scenario.

Use `scripts/export_results.sh` to review and bundle all raw records. The archive
includes failed/incomplete runs as well; the generated comparison review excludes
them and lists their names.
