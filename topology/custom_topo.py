#!/usr/bin/env python3
"""Build the six-host OpenFlow diamond network and its traffic-control settings."""

import argparse
import logging
import subprocess
import sys

try:
    from mininet.cli import CLI
    from mininet.link import TCLink
    from mininet.log import info, setLogLevel, warn
    from mininet.net import Mininet
    from mininet.node import OVSSwitch, RemoteController
    from mininet.topo import Topo
except ImportError:

    class Topo:
        def __init__(self, *args, **kwargs):
            self.switches_dict = {}
            self.hosts_dict = {}
            self.links_list = []
            self.ports = {}
            self.build(*args, **kwargs)

        def addSwitch(self, name, **opts):
            self.switches_dict[name] = opts
            return name

        def addHost(self, name, **opts):
            self.hosts_dict[name] = opts
            return name

        def addLink(self, node1, node2, port1=None, port2=None, **opts):
            self.links_list.append(
                {"node1": node1, "node2": node2, "port1": port1, "port2": port2, "opts": opts}
            )
            self.ports.setdefault(node1, {})[node2] = port1
            self.ports.setdefault(node2, {})[node1] = port2
            return (node1, node2)

        def switches(self):
            return list(self.switches_dict.keys())

        def hosts(self):
            return list(self.hosts_dict.keys())

        def links(self, *args, **kwargs):
            return [(link["node1"], link["node2"]) for link in self.links_list]

    Mininet = None
    RemoteController = None
    OVSSwitch = None
    TCLink = None
    CLI = None

    def setLogLevel(lvl):
        return None

    def info(*args):
        return print(*args)

    def warn(*args):
        return print(*args, file=sys.stderr)


class TimeSyncTopo(Topo):
    """OpenFlow 1.3 4-switch diamond topology with deterministic switch ports."""

    def build(self, **opts):

        s1 = self.addSwitch("s1", dpid="0000000000000001", protocols="OpenFlow13")
        s2 = self.addSwitch("s2", dpid="0000000000000002", protocols="OpenFlow13")
        s3 = self.addSwitch("s3", dpid="0000000000000003", protocols="OpenFlow13")
        s4 = self.addSwitch("s4", dpid="0000000000000004", protocols="OpenFlow13")

        h_server = self.addHost("h_server", ip="10.0.0.1/24", mac="00:00:00:00:00:01")
        h_sink = self.addHost("h_sink", ip="10.0.0.2/24", mac="00:00:00:00:00:02")

        h_client1 = self.addHost("h_client1", ip="10.0.0.11/24", mac="00:00:00:00:00:11")
        h_client2 = self.addHost("h_client2", ip="10.0.0.12/24", mac="00:00:00:00:00:12")
        h_client3 = self.addHost("h_client3", ip="10.0.0.13/24", mac="00:00:00:00:00:13")
        h_load = self.addHost("h_load", ip="10.0.0.20/24", mac="00:00:00:00:00:20")

        # HFSC shapes link rates; OVS separately manages the application HTB queues.

        self.addLink(
            s1,
            h_client1,
            port1=1,
            cls=TCLink,
            use_hfsc=True,
            bw=100,
            delay="1ms",
            max_queue_size=1000,
        )
        self.addLink(
            s1,
            h_client2,
            port1=2,
            cls=TCLink,
            use_hfsc=True,
            bw=100,
            delay="1ms",
            max_queue_size=1000,
        )
        self.addLink(
            s1,
            h_client3,
            port1=3,
            cls=TCLink,
            use_hfsc=True,
            bw=100,
            delay="1ms",
            max_queue_size=1000,
        )
        self.addLink(
            s1, h_load, port1=4, cls=TCLink, use_hfsc=True, bw=100, delay="1ms", max_queue_size=1000
        )

        self.addLink(
            s4,
            h_server,
            port1=1,
            cls=TCLink,
            use_hfsc=True,
            bw=100,
            delay="1ms",
            max_queue_size=1000,
        )
        self.addLink(
            s4, h_sink, port1=2, cls=TCLink, use_hfsc=True, bw=100, delay="1ms", max_queue_size=1000
        )

        self.addLink(
            s1,
            s2,
            port1=5,
            port2=1,
            cls=TCLink,
            use_hfsc=True,
            bw=10,
            delay="2ms",
            max_queue_size=100,
        )

        self.addLink(
            s2,
            s4,
            port1=2,
            port2=5,
            cls=TCLink,
            use_hfsc=True,
            bw=10,
            delay="2ms",
            max_queue_size=100,
        )

        self.addLink(
            s1,
            s3,
            port1=6,
            port2=1,
            cls=TCLink,
            use_hfsc=True,
            bw=50,
            delay="2ms",
            max_queue_size=1000,
        )

        self.addLink(
            s3,
            s4,
            port1=2,
            port2=6,
            cls=TCLink,
            use_hfsc=True,
            bw=50,
            delay="2ms",
            max_queue_size=1000,
        )


def _run_cmd(cmd: list[str]):
    """Run an argument list and return its exit code, stdout, and stderr."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, check=False)
        return proc.returncode, proc.stdout, proc.stderr
    except OSError as exc:
        return -1, "", str(exc)


def setup_qos_queues(net=None):
    """Configure HTB queues on the two Path A edge egress ports."""
    ports = ["s1-eth5", "s4-eth5"]

    success = True

    for port in ports:
        _run_cmd(["ovs-vsctl", "--if-exists", "clear", "Port", port, "qos"])

        cmd = (
            f"ovs-vsctl -- set Port {port} qos=@newqos "
            f"-- --id=@newqos create QoS type=linux-htb other-config:max-rate=10000000 "
            f"queues=0=@q0,1=@q1,2=@q2 "
            f"-- --id=@q0 create Queue other-config:min-rate=1000000 other-config:max-rate=10000000 "
            f"-- --id=@q1 create Queue other-config:min-rate=2000000 other-config:max-rate=10000000 other-config:priority=1 "
            f"-- --id=@q2 create Queue other-config:min-rate=1000000 other-config:max-rate=6000000 other-config:priority=10"
        )
        code, _, err = _run_cmd(cmd.split())
        if code == 0:
            logging.info("QoS ready on %s: default / sync / background queues", port)
        else:
            print(
                f"[QoS Warning] Failed to configure QoS on {port}: {err.strip()}", file=sys.stderr
            )
            success = False

    return success


def inject_link_impairment(
    net=None, delay_ms: int = 50, jitter_ms: int = 15, loss_pct: float = 0.0
):
    """Delay the forward Path A egress while retaining its 10 Mbps limit."""
    if net is None:
        raise ValueError("A running Mininet network is required")
    result = (
        net.get("s2")
        .intf("s2-eth2")
        .config(
            bw=10,
            use_hfsc=True,
            delay=f"{delay_ms}ms",
            jitter=f"{jitter_ms}ms",
            loss=loss_pct,
            max_queue_size=100,
        )
    )
    if result.get("tcoutputs") and any(result["tcoutputs"]):
        raise RuntimeError(f"Could not apply link impairment: {result['tcoutputs']}")


def clear_link_impairment(net=None):
    """Restore the impaired egress to its original 10 Mbps, 2 ms link settings."""

    inject_link_impairment(net, delay_ms=2, jitter_ms=0, loss_pct=0.0)


def create_network(
    controller_ip: str = "127.0.0.1", controller_port: int = 6653, enable_qos: bool = True
):
    """Creates and starts the Mininet network."""
    if Mininet is None:
        raise RuntimeError("Mininet is not installed in this environment. Run inside Mininet VM.")

    topo = TimeSyncTopo()
    net = Mininet(
        topo=topo,
        controller=lambda name: RemoteController(name, ip=controller_ip, port=controller_port),
        switch=OVSSwitch,
        link=TCLink,
        autoSetMacs=False,
    )

    info("*** Starting Mininet network...\n")
    net.start()

    if enable_qos:
        info("*** Initializing OVS HTB QoS queues on Path A egress ports...\n")
        setup_qos_queues(net)

    hosts_dict = {h.name: h for h in net.hosts}
    return net, hosts_dict


def start_topology(
    mode: str = "optimized",
    cli: bool = False,
    controller_ip: str = "127.0.0.1",
    controller_port: int = 6653,
):
    """Convenience launcher for standalone testing and benchmark integration."""
    enable_qos = mode == "optimized"
    net, hosts = create_network(
        controller_ip=controller_ip, controller_port=controller_port, enable_qos=enable_qos
    )

    if cli:
        info(f"*** Network Time Sync topology active in '{mode}' mode. Starting CLI...\n")
        CLI(net)
        info("*** Stopping Mininet network...\n")
        net.stop()

    return net, hosts


topos = {"timesynctopo": lambda: TimeSyncTopo()}

if __name__ == "__main__":
    setLogLevel("info")
    parser = argparse.ArgumentParser(
        description="Multi-path Mininet Topology for Time Sync (Team 11)"
    )
    parser.add_argument("--test-cli", action="store_true", help="Start interactive Mininet CLI")
    parser.add_argument(
        "--mode",
        choices=["baseline", "optimized"],
        default="optimized",
        help="Topology mode: 'baseline' (no QoS) or 'optimized' (with OVS HTB QoS)",
    )
    parser.add_argument(
        "--controller-ip", default="127.0.0.1", help="Controller IP (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--controller-port", type=int, default=6653, help="Controller Port (default: 6653)"
    )

    args = parser.parse_args()
    start_topology(
        mode=args.mode,
        cli=True,
        controller_ip=args.controller_ip,
        controller_port=args.controller_port,
    )
