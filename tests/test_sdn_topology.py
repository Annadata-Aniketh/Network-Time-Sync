"""
Unit tests for Member 2 deliverables:
  - Multi-path diamond topology (topology/custom_topo.py)
  - SDN Controller & Flow Rules (sdn/controller.py, sdn/flow_rules.json)
"""

import os
import json
import unittest
from topology import (
    TimeSyncTopo,
    create_network,
    setup_qos_queues,
    inject_link_impairment,
    clear_link_impairment,
    start_topology,
)
from sdn import TimeSyncSDNController


class TestTimeSyncTopology(unittest.TestCase):
    def setUp(self):
        self.topo = TimeSyncTopo()

    def test_switches(self):
        """Verify the 4 switches in the diamond topology."""
        switches = set(self.topo.switches())
        self.assertEqual(switches, {'s1', 's2', 's3', 's4'})

    def test_hosts(self):
        """Verify the 6 hosts (3 clients, 1 server, 2 background)."""
        hosts = set(self.topo.hosts())
        expected = {'h_server', 'h_bg_server', 'h_client1', 'h_client2', 'h_client3', 'h_bg_client'}
        self.assertEqual(hosts, expected)

    def test_switch_dpids(self):
        """Verify fixed OpenFlow 1.3 DPIDs for s1-s4."""
        if hasattr(self.topo, 'switches_dict'):
            for i in range(1, 5):
                name = f's{i}'
                self.assertIn(name, self.topo.switches_dict)
                self.assertEqual(self.topo.switches_dict[name].get('dpid'), f'{i:016x}')

    def test_host_addressing(self):
        """Verify deterministic IP and MAC assignments."""
        if hasattr(self.topo, 'hosts_dict'):
            self.assertEqual(self.topo.hosts_dict['h_server']['ip'], '10.0.0.1/24')
            self.assertEqual(self.topo.hosts_dict['h_server']['mac'], '00:00:00:00:00:01')
            self.assertEqual(self.topo.hosts_dict['h_bg_server']['ip'], '10.0.0.2/24')
            self.assertEqual(self.topo.hosts_dict['h_bg_server']['mac'], '00:00:00:00:00:02')
            self.assertEqual(self.topo.hosts_dict['h_client1']['ip'], '10.0.0.11/24')
            self.assertEqual(self.topo.hosts_dict['h_client1']['mac'], '00:00:00:00:00:11')
            self.assertEqual(self.topo.hosts_dict['h_client2']['ip'], '10.0.0.12/24')
            self.assertEqual(self.topo.hosts_dict['h_client2']['mac'], '00:00:00:00:00:12')
            self.assertEqual(self.topo.hosts_dict['h_client3']['ip'], '10.0.0.13/24')
            self.assertEqual(self.topo.hosts_dict['h_client3']['mac'], '00:00:00:00:00:13')
            self.assertEqual(self.topo.hosts_dict['h_bg_client']['ip'], '10.0.0.20/24')
            self.assertEqual(self.topo.hosts_dict['h_bg_client']['mac'], '00:00:00:00:00:20')

    def test_deterministic_ports_s1(self):
        """Verify deterministic switch port mapping on switch s1."""
        if hasattr(self.topo, 'links_list'):
            s1_ports = {}
            for l in self.topo.links_list:
                if l['node1'] == 's1':
                    s1_ports[l['node2']] = l['port1']
                elif l['node2'] == 's1':
                    s1_ports[l['node1']] = l['port2']

            self.assertEqual(s1_ports.get('h_client1'), 1)
            self.assertEqual(s1_ports.get('h_client2'), 2)
            self.assertEqual(s1_ports.get('h_client3'), 3)
            self.assertEqual(s1_ports.get('h_bg_client'), 4)
            self.assertEqual(s1_ports.get('s2'), 5)  # Path A uplink
            self.assertEqual(s1_ports.get('s3'), 6)  # Path B uplink

    def test_deterministic_ports_s4(self):
        """Verify deterministic switch port mapping on switch s4."""
        if hasattr(self.topo, 'links_list'):
            s4_ports = {}
            for l in self.topo.links_list:
                if l['node1'] == 's4':
                    s4_ports[l['node2']] = l['port1']
                elif l['node2'] == 's4':
                    s4_ports[l['node1']] = l['port2']

            self.assertEqual(s4_ports.get('h_server'), 1)
            self.assertEqual(s4_ports.get('h_bg_server'), 2)
            self.assertEqual(s4_ports.get('s2'), 5)  # Path A downlink
            self.assertEqual(s4_ports.get('s3'), 6)  # Path B downlink

    def test_link_parameters(self):
        """Verify bandwidth, delay, and queue constraints on Core Paths."""
        if hasattr(self.topo, 'links_list'):
            for l in self.topo.links_list:
                pair = {l['node1'], l['node2']}
                # Path A links: 10 Mbps, 2ms, Q=100
                if pair in ({'s1', 's2'}, {'s2', 's4'}):
                    self.assertEqual(l['opts'].get('bw'), 10)
                    self.assertEqual(l['opts'].get('delay'), '2ms')
                    self.assertEqual(l['opts'].get('max_queue_size'), 100)
                # Path B links: 50 Mbps, 2ms, Q=1000
                elif pair in ({'s1', 's3'}, {'s3', 's4'}):
                    self.assertEqual(l['opts'].get('bw'), 50)
                    self.assertEqual(l['opts'].get('delay'), '2ms')
                    self.assertEqual(l['opts'].get('max_queue_size'), 1000)

    def test_helper_functions_callable(self):
        """Verify topology helper functions exist and are callable."""
        for fn in [setup_qos_queues, inject_link_impairment, clear_link_impairment, create_network, start_topology]:
            self.assertTrue(callable(fn))


class TestSDNController(unittest.TestCase):
    def test_flow_rules_json(self):
        """Verify sdn/flow_rules.json conforms to configuration schema."""
        path = os.path.join(os.path.dirname(__file__), '..', 'sdn', 'flow_rules.json')
        self.assertTrue(os.path.exists(path))
        with open(path) as f:
            cfg = json.load(f)

        self.assertEqual(cfg['sync_udp_port'], 12300)
        self.assertEqual(cfg['bg_port'], 5001)
        self.assertEqual(cfg['congestion_threshold_mbps'], 4.0)
        self.assertEqual(cfg['poll_interval_sec'], 2.0)
        self.assertEqual(cfg['qos_queues']['high_priority_sync'], 1)
        self.assertEqual(cfg['qos_queues']['low_priority_bg'], 2)
        self.assertEqual(cfg['qos_queues']['default'], 0)
        self.assertEqual(cfg['paths']['path_a_switches'], [1, 2, 4])
        self.assertEqual(cfg['paths']['path_b_switches'], [1, 3, 4])

    def test_controller_modes(self):
        """Verify controller operates in baseline and optimized modes."""
        os.environ['SDN_MODE'] = 'optimized'
        c_opt = TimeSyncSDNController()
        self.assertEqual(c_opt.mode, 'optimized')
        self.assertFalse(c_opt.is_rerouted)

        os.environ['SDN_MODE'] = 'baseline'
        c_base = TimeSyncSDNController()
        self.assertEqual(c_base.mode, 'baseline')
        os.environ['SDN_MODE'] = 'optimized'

    def test_host_map(self):
        """Verify static host map for loop-free ARP resolution."""
        c = TimeSyncSDNController()
        self.assertIn('10.0.0.1', c.HOST_MAP)
        self.assertIn('10.0.0.2', c.HOST_MAP)
        self.assertIn('10.0.0.11', c.HOST_MAP)
        self.assertIn('10.0.0.20', c.HOST_MAP)
        self.assertEqual(c.HOST_MAP['10.0.0.1']['mac'], '00:00:00:00:00:01')
        self.assertEqual(c.HOST_MAP['10.0.0.1']['port'], 1)

    def test_reroute_and_restore(self):
        """Verify reroute to Path B and restore to Path A execute cleanly."""
        controller = TimeSyncSDNController()
        controller._reroute_to_path_b()
        controller._restore_to_path_a()


if __name__ == '__main__':
    unittest.main()
