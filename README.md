# Network Time Synchronization

Synchronize drifting clocks over UDP and see how network congestion affects their
accuracy. Run the same experiment with ordinary forwarding and with a network
controller that prioritizes time-sync packets and moves them to a less busy path.

The experiment runs inside a Linux VM. Clients use virtual clocks, so your VM's
system time stays unchanged.

## Get started

You'll need an Ubuntu or Debian-based Linux VM with Python 3, Git, an internet
connection for setup, and sudo access. Mininet creates the virtual network;
Open vSwitch forwards packets, and OS-Ken controls their paths.

Clone the repository inside the VM:

```bash
git clone https://github.com/Annadata-Aniketh/Network-Time-Sync.git
cd Network-Time-Sync
```

Install dependencies, then open the terminal menu:

```bash
sudo bash scripts/setup_env.sh
sudo bash scripts/run_demo.sh
```

Setup installs the network tools and creates a Python environment in `.venv`.
The controller uses OS-Ken, a fork of Ryu, with a Python 3.12-compatible Eventlet
release. Run the environment check before starting your first experiment.

## Try your first comparison

In the menu:

1. Select **1 — Check environment** to check the required tools and services.
2. Select **4 — Run comparison** to run baseline and optimized modes.
3. When it finishes, select **5 — Generate plots**. Press Enter to use that run's
   results directory.
4. Select **6 — Show summary** and press Enter to read the comparison.
5. Select **0 — Exit** when you're done.

A comparison takes about two minutes, plus network startup and cleanup. You can
also run baseline or optimized mode separately, change the duration, or run tests.
Plots require a completed comparison containing both modes.

Each mode runs three phases:

| Time | What happens |
| --- | --- |
| 0–20 seconds | Three clients synchronize with the reference server. |
| 20–40 seconds | Background traffic loads the primary path. |
| 40–60 seconds | Background traffic continues, with added delay and jitter. |

**Baseline** keeps packets on the primary path. **Optimized** gives time-sync
packets a dedicated bandwidth queue and switches them to the alternate path when
primary-path traffic exceeds the configured threshold. Compare the measured
clock error, round-trip delay, and jitter to see the effect.

## Check automatic recovery

Select **9 — Test automatic recovery** in the menu. Keep the duration at 60
seconds or longer. This runs optimized mode with the following schedule:

| Time | Condition |
| --- | --- |
| 0–20 seconds | Normal synchronization on Path A |
| 20–40 seconds | UDP background load triggers rerouting to Path B |
| 40–60 seconds | Load stops; the controller should restore Path A automatically |

This test adds no link impairment. It checks the complete load-and-recovery
cycle independently from the comparison experiment. A PASS requires packets on
Path B under load, removal of reroute rules, an increasing sync request counter
on Path A after recovery, and successful replies to all three clients during
recovery. The runner does not manually restore any flow rules.

The result appears immediately and is saved in `summary_metrics.md` and
`recovery_check.json` in the new run directory. Select **6** to read it again.
Comparison plots from option 5 apply to comparison runs, not recovery runs.

To run this test directly:

```bash
sudo bash scripts/run_demo.sh --batch --scenario recovery --duration 60
```

## Find your results

Each run saves its output in `evaluation/runs/<timestamp>/`. The terminal prints
the exact directory.

| Output | Contents |
| --- | --- |
| `run.json` | Run settings and completion status |
| `baseline_metrics.csv` | Baseline client measurements |
| `sdn_optimized_metrics.csv` | Optimized client measurements |
| `baseline/`, `optimized/` | Client, controller, traffic and connectivity logs; network snapshots |
| `summary_metrics.md` | Comparison table, created when you generate plots |
| `plots/` | Clock error, round-trip delay distribution, and jitter charts |

Lower clock error means the client is closer to the reference time. Lower
round-trip delay means replies arrive faster. Lower jitter means delay varies
less between replies. Check the failure percentage too: missing replies are
reported separately rather than counted as successful measurements.

Clock error is measured immediately after each correction. It does not show the
drift accumulated between requests. Use a fresh run directory for your results;
the older files in `evaluation/data/` and `evaluation/plots/` have no recorded
runtime information.

## How it works

```text
                    primary path
                 ┌───── s2 ─────┐
clients ─────── s1              s4 ─────── reference server
                 └───── s3 ─────┘
                   alternate path
```

The background traffic hosts are named `h_load` and `h_sink` so their generated
interface names fit Linux's 15-character limit.

Three clients periodically exchange timestamps with the server over UDP port
12300. Each client estimates the network round-trip delay and its clock offset,
then adds the offset to its virtual clock.

The primary path has 10 Mbps core links; the alternate path has 50 Mbps core
links. In optimized mode, the controller checks primary-path traffic every two
seconds. At 4 Mbps or above, it moves time-sync traffic to the alternate path.
After three consecutive checks below that threshold, it restores the primary
path. Settings are in `sdn/flow_rules.json`.

## Run without the menu

```bash
# Run both modes and save measurements.
sudo bash scripts/run_demo.sh --batch --scenario both --duration 60

# Run just one mode.
sudo bash scripts/run_demo.sh --batch --scenario baseline --duration 60

# Generate plots from a completed comparison; replace the path with your run.
sudo .venv/bin/python -m evaluation.plot_results --data-dir evaluation/runs/<timestamp>
```

Use `--scenario optimized` for optimized mode only. Optional flags include
`--interval 0.5` for the sampling interval and `--output-dir /path/to/empty-directory`
for a custom results directory. The default duration is 60 seconds per mode.

## Troubleshooting

- **Root privileges required:** start the demo with `sudo` inside the Linux VM.
- **Controller port already in use:** stop the controller or experiment using
  port 6653, then retry. Run one experiment at a time.
- **Network state left after a crash:** run `sudo mn -c`, then restart the demo.
- **Missing tools or import errors:** check the setup output and select the
  environment check before retrying.
- **Package download timed out:** setup allows 120 seconds per socket operation
  and retries the dependency install up to three times. Check the VM's internet
  connection if all attempts fail, then rerun setup; cached downloads are reused.
- **Run fails:** inspect `controller.log` and the client or traffic logs in that
  run's directory. For connectivity failures, `connectivity.txt` lists each
  host pair and its ping output; `startup-*-flows.txt` contains the forwarding rules.

Press Ctrl+C to stop an experiment. The runner cleans up the processes and
virtual network it started.

## Export results

To review completed experiments and package their CSVs, logs, plots, and runtime
versions into one archive, run this inside the Linux VM:

```bash
sudo bash scripts/export_results.sh
```

The command prints the archive path. It also creates `evaluation/runs/review.md`,
which separates timeouts from invalid replies for each run and phase. Existing
measurements are retained.

## Development

Application code is in `app/`, network setup in `topology/`, and controller logic
in `sdn/`. The runner and plotting code live in `evaluation/`; the terminal menu
is in `scripts/demo.py`.

Run the tests:

```bash
.venv/bin/python -m unittest discover -s tests -v
```

The [technical report](docs/project_report.md) explains the implementation and
recorded VM results. The [presentation](docs/network-time-sync.pptx) provides an
editable walkthrough of the same evidence.
