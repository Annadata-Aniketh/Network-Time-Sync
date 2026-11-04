# Testing and load checks

The supported network environment is Ubuntu 24.04 or Linux Mint 22 with Python
3.12. Run these commands from the repository root. The browser needs no build
step; Node.js 24 is required for the optional browser development tools.

## Install development tools

```bash
./timesync setup
sudo .venv/bin/python -m pip install -r requirements-dev.txt
npm ci --ignore-scripts
```

Runtime packages remain pinned in `requirements.txt`. Development versions are
pinned in `requirements-dev.txt` and `package-lock.json`.

## Automated suites

```bash
./timesync test
npm test
```

The Python suite covers packet validation, timestamp calculations, real UDP
client/server integration, failure accounting, server admission limits, source
address checks, topology, controller flow logic, startup/cleanup, and terminal
behavior. The JavaScript suite checks the deterministic teaching model.
Tests use ephemeral localhost ports and temporary output directories.

The OpenFlow forwarding test requires OS-Ken. Without it, that test is reported
as skipped; a local result with skips is not equivalent to the full VM result.

## Static analysis

```bash
.venv/bin/ruff check app evaluation scripts sdn topology tests
.venv/bin/ruff format --check app evaluation scripts sdn topology tests
.venv/bin/shellcheck timesync scripts/*.sh
npm run lint
.venv/bin/bandit -r app evaluation scripts sdn topology -ll
.venv/bin/pip-audit -r requirements-dev.txt
npm audit
```

Ruff checks imports, undefined names, syntax, common bugs, and Python 3.12
compatibility. ESLint checks all browser scripts and the browser-model tests.
Bandit fails the check for findings at medium or high severity. Run it without
`-ll` to inspect informational low-severity subprocess findings as well; the
project uses argument lists and trusted local command paths, with no shell
interpolation. The [security scope](../SECURITY.md) explains the review limits.

## Application load and overload

```bash
.venv/bin/python -m evaluation.load_test --output evaluation/runs/load-normal.json
.venv/bin/python -m evaluation.load_test --clients 64 --requests 10 \
  --max-pending 8 --timeout .1 --worker-delay-ms 5 --expect-overload \
  --output evaluation/runs/load-overload.json
```

The normal test sends 200 requests from each of 32 concurrent clients: 6,400
attempts, using the standalone client's two-second reply deadline. It also
injects malformed and oversized datagrams. A PASS requires no
failed exchanges, no worker errors, rejection of malformed traffic, a drained
queue, and a successful final probe.

The overload test deliberately slows workers and limits pending work to eight.
A PASS requires rejected excess work, a peak pending count no greater than eight,
no worker errors, complete draining, and a successful final probe. Dropped UDP
attempts are expected in this test. Throughput is a machine-specific observation,
not a capacity guarantee or a Mininet timing result.

## Mininet traffic and recovery

```bash
./timesync doctor
./timesync --batch --scenario both --duration 60
./timesync --batch --scenario recovery --duration 60
```

The comparison offers 12 Mbps of UDP traffic to the 10 Mbps primary path, then
adds 50 ms delay and 15 ms jitter. Each mode checks all 30 directed host pairs
before measurement. Recovery independently checks Path B use under load, rule
removal, increasing Path A counters, and successful replies after load stops.
See [the demo guide](DEMO.md) for plots and evidence export.

To reproduce the historical five-run audit:

```bash
.venv/bin/python -m evaluation.audit_results
```

The [verification record](VERIFICATION.md) states what was actually run.
The GitHub Actions workflow repeats static checks, audits, suites, application
load, a comparison, and recovery on Ubuntu 24.04, and saves diagnostics as a
workflow artifact.
