# Verification evidence: 4 November 2026

This folder records the final code review and validation. It supplements the
historical [five-run reference evidence](../../reference/README.md); it does not
replace or extend that dataset.

| Artifact | Contents |
| --- | --- |
| `linux-validation.log` | Environment check, 94 tests with no skips, initial load checks, fresh Mininet comparison, plots, recovery, and cleanup. |
| `linux-validation.tar.gz` | Raw comparison/recovery CSVs, flow snapshots, logs, plots, final load JSONs, and the validated source hash manifest. |
| `linux-load.log` | Final normal-load and intentional-overload checks. |
| `linux-load-normal.json` / `linux-load-overload.json` | Final Linux application stress measurements. |
| `macos-load-normal.json` / `macos-load-overload.json` | Local application stress measurements. |
| `load-normal-1s.json` | Additional Linux repeat with a one-second deadline: one failed attempt out of 6,400; health, bounds, draining, and recovery checks passed. |
| `source-sha256.json` | SHA-256 for every validated Python source/test, shell script, and launcher. |
| `python-audit.json` | Runtime/development requirements and resolved dependency advisory audit. |
| `linux-runtime.txt` / `linux-runtime-audit.json` | Local packages in the Linux virtual environment and the audit of that inventory with resolved dependencies. |
| `npm-audit.json` | Audit of all browser development dependencies; zero advisories. |
| `bandit.json` | Source scan at medium/high severity; no findings at those levels. |

The normal release check uses the standalone client's two-second deadline and
requires zero failed exchanges. The overload check uses a deliberate 100 ms
deadline and an eight-request admission limit; dropped or late attempts are
expected. The one-second repeat is retained to make the scheduler-sensitive
failure visible. A different timeout was not used to reinterpret that result.

The source hash manifest matches the final Python and shell files in this
change. The full 94-test suite and Mininet workflow ran before a small load
harness cleanup; both stress modes were rerun after that cleanup and after
aligning the normal timeout with the standalone client. Application and
controller behavior did not change between those runs.

See [final verification](../../../docs/VERIFICATION.md),
[testing instructions](../../../docs/TESTING.md), and
[security scope](../../../SECURITY.md) for interpretation and reproduction.
