# TimeSync

A UDP clock synchronization experiment with a network you can watch and explain.
Three clients correct drifting virtual clocks against a reference server. Compare
ordinary forwarding with prioritized traffic and automatic path changes under load.

## Start in the Linux VM

Use an Ubuntu or Debian-based VM with Python 3, Git, and sudo access.

```bash
git clone https://github.com/Annadata-Aniketh/Network-Time-Sync.git
cd Network-Time-Sync
sudo bash scripts/setup_env.sh
sudo bash scripts/run_demo.sh
```

Setup installs Mininet, Open vSwitch, iperf, and the project's Python environment.
OS-Ken provides the OpenFlow 1.3 controller. The experiment changes virtual client
clocks; your machine's system time stays unchanged.

## Terminal controls

| Key | Action |
| --- | --- |
| `1` | Check the VM environment |
| `2` / `3` | Run baseline / optimized mode |
| `4` | Compare both modes |
| `5` / `6` | Generate plots / read results |
| `7` | Change duration; default is 60 seconds per mode |
| `8` | Run tests |
| `9` | Verify automatic recovery after load stops |
| `i` | Animated explanation of the protocol and paths |
| `h` | Ten-minute demo guide |
| `w` | Show website instructions |
| `0` | Exit |

During an interactive experiment, the terminal shows the phase, elapsed time,
latest measurements for each client, and the route reported by the controller.
The `i` walkthrough is an illustration; it is separate from the real experiment.
Colors respect `NO_COLOR`, and redirected output stays plain.

## Animated explainer

Open **`web/index.html`** in your browser. It works offline, without installation.
For a local server instead:

```bash
python3 -m http.server 8080 --bind 127.0.0.1 --directory web
```

Visit [localhost:8080](http://localhost:8080). Follow six animated chapters, switch
between baseline and optimized policy, and change directional delay to explore
the timestamp equations. A separate evidence section shows recorded VM results.
The page is a concept explanation, not a live connection to Mininet.

## A ten-minute demo

1. **0–2 min:** explain clock drift, the four timestamps, and the two paths using
   terminal option `i` or the website.
2. **2–5 min:** select `4`. Narrate normal traffic, congestion, and link impairment
   as the live measurements update.
3. **5–7 min:** select `5`, then `6`. Explain clock error, RTT, and failed samples.
4. **7–9 min:** select `9`. The load stops; verify the return to Path A.
5. **9–10 min:** show the PASS checks and discuss the measurement limits.

Allow for VM startup overhead. Keep the 60-second default; rehearse once before
presenting. The menu starts nothing until you select an action.

## What the experiment does

```text
                     Path A · 10 Mbps
                  ┌───── s2 ─────┐
clients + load ── s1              s4 ── reference + sink
                  └───── s3 ─────┘
                     Path B · 50 Mbps
```

Time-sync requests and replies use UDP port **12300**; background load uses UDP
port **5001**. The controller connection uses TCP **6653**. Connectivity probes
use ICMP, independently of the application protocol.

Each comparison mode runs three equal phases:

| Default time | Condition |
| --- | --- |
| 0–20 s | Three drifting clients synchronize normally |
| 20–40 s | Add UDP background traffic with `iperf -b 12M` |
| 40–60 s | Retain the load; add 50 ms delay and 15 ms jitter to Path A |

Baseline stays on Path A. Optimized mode gives sync traffic a dedicated queue,
caps background traffic at 6 Mbps, and reroutes sync traffic to Path B when s1's
primary uplink reaches 4 Mbps. It polls every two seconds. Three successive polls
below the threshold restore Path A. Settings are in `sdn/flow_rules.json`.

Recovery (`9`) is a separate 60-second test: normal, load, then load stopped.
It adds no link impairment and never manually restores flow rules. A PASS requires
observed Path B packets, removal of reroute rules, an increasing Path A request
counter, and replies to all three clients during recovery.

## Results

Each run saves a new directory under `evaluation/runs/`. It contains `run.json`,
client CSVs, controller and traffic logs, connectivity checks, and flow snapshots.
Generate plots with `5`; use `6` to display the summary. Press Enter to select the
current run, or enter the directory of an earlier one.

Clock error is measured immediately after correction, not continuously between
requests. RTT uses successful replies only; timeouts and invalid replies are
counted separately. The baseline and optimized test combine queue treatment and
routing changes, and the alternate path has more capacity.

Recorded reference evidence is preserved under `evaluation/reference/`: five
comparisons and one recovery run. The explainer's results come from that archive.
Recompute its audit with:

```bash
.venv/bin/python -m evaluation.audit_results
```

To review and package new VM results:

```bash
sudo bash scripts/export_results.sh
```

## Commands without the menu

```bash
sudo bash scripts/run_demo.sh --batch --scenario both --duration 60
sudo bash scripts/run_demo.sh --batch --scenario recovery --duration 60
python3 -m scripts.demo --explain
.venv/bin/python -m evaluation.plot_results --data-dir evaluation/runs/<run>
.venv/bin/python -m unittest discover -s tests -v
```

Use `--scenario baseline` or `--scenario optimized` for an individual mode.
Other flags: `--interval 0.5`, `--output-dir /path/to/empty-directory`, `--no-color`.
Root-owned result directories may require `sudo` when generating plots directly.

## Troubleshooting

- Run experiments with `sudo` inside the Linux VM. Open vSwitch must be running.
- Run one experiment at a time. If port 6653 is occupied, stop the old controller.
- After an interrupted or crashed run, use `sudo mn -c` before retrying.
- Setup retries slow dependency downloads. If it fails, check the VM connection
  and the actual error before starting a run.
- Inspect `controller.log`, `connectivity.txt`, and startup flow dumps in a failed
  run's directory. Ctrl+C stops the experiment and cleans up its network.

## Layout

`app/` contains UDP messages and clocks, `sdn/` the controller, `topology/` the
network, `evaluation/` experiments and evidence, `scripts/` the terminal tools,
and `web/` the offline explainer. `docs/` holds the retained reference files.
