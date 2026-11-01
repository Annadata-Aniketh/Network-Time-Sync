#!/usr/bin/env python3
"""OpenFlow 1.3 controller: Path A forwarding, edge QoS, and load-based rerouting.

SDN_MODE selects baseline or optimized. Optimized mode polls s1 port 5 every
2 seconds, moves UDP 12300 to Path B above 4 Mbps, and restores Path A after
three consecutive low-load polls. Queue IDs apply only on s1/s4 Path A egress.
"""

import os
import sys
import json
import time
import logging

try:
    from os_ken.base import app_manager
    from os_ken.controller import ofp_event
    from os_ken.controller.handler import CONFIG_DISPATCHER, MAIN_DISPATCHER, set_ev_cls
    from os_ken.ofproto import ofproto_v1_3
    from os_ken.lib.packet import packet, ethernet, ether_types, arp, ipv4, udp, tcp
    from os_ken.lib import hub
except ImportError:
    # Graceful fallback mock classes for local dev / testing on environments without OS-Ken (e.g. macOS)
    class app_manager:
        class OSKenApp:
            def __init__(self, *args, **kwargs):
                self.logger = logging.getLogger("SDNController")

    class ofp_event:
        class EventOFPSwitchFeatures: pass
        class EventOFPPacketIn: pass
        class EventOFPPortStatsReply: pass

    CONFIG_DISPATCHER = 'config'
    MAIN_DISPATCHER = 'main'
    set_ev_cls = lambda *a, **k: (lambda f: f)

    class ofproto_v1_3:
        OFP_VERSION = 0x04

    packet = ethernet = ether_types = arp = ipv4 = udp = tcp = None

    class hub:
        @staticmethod
        def spawn(func, *args, **kwargs): return None
        @staticmethod
        def sleep(sec): time.sleep(sec)


DEFAULT_SYNC_PORT = 12300
DEFAULT_BG_PORT = 5001
DEFAULT_THRESHOLD_MBPS = 4.0
DEFAULT_POLL_INTERVAL = 2.0

# Deterministic Host Map (IP -> MAC, switch DPID, switch port)
HOST_MAP = {
    '10.0.0.1':  {'mac': '00:00:00:00:00:01', 'dpid': 4, 'port': 1, 'name': 'h_server'},
    '10.0.0.2':  {'mac': '00:00:00:00:00:02', 'dpid': 4, 'port': 2, 'name': 'h_bg_server'},
    '10.0.0.11': {'mac': '00:00:00:00:00:11', 'dpid': 1, 'port': 1, 'name': 'h_client1'},
    '10.0.0.12': {'mac': '00:00:00:00:00:12', 'dpid': 1, 'port': 2, 'name': 'h_client2'},
    '10.0.0.13': {'mac': '00:00:00:00:00:13', 'dpid': 1, 'port': 3, 'name': 'h_client3'},
    '10.0.0.20': {'mac': '00:00:00:00:00:20', 'dpid': 1, 'port': 4, 'name': 'h_bg_client'},
}


class TimeSyncSDNController(app_manager.OSKenApp):
    OFP_VERSIONS = [ofproto_v1_3.OFP_VERSION]
    HOST_MAP = HOST_MAP

    def __init__(self, *args, **kwargs):
        super(TimeSyncSDNController, self).__init__(*args, **kwargs)

        if not hasattr(self, 'logger') or self.logger is None:
            self.logger = logging.getLogger("SDNController")
        self.logger.setLevel(logging.INFO)

        # Load flow rules configuration
        self.config = self._load_configuration()
        self.sync_udp_port = self.config.get("sync_udp_port", DEFAULT_SYNC_PORT)
        self.bg_port = self.config.get("bg_port", DEFAULT_BG_PORT)
        self.congestion_threshold_mbps = float(self.config.get("congestion_threshold_mbps", DEFAULT_THRESHOLD_MBPS))
        self.poll_interval_sec = float(self.config.get("poll_interval_sec", DEFAULT_POLL_INTERVAL))
        self.qos_queues = self.config.get("qos_queues", {"high_priority_sync": 1, "low_priority_bg": 2, "default": 0})

        # Operating mode: read from environment or default to 'optimized'
        self.mode = os.environ.get("SDN_MODE", "optimized").lower().strip()
        self.logger.info(f"Initialized TimeSyncSDNController [Mode: {self.mode}]")
        self.logger.info(f"Policy: Time-Sync Port={self.sync_udp_port}, BG Port={self.bg_port}, "
                         f"Threshold={self.congestion_threshold_mbps} Mbps, Poll={self.poll_interval_sec}s")

        # Datapath connections: dpid -> datapath
        self.datapaths = {}

        # Port statistics cache: (dpid, port_no) -> (tx_bytes, timestamp, tx_dropped)
        self.port_stats = {}

        # Dynamic reroute state
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
                    with open(p, "r") as f:
                        cfg = json.load(f)
                        self.logger.info(f"Loaded flow rules configuration from: {p}")
                        return cfg
                except Exception as exc:
                    self.logger.warning(f"Error reading {p}: {exc}")
        return {
            "sync_udp_port": DEFAULT_SYNC_PORT,
            "bg_port": DEFAULT_BG_PORT,
            "congestion_threshold_mbps": DEFAULT_THRESHOLD_MBPS,
            "poll_interval_sec": DEFAULT_POLL_INTERVAL,
            "qos_queues": {"high_priority_sync": 1, "low_priority_bg": 2, "default": 0},
            "paths": {"path_a_switches": [1, 2, 4], "path_b_switches": [1, 3, 4]}
        }

    # =========================================================================
    # OpenFlow Flow Management Helpers
    # =========================================================================

    def add_flow(self, datapath, priority: int, match, actions, buffer_id=None, idle_timeout=0, hard_timeout=0):
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
            "hard_timeout": hard_timeout
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
            cookie_mask=0xffffffffffffffff,
            out_port=ofproto.OFPP_ANY,
            out_group=ofproto.OFPG_ANY,
            priority=priority,
            match=match
        )
        datapath.send_msg(mod)

    # =========================================================================
    # Switch Connection & Proactive Flows
    # =========================================================================

    @set_ev_cls(ofp_event.EventOFPSwitchFeatures, CONFIG_DISPATCHER)
    def switch_features_handler(self, ev):
        """Handles switch connection, handshake, table-miss rule, and proactive rules."""
        datapath = ev.msg.datapath
        ofproto = datapath.ofproto
        parser = datapath.ofproto_parser
        dpid = datapath.id

        self.datapaths[dpid] = datapath
        self.logger.info(f"Switch connected: DPID={dpid} (0x{dpid:016x})")

        # Table-Miss Flow Entry (Priority 0 -> send packet to controller)
        match_miss = parser.OFPMatch()
        actions_miss = [parser.OFPActionOutput(ofproto.OFPP_CONTROLLER, ofproto.OFPCML_NO_BUFFER)]
        self.add_flow(datapath, priority=0, match=match_miss, actions=actions_miss)

        # Install proactive flow rules according to active mode
        if self.mode == "baseline":
            self._install_baseline_flows(datapath)
        else:
            self._install_optimized_flows(datapath)

        # Spawn real-time monitoring thread on the controller hub once in optimized mode
        if self.mode == "optimized" and not self.monitor_started:
            self.monitor_started = True
            hub.spawn(self._monitor_loop)
            self.logger.info("SDN real-time port monitoring thread started (hub.spawn).")

    def _install_baseline_flows(self, datapath):
        """Baseline Mode: All traffic routed over Path A in default Queue 0 without QoS."""
        parser = datapath.ofproto_parser
        dpid = datapath.id

        if dpid == 1:
            for srv_ip in ['10.0.0.1', '10.0.0.2']:
                self.add_flow(datapath, 10, parser.OFPMatch(eth_type=0x0800, ipv4_dst=srv_ip), [parser.OFPActionOutput(5)])
            for cip, port in [('10.0.0.11', 1), ('10.0.0.12', 2), ('10.0.0.13', 3), ('10.0.0.20', 4)]:
                self.add_flow(datapath, 10, parser.OFPMatch(eth_type=0x0800, ipv4_dst=cip), [parser.OFPActionOutput(port)])
        elif dpid == 2:
            self.add_flow(datapath, 10, parser.OFPMatch(in_port=1), [parser.OFPActionOutput(2)])
            self.add_flow(datapath, 10, parser.OFPMatch(in_port=2), [parser.OFPActionOutput(1)])
        elif dpid == 4:
            self.add_flow(datapath, 10, parser.OFPMatch(eth_type=0x0800, ipv4_dst='10.0.0.1'), [parser.OFPActionOutput(1)])
            self.add_flow(datapath, 10, parser.OFPMatch(eth_type=0x0800, ipv4_dst='10.0.0.2'), [parser.OFPActionOutput(2)])
            for cip in ['10.0.0.11', '10.0.0.12', '10.0.0.13', '10.0.0.20']:
                self.add_flow(datapath, 10, parser.OFPMatch(eth_type=0x0800, ipv4_dst=cip), [parser.OFPActionOutput(5)])

    def _install_optimized_flows(self, datapath):
        """Optimized Mode: Microflow classification, HTB QoS queues, and initial Path A routing."""
        parser = datapath.ofproto_parser
        dpid = datapath.id
        q_sync = self.qos_queues.get("high_priority_sync", 1)
        q_bg = self.qos_queues.get("low_priority_bg", 2)

        # 1. Base Unicast Forwarding (Priority 10)
        self._install_baseline_flows(datapath)

        # Relay rules for core switch s3 (Path B)
        if dpid == 3:
            self.add_flow(datapath, 10, parser.OFPMatch(in_port=1), [parser.OFPActionOutput(2)])
            self.add_flow(datapath, 10, parser.OFPMatch(in_port=2), [parser.OFPActionOutput(1)])

        # 2. Time-Sync Microflows (Priority 100, Queue 1)
        if dpid == 1:
            # Client -> Server: match udp_dst=12300, forward out Path A uplink Port 5 with Queue 1
            m_fwd = parser.OFPMatch(eth_type=0x0800, ip_proto=17, udp_dst=self.sync_udp_port)
            self.add_flow(datapath, 100, m_fwd, [parser.OFPActionSetQueue(q_sync), parser.OFPActionOutput(5)])

            # Server -> Clients: match udp_src=12300 and destination IP, forward to host ports
            for cip, port in [('10.0.0.11', 1), ('10.0.0.12', 2), ('10.0.0.13', 3)]:
                m_rev = parser.OFPMatch(eth_type=0x0800, ip_proto=17, udp_src=self.sync_udp_port, ipv4_dst=cip)
                self.add_flow(datapath, 100, m_rev, [parser.OFPActionOutput(port)])

        elif dpid == 2:
            m_fwd = parser.OFPMatch(eth_type=0x0800, ip_proto=17, udp_dst=self.sync_udp_port)
            self.add_flow(datapath, 100, m_fwd, [parser.OFPActionOutput(2)])

            m_rev = parser.OFPMatch(eth_type=0x0800, ip_proto=17, udp_src=self.sync_udp_port)
            self.add_flow(datapath, 100, m_rev, [parser.OFPActionOutput(1)])

        elif dpid == 4:
            m_fwd = parser.OFPMatch(eth_type=0x0800, ip_proto=17, udp_dst=self.sync_udp_port, ipv4_dst='10.0.0.1')
            self.add_flow(datapath, 100, m_fwd, [parser.OFPActionOutput(1)])

            m_rev = parser.OFPMatch(eth_type=0x0800, ip_proto=17, udp_src=self.sync_udp_port)
            self.add_flow(datapath, 100, m_rev, [parser.OFPActionSetQueue(q_sync), parser.OFPActionOutput(5)])

        # 3. Background Traffic Rate-Limiting (Priority 50, Queue 2)
        if dpid == 1:
            m_udp_bg = parser.OFPMatch(eth_type=0x0800, ip_proto=17, udp_dst=self.bg_port)
            self.add_flow(datapath, 50, m_udp_bg, [parser.OFPActionSetQueue(q_bg), parser.OFPActionOutput(5)])

            m_tcp_bg = parser.OFPMatch(eth_type=0x0800, ip_proto=6, tcp_dst=self.bg_port)
            self.add_flow(datapath, 50, m_tcp_bg, [parser.OFPActionSetQueue(q_bg), parser.OFPActionOutput(5)])

            m_host_bg = parser.OFPMatch(eth_type=0x0800, ipv4_src='10.0.0.20')
            self.add_flow(datapath, 40, m_host_bg, [parser.OFPActionSetQueue(q_bg), parser.OFPActionOutput(5)])

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
            m_udp_bg = parser.OFPMatch(eth_type=0x0800, ip_proto=17, udp_dst=self.bg_port, ipv4_dst='10.0.0.2')
            self.add_flow(datapath, 50, m_udp_bg, [parser.OFPActionOutput(2)])

            m_tcp_bg = parser.OFPMatch(eth_type=0x0800, ip_proto=6, tcp_dst=self.bg_port, ipv4_dst='10.0.0.2')
            self.add_flow(datapath, 50, m_tcp_bg, [parser.OFPActionOutput(2)])

            m_udp_rev = parser.OFPMatch(eth_type=0x0800, ip_proto=17, udp_src=self.bg_port)
            self.add_flow(datapath, 50, m_udp_rev, [parser.OFPActionOutput(5)])

            m_tcp_rev = parser.OFPMatch(eth_type=0x0800, ip_proto=6, tcp_src=self.bg_port)
            self.add_flow(datapath, 50, m_tcp_rev, [parser.OFPActionOutput(5)])

    # =========================================================================
    # Loop-Free ARP Proxy & Packet-In Handler
    # =========================================================================

    @set_ev_cls(ofp_event.EventOFPPacketIn, MAIN_DISPATCHER)
    def packet_in_handler(self, ev):
        """
        Processes unhandled packets (table-miss).
        Implements an ARP Proxy to eliminate broadcast storms across diamond topology loops.
        """
        msg = ev.msg
        datapath = msg.datapath
        in_port = msg.match['in_port']

        if packet is None:
            return

        pkt = packet.Packet(msg.data)
        eth = pkt.get_protocols(ethernet.ethernet)[0]

        if eth.ethertype == ether_types.ETH_TYPE_LLDP:
            return

        # -------------------------------------------------------------
        # Loop-Free ARP Proxy
        # -------------------------------------------------------------
        if eth.ethertype == ether_types.ETH_TYPE_ARP:
            arp_pkt = pkt.get_protocol(arp.arp)
            if arp_pkt and arp_pkt.opcode == arp.ARP_REQUEST:
                target_ip = arp_pkt.dst_ip
                if target_ip in HOST_MAP:
                    target_mac = HOST_MAP[target_ip]['mac']

                    # Generate ARP reply directly to requester
                    reply = packet.Packet()
                    reply.add_protocol(ethernet.ethernet(
                        ethertype=ether_types.ETH_TYPE_ARP,
                        dst=eth.src,
                        src=target_mac
                    ))
                    reply.add_protocol(arp.arp(
                        opcode=arp.ARP_REPLY,
                        src_mac=target_mac,
                        src_ip=target_ip,
                        dst_mac=arp_pkt.src_mac,
                        dst_ip=arp_pkt.src_ip
                    ))
                    reply.serialize()

                    actions = [datapath.ofproto_parser.OFPActionOutput(in_port)]
                    out = datapath.ofproto_parser.OFPPacketOut(
                        datapath=datapath,
                        buffer_id=datapath.ofproto.OFP_NO_BUFFER,
                        in_port=datapath.ofproto.OFPP_CONTROLLER,
                        actions=actions,
                        data=reply.data
                    )
                    datapath.send_msg(out)
                    return

    # =========================================================================
    # Real-Time Monitoring & Dynamic Rerouting
    # =========================================================================

    def _monitor_loop(self):
        """
        Background green thread polling OpenFlow port statistics on Switch s1 (Path A uplink Port 5).
        Calculates instantaneous throughput (Mbps) and evaluates congestion trigger conditions.
        """
        while True:
            try:
                # Request port statistics for s1 Port 5 if s1 is connected
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
                        # Throughput in Megabits per second (Mbps)
                        throughput_mbps = (delta_bytes * 8.0) / (delta_time * 1e6)
                        delta_dropped = stat.tx_dropped - prev_dropped

                        is_congested = throughput_mbps >= self.congestion_threshold_mbps

                        # -----------------------------------------------------
                        # Trigger Reroute: Congestion detected
                        # -----------------------------------------------------
                        if is_congested and not self.is_rerouted:
                            self.is_rerouted = True
                            self.low_congestion_count = 0
                            self.logger.info(
                                "Path A load %.2f Mbps (threshold %.2f); rerouting sync traffic to Path B. Drops: %s",
                                throughput_mbps, self.congestion_threshold_mbps, delta_dropped,
                            )
                            self._reroute_to_path_b()

                        # -----------------------------------------------------
                        # Recovery: Traffic dropped below threshold for 3 polls
                        # -----------------------------------------------------
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
        # 1. Update s1: Send outgoing UDP 12300 out Port 6 (Path B uplink to s3)
        if 1 in self.datapaths:
            dp = self.datapaths[1]
            p = dp.ofproto_parser
            m_fwd = p.OFPMatch(eth_type=0x0800, ip_proto=17, udp_dst=self.sync_udp_port)
            self.add_flow(dp, 200, m_fwd, [p.OFPActionOutput(6)])

            for cip, port in [('10.0.0.11', 1), ('10.0.0.12', 2), ('10.0.0.13', 3)]:
                m_rev = p.OFPMatch(eth_type=0x0800, ip_proto=17, udp_src=self.sync_udp_port, ipv4_dst=cip)
                self.add_flow(dp, 200, m_rev, [p.OFPActionOutput(port)])

        # 2. Update s3 (Path B Core): Forward between Port 1 and Port 2
        if 3 in self.datapaths:
            dp = self.datapaths[3]
            p = dp.ofproto_parser
            m_fwd = p.OFPMatch(eth_type=0x0800, ip_proto=17, udp_dst=self.sync_udp_port)
            self.add_flow(dp, 200, m_fwd, [p.OFPActionOutput(2)])

            m_rev = p.OFPMatch(eth_type=0x0800, ip_proto=17, udp_src=self.sync_udp_port)
            self.add_flow(dp, 200, m_rev, [p.OFPActionOutput(1)])

        # 3. Update s4: Send returning UDP 12300 out Port 6 (Path B downlink to s3)
        if 4 in self.datapaths:
            dp = self.datapaths[4]
            p = dp.ofproto_parser
            m_rev = p.OFPMatch(eth_type=0x0800, ip_proto=17, udp_src=self.sync_udp_port)
            self.add_flow(dp, 200, m_rev, [p.OFPActionOutput(6)])

            m_fwd = p.OFPMatch(eth_type=0x0800, ip_proto=17, udp_dst=self.sync_udp_port, ipv4_dst='10.0.0.1')
            self.add_flow(dp, 200, m_fwd, [p.OFPActionOutput(1)])

        self.logger.info("[SDN-REROUTE] Pushed Priority 200 FlowMod rules to s1, s3, s4 -> Path B active.")

    def _restore_to_path_a(self):
        """Deletes Priority 200 rules so switches fall back to Priority 100 on Path A."""
        for dpid in [1, 3, 4]:
            if dpid in self.datapaths:
                dp = self.datapaths[dpid]
                p = dp.ofproto_parser
                self.del_flow(dp, 200, p.OFPMatch(eth_type=0x0800, ip_proto=17, udp_dst=self.sync_udp_port))
                self.del_flow(dp, 200, p.OFPMatch(eth_type=0x0800, ip_proto=17, udp_src=self.sync_udp_port))

        self.logger.info("[SDN-REROUTE] Cleared Priority 200 FlowMod rules. Primary Path A restored.")
