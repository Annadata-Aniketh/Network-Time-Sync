# Final repository verification

Reviewed on **4 November 2026**, on the `final` branch. The current code was
checked locally and in the existing Linux Mint 22.3 VM using an isolated copy of
the source. The original VM checkout and the historical reference archive were
preserved.

## Automated checks

| Check | Result |
| --- | --- |
| Python unit, integration, and regression suite | **94 passed, no skips** on Linux / Python 3.12.3 and locally / Python 3.12.13 with OS-Ken installed. |
| Browser model suite | **10 passed** with Node.js. |
| Ruff lint and format checks | Passed for all project Python modules and tests. |
| ESLint | Passed for all four browser scripts and the browser-model tests. |
| ShellCheck, shell syntax, Python compilation | Passed. |
| Bandit | No medium or high findings. Low-severity subprocess findings reviewed; commands use argument lists and trusted local tools. |
| Python dependency audits | No known advisories in resolved runtime/development requirements or the Linux VM's local Python package inventory and its resolved dependencies. |
| npm dependency audit | Zero advisories, including development dependencies. The vulnerable minimatch version was replaced through an explicit override. |
| Historical evidence audit | Recomputed results match `evaluation/reference/audit.json` exactly. |
| Browser evidence values | Recorded trials, aggregate totals, and recovery values match the preserved audit. |

The added regressions exercise malformed and oversized datagrams, worker queue
limits and reuse, worker failures, unexpected UDP senders, invalid clock/client
settings, fractional iperf rates/durations, shell-free topology execution, and
invalid controller mode or polling settings.

## Application stress tests

Normal load uses 32 concurrent clients, 200 requests per client, and 500
malformed/oversized datagrams. Both macOS and Linux completed **6,400 of 6,400**
exchanges without failures at the final two-second deadline. Invalid traffic
was rejected, pending work drained, and a final probe succeeded. An additional
Linux repeat at a one-second deadline recorded one failed attempt out of 6,400;
that result is retained separately. Queue, worker-health, draining, and final
probe checks still passed in that repeat.

The separate overload test uses 64 clients, ten requests each, a 5 ms artificial
worker delay, and an eight-request admission limit. Both platforms rejected
excess work, stayed within the configured pending limit, drained their queues,
and answered a final probe. Lost or late attempts are expected under this
intentional overload. Throughput and latency depend on machine scheduling;
these application stress results are separate from Mininet measurements.

## Fresh Linux network validation

A new 60-second-per-mode comparison completed after the security changes.
Baseline and optimized modes each passed all **30 directed host-pair checks**;
all three clients produced successful synchronization samples. Plot generation
and the summary completed. This additional run recorded mean post-attempt clock
error of 50.457 ms for baseline and 0.856 ms for optimized mode. It is a validation
run, not an addition to the original five-run statistical comparison.

A separate 60-second recovery run passed every evidence check:

- Sync requests used Path B under load: 132 packets counted.
- Temporary reroute rules were removed from s1, s3, and s4.
- The Path A request counter increased from 132 to 144 after load stopped.
- All three clients received replies during recovery.

The final environment check passed after cleanup, including availability of
controller port 6653. The evidence is in
[`evaluation/verification/20261104/`](../evaluation/verification/20261104/README.md).

## Documentation and artifacts

The README links the supplied full-size topology, revised command sheet,
updated 17-slide presentation, editable PowerPoint copy, and academic report.
The copyable [demo guide](DEMO.md), [testing instructions](TESTING.md), and
[security scope](../SECURITY.md) describe the current behavior and checks.

Presentation slides 7, 8, and 12 now explain bounded admission, source checks,
and the latest validation. The original chart and embedded workbook were
preserved byte-for-byte after the presentation exporter dropped their
relationship during import/export. The resulting editable deck passed package,
layout, chart/workbook, and import checks. Changed PDF pages were rendered and
visually checked; the remaining pages retain the supplied PDF content.

The academic report remains a cited snapshot of its original source revision.
Its earlier test count is superseded by this verification record. The historical
performance figures in the report, browser, and presentation remain unchanged.
The preserved VM archive's SHA-256 is:

```text
3b094b35eebdcef4f8252b8a915cc629d7100e24c7aed5993e95093e7cade2a2
```

## Scope

The checks support the documented laboratory workflow. Source address checks
provide no cryptographic authentication, bounded admission does not guarantee
UDP delivery, and the optimized comparison combines queue treatment with a
higher-capacity alternate path. See [security scope](../SECURITY.md) for those
boundaries and [testing instructions](TESTING.md) to reproduce the checks.
