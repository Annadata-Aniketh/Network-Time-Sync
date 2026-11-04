# Security scope

TimeSync is a laboratory demonstration for isolated, trusted networks. It adjusts
virtual clocks and does not set operating system time. Its custom UDP packets
are not NTP-compatible and do not provide cryptographic authentication.

## Protections

- The reference server and Python traffic receiver bind to loopback by default.
  Remote use requires an explicit local interface address. The benchmark binds
  the time server to `10.0.0.1` inside its Mininet namespace.
- The OpenFlow controller launcher listens on `127.0.0.1`; the supplied topology
  connects locally. The browser server also listens only on loopback.
- The server rejects wrong-size, non-finite, and non-request datagrams before
  allocating a worker task. Oversized datagrams are rejected even when truncated
  by the receive buffer. Invalid datagrams are counted without logging each one.
- A semaphore limits active plus queued requests to 128 by default. Excess UDP
  requests are dropped. Worker completion or failure releases admission capacity.
  The `--max-pending` option must be at least the worker count.
- The standalone client checks the sender IP and UDP port, response type, client
  ID, sequence, and echoed send timestamp before correcting its clock. The
  benchmark uses a connected UDP socket and the same packet-field checks.
- Traffic rates, durations, clock settings, and polling intervals reject invalid
  or non-finite values. Fractional iperf durations round up to one second and have
  a subprocess deadline; fractional rates remain fractional.
- Topology commands use argument lists rather than a shell. The reference audit
  rejects unexpected archive member types and extracts with Python's data filter.

## Review and dependency checks

Run the commands in [testing instructions](docs/TESTING.md) to repeat Ruff,
ESLint, ShellCheck, Bandit, `pip-audit`, and `npm audit`. Audits report known
advisories at the time they run; they do not establish absence of all defects.

The development lockfile overrides `minimatch` to 11.0.4 because its earlier
versions were affected by [GHSA-g3hv-75wg-m249](https://github.com/advisories/GHSA-g3hv-75wg-m249).
The override is exercised by the ESLint check. There are no browser runtime npm
dependencies. No vulnerability IDs are suppressed in the dependency audits.

Bandit's low-severity findings concern importing subprocess, executing argument
lists, and looking up Linux tools on PATH. These are required for Mininet/OVS and
were reviewed as trusted local command execution. Medium/high findings remain a
failing check; tests and temporary build directories are outside the source scan.

## Remaining boundaries

An attacker able to spoof the configured server, observe the local network, or
modify the controller can falsify timing. Sender checks are not authentication.
A flood can still consume network bandwidth and cause lost UDP requests even
though the worker queue is bounded. The application does not guarantee delivery
or fairness under overload.

Keep the controller and UDP services on the trusted experiment network. Mininet
and traffic-control operations require root; do not run untrusted checkouts or
alter PATH to include untrusted executables before invoking the launcher.
Historical measurements and the academic report remain snapshots of their
recorded source revisions. See [final verification](docs/VERIFICATION.md) for the
current checks and their evidence.
