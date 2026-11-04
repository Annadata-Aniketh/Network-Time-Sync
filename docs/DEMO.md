# TimeSync demo guide

Run network experiments in an Ubuntu 24.04 or Linux Mint 22 VM with Python 3.12,
Git, internet access for setup, and sudo. Run one experiment at a time.
Only virtual clocks are adjusted; the operating system clock stays unchanged.

## Get the final version

```bash
cd ~
git clone --branch final https://github.com/Annadata-Aniketh/Network-Time-Sync.git
cd Network-Time-Sync
```

For an existing clean clone, use `git switch final` and `git pull --ff-only`.
Preserve any local changes before updating.

## Before presenting

```bash
./timesync setup
./timesync doctor
./timesync test
```

Setup installs Mininet, Open vSwitch, iperf v2, and the pinned Python dependencies
in `.venv`. The default launcher also performs setup when needed. `doctor`
checks the local environment; the experiment checks all 30 directed host pairs
after starting its network. Rehearse the comparison and recovery once on the VM.

## Present from the menu

```bash
./timesync
```

Keep 60 seconds per mode; the comparison runs baseline and optimized in sequence.
Allow additional time for controller startup and connectivity checks.

| Key | Action |
| --- | --- |
| `i` | Explain the four timestamps and virtual clocks. Enter advances, `b` goes back, `q` returns. |
| `4` | Run both policies through normal traffic, congestion, then delay and jitter. |
| `5` | Generate plots; press Enter to use the latest comparison. |
| `6` | Show that comparison's summary. |
| `9` | Run the separate recovery experiment: normal, load, then load stopped. |
| `0` | Exit. |

Show the comparison plots before starting recovery, because recovery becomes the
latest run. The recovery summary appears after option `9`; option `6` can show it
again. Recovery has its own PASS/FAIL checks and is not a comparison plot input.

## Run without the menu

```bash
./timesync --batch --scenario both --duration 60
./timesync --batch --scenario recovery --duration 60
```

Each command prints its results directory under `evaluation/runs/`. For a
completed comparison, replace `<run>` with that directory's name:

```bash
.venv/bin/python -m evaluation.plot_results --data-dir evaluation/runs/<run>
```

Plots go to the run's `plots/` folder; the summary is `summary_metrics.md`.
Recovery writes `recovery_check.json` and its own `summary_metrics.md`.

## Walkthrough, browser lab, and evidence

```bash
./timesync explain
./timesync web
```

The browser lab is at `http://localhost:8080`; Ctrl+C stops the local server.
It also works by opening `web/index.html` directly. These two modes work without
Mininet. The browser model tests need a separate Node.js installation:

```bash
node --test tests/clock-model.test.cjs
```

Recompute the preserved VM results or export fresh local measurements:

```bash
.venv/bin/python -m evaluation.audit_results
sudo bash scripts/export_results.sh
```

The audit writes to `evaluation/runs/audit/`; it does not replace the reference
archive. Export needs at least one completed `both` comparison and prints the
archive path in the repository's parent directory.

## If a rehearsal fails

- Run `./timesync doctor` and inspect the failed run's `controller.log`,
  `connectivity.txt`, client logs, and flow snapshots.
- Port 6653 must be free. Stop the old controller before starting another run.
- After a crashed experiment, run `sudo mn -c` once no other Mininet experiment
  is running, then retry. Ctrl+C normally invokes cleanup automatically.
- Use `./timesync setup` to retry dependency installation. If `.venv` was made on
  another OS or Python version, rename it and rerun setup inside the Linux VM.

Explain the metrics accurately: RTT uses successful replies; clock error is
sampled after each attempt; timeouts are failed attempts rather than measured
network packet loss. The optimized policy changes queue treatment and routing
together, and Path B has higher capacity. The protocol is custom UDP using
NTP-style calculations, not a complete NTP implementation.
