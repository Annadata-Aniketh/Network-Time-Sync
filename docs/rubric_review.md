# Rubric review

Reviewed against `Reference docs/SDN-Socket Programming-Guidelines_Rubrics.pdf`
(two pages) and `Team 11 - Network Time Synchronization System Project Guide.pdf`
(six pages). This is an evidence checklist, not a predicted mark.

## Coverage

| Deliverable | Marks | Current coverage | Evidence still needed |
| --- | ---: | --- | --- |
| D1: Problem and architecture | 2 | Protocol, topology, objectives, and communication flow documented | Confirm diagrams match final VM implementation |
| D1: UDP sockets | 4 | Binary request/reply, concurrent server, virtual clocks, timeout logging | Screenshots show three client reply counters; inspect raw client logs |
| D1: Mininet + SDN | 4 | Four-switch diamond, fixed addressing, OpenFlow controller, queue configuration | VM reports 30/30 connectivity and queue setup; inspect raw qdisc/queue dumps |
| D1: Socket–SDN integration | 3 | Persistent client processes inside host namespaces; UDP classification | Flow counters or packet capture showing application traffic on the selected path |
| D1: Initial tests and demo | 2 | Protocol/clock/socket tests and menu available | Comparisons completed in VM; raw logs pending |
| D2: Complete application | 4 | Three drifting virtual clocks, periodic correction, structured CSV logs | Verify all clients complete and inspect failures |
| D2: Dynamic SDN | 6 | Load-based rerouting, queue assignment, three-poll recovery | Reroute counter and recovery PASS screenshots supplied; inspect raw dumps |
| D2: Challenging scenario | 4 | 12 Mbps offered load plus forward delay/jitter | Verify iperf delivery, `tc` settings, and behavior under impairment |
| D2: Performance comparison | 5 | Matched baseline/optimized schedule; RTT, jitter, error, failures, convergence plots | Three repeated summaries supplied; inspect raw measurements |
| D2: Docs, demo, viva | 6 | README, interactive demo, code map, explanation below | Final architecture/report and presentation; individual walkthrough |

The user has supplied VM screenshots of completed comparisons and automatic
recovery. See [the validation record](vm_validation.md) and
[the report draft](project_report.md). Raw VM logs/CSVs still need transfer and
review. The report draft is available; final report exports and presentation
remain unfinished. Legacy charts are not used as current VM evidence.

## Problems addressed on this branch

- The old benchmark imported `CustomTopo`, which does not exist. It now uses
  `TimeSyncTopo`, preserving the controller's fixed IP/MAC/port plan.
- It passed `sdn_optimized` while the controller starts monitoring only for
  `optimized`. Runtime modes are now `baseline` and `optimized` throughout.
- Queue setup was not called. The optimized benchmark now requires successful
  configuration. Queue actions are restricted to the two configured edge ports.
- Every sample previously spawned a Python process, including its startup time
  in RTT. Persistent host processes now timestamp actual socket exchanges.
- Timeouts were recorded as made-up 150 ms RTT and 50 ms jitter. They now have
  explicit status and missing delay fields; summaries report the failure rate.
- Flow deletion did not restrict priority in OpenFlow's non-strict delete mode.
  Cookies now isolate reroute rules so restoring Path A preserves base rules.
- Recovery polls did not reset when load rose again. They now must be consecutive.
- Impairment previously replaced root qdiscs on both directions. It now targets
  the forward interface through Mininet's traffic-control configuration with a
  retained bandwidth setting. Inspect the resulting qdisc tree in the VM.
- Background load now lasts through the impaired phase at every chosen duration.
- The macOS/local proxy fallback was removed. Runs require Linux, root, Mininet,
  OVS, iperf, and an importable OS-Ken runtime.
- The README and plotting code no longer promise fixed improvements, sub-ms
  accuracy, or a reroute timestamp that was never measured.

## Linux VM acceptance checklist

1. Record the VM OS, Python, OS-Ken, Mininet, and OVS versions. Run the menu's
   environment check. Controller/Eventlet compatibility with that Python must be verified;
   installing packages alone does not establish controller functionality.
2. Run all tests. Then run the baseline and optimized comparison for 60 seconds
   per scenario. Inspect every client's log for successful replies in all phases.
3. Inspect phase flow dumps: baseline stays on Path A; optimized adds priority-200
   sync rules on s1/s3/s4 under load, with increasing packet counters. Check the
   controller logs for the actual trigger. Confirm queue 1/2 on the edge ports.
4. Inspect iperf logs for actual load. During phase 3, use `tc -s qdisc show dev
   s2-eth2` to confirm delay/jitter and the bandwidth hierarchy. Confirm that OVS
   QoS and TCLink shaping coexist as intended in this VM.
5. Select menu option 9 for the separate automatic recovery test. It runs normal
   traffic, adds background load, then stops the load. Check the PASS/FAIL summary
   and `recovery_check.json`: Path B must carry sync requests under load, the
   priority-200 rules must disappear, and the Path A request counter must increase
   afterward. The standard comparison keeps load active until the end and does
   not exercise this recovery cycle.
6. Generate plots from the completed run directory. Check failures and phase-wise
   behavior, repeat the comparison, and report actual results with VM details.
7. Assemble the reports/slides with the final diagram, protocol, screenshots,
   measured results, limitations, and each member's contribution.

## Walkthrough for the viva

Follow a single packet: the client records t0, s1 identifies UDP 12300, switches
forward it to the server, the server records t1/t2, and the client records t3.
Explain the two equations and why unequal directional delay biases the estimate.
Show that only virtual time changes.

Then introduce background traffic. Explain queue 1 versus queue 2, how byte-counter
differences become Mbps, and why 4 Mbps is a load policy rather than measured
latency. Show the changed flow rules and packet counters. Use the CSV to connect
network behavior to measured clock error. State that QoS and rerouting are tested
together and that a faster alternate path is part of this topology.

For limitations, explain UDP loss, the symmetric-delay assumption, step corrections,
shared-clock ground truth, large artificial drift rates, scheduler timing, and
why these results do not establish production NTP accuracy.

## Controller runtime update

OS-Ken 2.11.2 replaces the unmaintained Ryu package to avoid its Setuptools
installation hook. Controller imports and launcher use `os_ken`; the OpenFlow
policy is unchanged. Eventlet is updated for Python 3.12. OS-Ken is a Ryu fork,
so describe that runtime choice explicitly in the final documentation.
