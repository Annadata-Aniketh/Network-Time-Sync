#!/usr/bin/env python3
"""Control Path A forwarding, sync queues, and load-based rerouting."""

import json
import logging
import math
import os
import time

try:
    from os_ken.base import app_manager
    from os_ken.controller import ofp_event
    from os_ken.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
    from os_ken.lib import hub
    from os_ken.lib.packet import arp, ether_types, ethernet, ipv4, packet, tcp, udp
    from os_ken.ofproto import ofproto_v1_3
except ImportError:

    class app_manager:
        class OSKenApp:
            def __init__(self, *args, **kwargs):
                self.logger = logging.getLogger("SDNController")

    class ofp_event:
        class EventOFPSwitchFeatures:
            pass

        class EventOFPPacketIn:
            pass

        class EventOFPPortStatsReply:
            pass

    CONFIG_DISPATCHER = "config"
    MAIN_DISPATCHER = "main"

    def set_ev_cls(*a, **k):
        return lambda f: f

    class ofproto_v1_3:
        OFP_VERSION = 0x04

    packet = ethernet = ether_types = arp = ipv4 = udp = tcp = None

    class hub:
        @staticmethod
        def spawn(func, *args, **kwargs):
            return None

        @staticmethod
        def sleep(sec):
            time.sleep(sec)


DEFAULT_SYNC_PORT = 12300
DEFAULT_BG_PORT = 5001
DEFAULT_THRESHOLD_MBPS = 4.0
DEFAULT_POLL_INTERVAL = 2.0

HOST_MAP = {
    "10.0.0.1": {"mac": "00:00:00:00:00:01", "dpid": 4, "port": 1, "name": "h_server"},
    "10.0.0.2": {"mac": "00:00:00:00:00:02", "dpid": 4, "port": 2, "name": "h_sink"},
    "10.0.0.11": {"mac": "00:00:00:00:00:11", "dpid": 1, "port": 1, "name": "h_client1"},
    "10.0.0.12": {"mac": "00:00:00:00:00:12", "dpid": 1, "port": 2, "name": "h_client2"},
    "10.0.0.13": {"mac": "00:00:00:00:00:13", "dpid": 1, "port": 3, "name": "h_client3"},
    "10.0.0.20": {"mac": "00:00:00:00:00:20", "dpid": 1, "port": 4, "name": "h_load"},
}


class TimeSyncSDNController(app_manager.OSKenApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    HOST_MAP = HOST_MAP

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not hasattr(self, "logger") or self.logger is None:
            self.logger = logging.getLogger("SDNController")
        self.logger.setLevel(logging.INFO)

        self.config = self._load_configuration()
        self.sync_udp_port = self.config.get("sync_udp_port", DEFAULT_SYNC_PORT)
        self.bg_port = self.config.get("bg_port", DEFAULT_BG_PORT)
        self.congestion_threshold_mbps = float(
            self.config.get("congestion_threshold_mbps", DEFAULT_THRESHOLD_MBPS)
        )
        self.poll_interval_sec = float(self.config.get("poll_interval_sec", DEFAULT_POLL_INTERVAL))
        self.qos_queues = self.config.get(
            "qos_queues", {"high_priority_sync": 1, "low_priority_bg": 2, "default": 0}
        )

        self.mode = os.environ.get("SDN_MODE", "optimized").lower().strip()
        if self.mode not in {"baseline", "optimized"}:
            raise ValueError("SDN_MODE must be baseline or optimized")
        if not all(
            math.isfinite(value) and value > 0
            for value in (self.congestion_threshold_mbps, self.poll_interval_sec)
        ):
            raise ValueError("Threshold and polling interval must be positive and finite")
        self.logger.info(f"Initialized TimeSyncSDNController [Mode: {self.mode}]")
        self.logger.info(
            f"Policy: Time-Sync Port={self.sync_udp_port}, BG Port={self.bg_port}, "
            f"Threshold={self.congestion_threshold_mbps} Mbps, Poll={self.poll_interval_sec}s"
        )

        self.datapaths = {}

        self.port_stats = {}

        self.is_rerouted = False
        self.low_congestion_count = 0
        self.monitor_started = False

    def _load_configuration(self):
        """Loads policy settings from flow_rules.json with fallbacks."""
        candidates = [
            os.path.join(os.path.dirname(__file__), "flow_rules.json"),
            os.path.join(os.getcwd(), "sdn", "flow_rules.json"),
            os.path.join(os.getcwd(), "flow_rules.json"),
        ]
        for p in candidates:
            if os.path.exists(p):
                try:
                    with open(p) as f:
                        cfg = json.load(f)
                        self.logger.info(f"Loaded flow rules configuration from: {p}")
                        return cfg
                except (OSError, ValueError) as exc:
                    self.logger.warning(f"Error reading {p}: {exc}")
        return {
            "sync_udp_port": DEFAULT_SYNC_PORT,
            "bg_port": DEFAULT_BG_PORT,
            "congestion_threshold_mbps": DEFAULT_THRESHOLD_MBPS,
            "poll_interval_sec": DEFAULT_POLL_INTERVAL,
            "qos_queues": {"high_priority_sync": 1, "low_priority_bg": 2, "default": 0},
            "paths": {"path_a_switches": [1, 2, 4], "path_b_switches": [1, 3, 4]},
        }

    def add_flow(
        self,
        datapath,
        priority: int,
        match,
        actions,
        buffer_id=None,
        idle_timeout=0,
        hard_timeout=0,
    ):
        """Installs an OpenFlow 1.3 FlowMod rule on datapath."""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        inst = [parser.OFPInstructionActions(ofproto.OFPIT_APPLY_ACTIONS, actions)]
        kwargs = {
            "datapath": datapath,
            # Tag each rule group so recovery deletes only reroute rules.
            "cookie": priority,
            "priority": priority,
            "match": match,
            "instructions": inst,
            "idle_timeout": idle_timeout,
            "hard_timeout": hard_timeout,
        }
        if buffer_id is not None and buffer_id != ofproto.OFP_NO_BUFFER:
            kwargs["buffer_id"] = buffer_id
        datapath.send_msg(parser.OFPFlowMod(**kwargs))

    def del_flow(self, datapath, priority: int, match):
        """Deletes matching OpenFlow 1.3 FlowMod rules from datapath."""
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        mod = parser.OFPFlowMod(
            datapath=datapath,
            command=ofproto.OFPFC_DELETE,
            cookie=priority,
            cookie_mask=0xFFFFFFFFFFFFFFFF,
            out_port=ofproto.OFPP_ANY,
            out_group=ofproto.OFPG_ANY,
            priority=priority,
            match=match,
        )
        datapath.send_msg(mod)

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Handles switch connection, handshake, table-miss rule, and proactive rules."""
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id

        self.datapaths[dpid] = datapath
        self.logger.info(f"Switch connected: DPID={dpid} (0x{dpid:016x})")

        match_miss = parser.OFPMatch()
        actions_miss = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, priority=0, match=match_miss, actions=actions_miss)

        if self.mode == "baseline":
            self._install_baseline_flows(datapath)
        else:
            self._install_optimized_flows(datapath)

        if self.mode == "optimized" and not self.monitor_started:
            self.monitor_started = True
            hub.spawn(self._monitor_loop)
            self.logger.info("SDN real-time port monitoring thread started (hub.spawn).")

    def _install_baseline_flows(self, datapath):
        """Baseline Mode: All traffic routed over Path A in default Queue 0 without QoS."""
        parser = datapath.ofproto_parser
        dpid = datapath.id

        if dpid == 1:
            for srv_ip in ["10.0.0.1", "10.0.0.2"]:
                self.add_flow(
                    datapath,
                    10,
                    parser.OFPMatch(eth_type=0x0800, ipv4_dst=srv_ip),
                    [parser.OFPActionOutput(5)],
                )
            for cip, port in [
                ("10.0.0.11", 1),
                ("10.0.0.12", 2),
                ("10.0.0.13", 3),
                ("10.0.0.20", 4),
            ]:
                self.add_flow(
                    datapath,
                    10,
                    parser.OFPMatch(eth_type=0x0800, ipv4_dst=cip),
                    [parser.OFPActionOutput(port)],
                )
        elif dpid == 2:
            self.add_flow(datapath, 10, parser.OFPMatch(in_port=1), [parser.OFPActionOutput(2)])
            self.add_flow(datapath, 10, parser.OFPMatch(in_port=2), [parser.OFPActionOutput(1)])
        elif dpid == 4:
            self.add_flow(
                datapath,
                10,
                parser.OFPMatch(eth_type=0x0800, ipv4_dst="10.0.0.1"),
                [parser.OFPActionOutput(1)],
            )
            self.add_flow(
                datapath,
                10,
                parser.OFPMatch(eth_type=0x0800, ipv4_dst="10.0.0.2"),
                [parser.OFPActionOutput(2)],
            )
            for cip in ["10.0.0.11", "10.0.0.12", "10.0.0.13", "10.0.0.20"]:
                self.add_flow(
                    datapath,
                    10,
                    parser.OFPMatch(eth_type=0x0800, ipv4_dst=cip),
                    [parser.OFPActionOutput(5)],
                )

    def _install_optimized_flows(self, datapath):
        """Optimized Mode: Microflow classification, HTB QoS queues, and initial Path A routing."""
        parser = datapath.ofproto_parser
        dpid = datapath.id
        q_sync = self.qos_queues.get("high_priority_sync", 1)
        q_bg = self.qos_queues.get("low_priority_bg", 2)

        self._install_baseline_flows(datapath)

        if dpid == 3:
            self.add_flow(datapath, 10, parser.OFPMatch(in_port=1), [parser.OFPActionOutput(2)])
            self.add_flow(datapath, 10, parser.OFPMatch(in_port=2), [parser.OFPActionOutput(1)])

        if dpid == 1:
            m_fwd = parser.OFPMatch(eth_type=0x0800, ip_proto=17, udp_dst=self.sync_udp_port)
            self.add_flow(
                datapath, 100, m_fwd, [parser.OFPActionSetQueue(q_sync), parser.OFPActionOutput(5)]
            )

            for cip, port in [("10.0.0.11", 1), ("10.0.0.12", 2), ("10.0.0.13", 3)]:
                m_rev = parser.OFPMatch(
                    eth_type=0x0800, ip_proto=17, udp_src=self.sync_udp_port, ipv4_dst=cip
                )
                self.add_flow(datapath, 100, m_rev, [parser.OFPActionOutput(port)])

        elif dpid == 2:
            m_fwd = parser.OFPMatch(eth_type=0x0800, ip_proto=17, udp_dst=self.sync_udp_port)
            self.add_flow(datapath, 100, m_fwd, [parser.OFPActionOutput(2)])

            m_rev = parser.OFPMatch(eth_type=0x0800, ip_proto=17, udp_src=self.sync_udp_port)
            self.add_flow(datapath, 100, m_rev, [parser.OFPActionOutput(1)])

        elif dpid == 4:
            m_fwd = parser.OFPMatch(
                eth_type=0x0800, ip_proto=17, udp_dst=self.sync_udp_port, ipv4_dst="10.0.0.1"
            )
            self.add_flow(datapath, 100, m_fwd, [parser.OFPActionOutput(1)])

            m_rev = parser.OFPMatch(eth_type=0x0800, ip_proto=17, udp_src=self.sync_udp_port)
            self.add_flow(
                datapath, 100, m_rev, [parser.OFPActionSetQueue(q_sync), parser.OFPActionOutput(5)]
            )

        if dpid == 1:
            m_udp_bg = parser.OFPMatch(eth_type=0x0800, ip_proto=17, udp_dst=self.bg_port)
            self.add_flow(
                datapath, 50, m_udp_bg, [parser.OFPActionSetQueue(q_bg), parser.OFPActionOutput(5)]
            )

            m_tcp_bg = parser.OFPMatch(eth_type=0x0800, ip_proto=6, tcp_dst=self.bg_port)
            self.add_flow(
                datapath, 50, m_tcp_bg, [parser.OFPActionSetQueue(q_bg), parser.OFPActionOutput(5)]
            )

        elif dpid == 2:
            m_udp_bg = parser.OFPMatch(eth_type=0x0800, ip_proto=17, udp_dst=self.bg_port)
            self.add_flow(datapath, 50, m_udp_bg, [parser.OFPActionOutput(2)])

            m_tcp_bg = parser.OFPMatch(eth_type=0x0800, ip_proto=6, tcp_dst=self.bg_port)
            self.add_flow(datapath, 50, m_tcp_bg, [parser.OFPActionOutput(2)])

            m_udp_rev = parser.OFPMatch(eth_type=0x0800, ip_proto=17, udp_src=self.bg_port)
            self.add_flow(datapath, 50, m_udp_rev, [parser.OFPActionOutput(1)])

            m_tcp_rev = parser.OFPMatch(eth_type=0x0800, ip_proto=6, tcp_src=self.bg_port)
            self.add_flow(datapath, 50, m_tcp_rev, [parser.OFPActionOutput(1)])

        elif dpid == 4:
            m_udp_bg = parser.OFPMatch(
                eth_type=0x0800, ip_proto=17, udp_dst=self.bg_port, ipv4_dst="10.0.0.2"
            )
            self.add_flow(datapath, 50, m_udp_bg, [parser.OFPActionOutput(2)])

            m_tcp_bg = parser.OFPMatch(
                eth_type=0x0800, ip_proto=6, tcp_dst=self.bg_port, ipv4_dst="10.0.0.2"
            )
            self.add_flow(datapath, 50, m_tcp_bg, [parser.OFPActionOutput(2)])

            m_udp_rev = parser.OFPMatch(eth_type=0x0800, ip_proto=17, udp_src=self.bg_port)
            self.add_flow(datapath, 50, m_udp_rev, [parser.OFPActionOutput(5)])

            m_tcp_rev = parser.OFPMatch(eth_type=0x0800, ip_proto=6, tcp_src=self.bg_port)
            self.add_flow(datapath, 50, m_tcp_rev, [parser.OFPActionOutput(5)])

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """Processes unhandled packets (table-miss)."""
        msg = ev.msg
        datapath = msg.datapath
        in_port = msg.match["in_port"]

        if packet is None:
            return

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocol(ethernet.ethernet)
        if eth is None:
            return

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        if eth.ethertype == ether_types.ETH_TYPE_ARP:
            arp_pkt = pkt.get_protocol(arp.arp)
            if arp_pkt and arp_pkt.opcode == arp.ARP_REQUEST:
                target_ip = arp_pkt.dst_ip
                if target_ip in HOST_MAP:
                    target_mac = HOST_MAP[target_ip]["mac"]

                    reply = packet.Packet()
                    reply.add_protocol(
                        ethernet.ethernet(
                            ethertype=ether_types.ETH_TYPE_ARP, dst=eth.src, src=target_mac
                        )
                    )
                    reply.add_protocol(
                        arp.arp(
                            opcode=arp.ARP_REPLY,
                            src_mac=target_mac,
                            src_ip=target_ip,
                            dst_mac=arp_pkt.src_mac,
                            dst_ip=arp_pkt.src_ip,
                        )
                    )
                    reply.serialize()

                    actions = [datapath.ofproto_parser.OFPActionOutput(in_port)]
                    out = datapath.ofproto_parser.OFPPacketOut(
                        datapath=datapath,
                        buffer_id=datapath.ofproto.OFP_NO_BUFFER,
                        in_port=datapath.ofproto.OFPP_CONTROLLER,
                        actions=actions,
                        data=reply.data,
                    )
                    datapath.send_msg(out)
                    return

    def _monitor_loop(self):
        """Background green thread polling OpenFlow port statistics on Switch s1 (Path A uplink Port 5)."""
        while True:
            try:
                if 1 in self.datapaths:
                    dp = self.datapaths[1]
                    req = dp.ofproto_parser.OFPPortStatsRequest(dp, 0, 5)
                    dp.send_msg(req)

            except Exception as exc:
                self.logger.error(f"Error in monitor loop: {exc}")

            hub.sleep(self.poll_interval_sec)

    @set_ev_cls(ofp_event.EventOFPPortStatsReply, MAIN_DISPATCHER)
    def port_stats_reply_handler(self, ev):
        """Processes port stats, detects link saturation, and triggers failover/recovery."""
        for stat in ev.msg.body:
            if ev.msg.datapath.id == 1 and stat.port_no == 5:
                now = time.time()
                key = (1, 5)
                prev = self.port_stats.get(key)
                self.port_stats[key] = (stat.tx_bytes, now, stat.tx_dropped)

                if prev is not None:
                    prev_bytes, prev_time, prev_dropped = prev
                    delta_time = now - prev_time

                    if delta_time > 0:
                        delta_bytes = stat.tx_bytes - prev_bytes

                        throughput_mbps = (delta_bytes * 8.0) / (delta_time * 1e6)
                        delta_dropped = stat.tx_dropped - prev_dropped

                        is_congested = throughput_mbps >= self.congestion_threshold_mbps

                        if is_congested and not self.is_rerouted:
                            self.is_rerouted = True
                            self.low_congestion_count = 0
                            self.logger.info(
                                "Path A load %.2f Mbps (threshold %.2f); rerouting sync traffic to Path B. Drops: %s",
                                throughput_mbps,
                                self.congestion_threshold_mbps,
                                delta_dropped,
                            )
                            self._reroute_to_path_b()

                        elif is_congested:
                            self.low_congestion_count = 0
                        elif not is_congested and self.is_rerouted:
                            self.low_congestion_count += 1
                            if self.low_congestion_count >= 3:
                                self.logger.info(
                                    "Path A load %.2f Mbps; restoring after three low-load polls.",
                                    throughput_mbps,
                                )
                                self._restore_to_path_a()
                                self.is_rerouted = False
                                self.low_congestion_count = 0

    def _reroute_to_path_b(self):
        """Pushes Priority 200 rules on s1, s3, s4 to divert UDP 12300 onto Path B."""

        if 1 in self.datapaths:
            dp = self.datapaths[1]
            p = dp.ofproto_parser
            m_fwd = p.OFPMatch(eth_type=0x0800, ip_proto=17, udp_dst=self.sync_udp_port)
            self.add_flow(dp, 200, m_fwd, [p.OFPActionOutput(6)])

            for cip, port in [("10.0.0.11", 1), ("10.0.0.12", 2), ("10.0.0.13", 3)]:
                m_rev = p.OFPMatch(
                    eth_type=0x0800, ip_proto=17, udp_src=self.sync_udp_port, ipv4_dst=cip
                )
                self.add_flow(dp, 200, m_rev, [p.OFPActionOutput(port)])

        if 3 in self.datapaths:
            dp = self.datapaths[3]
            p = dp.ofproto_parser
            m_fwd = p.OFPMatch(eth_type=0x0800, ip_proto=17, udp_dst=self.sync_udp_port)
            self.add_flow(dp, 200, m_fwd, [p.OFPActionOutput(2)])

            m_rev = p.OFPMatch(eth_type=0x0800, ip_proto=17, udp_src=self.sync_udp_port)
            self.add_flow(dp, 200, m_rev, [p.OFPActionOutput(1)])

        if 4 in self.datapaths:
            dp = self.datapaths[4]
            p = dp.ofproto_parser
            m_rev = p.OFPMatch(eth_type=0x0800, ip_proto=17, udp_src=self.sync_udp_port)
            self.add_flow(dp, 200, m_rev, [p.OFPActionOutput(6)])

            m_fwd = p.OFPMatch(
                eth_type=0x0800, ip_proto=17, udp_dst=self.sync_udp_port, ipv4_dst="10.0.0.1"
            )
            self.add_flow(dp, 200, m_fwd, [p.OFPActionOutput(1)])

        self.logger.info(
            "[SDN-REROUTE] Pushed Priority 200 FlowMod rules to s1, s3, s4 -> Path B active."
        )

    def _restore_to_path_a(self):
        """Deletes Priority 200 rules so switches fall back to Priority 100 on Path A."""
        for dpid in [1, 3, 4]:
            if dpid in self.datapaths:
                dp = self.datapaths[dpid]
                p = dp.ofproto_parser
                self.del_flow(
                    dp, 200, p.OFPMatch(eth_type=0x0800, ip_proto=17, udp_dst=self.sync_udp_port)
                )
                self.del_flow(
                    dp, 200, p.OFPMatch(eth_type=0x0800, ip_proto=17, udp_src=self.sync_udp_port)
                )

        self.logger.info(
            "[SDN-REROUTE] Cleared Priority 200 FlowMod rules. Primary Path A restored."
        )
