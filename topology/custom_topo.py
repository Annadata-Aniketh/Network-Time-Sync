#!/usr/bin/env python3
"""
SDN Topology for Network Time Synchronization System (Project #23)
PES University - Computer Networks

Topology (Loop-Free Linear Backbone):
  h1 (Time Server) <---> s1 <== 10Mbps, 5ms ==> s2 <---> h3 (Client 2)
  h2 (Client 1)    <---> s1                     | <---> h4 (Client 3)
                                                |
                                        10Mbps, 5ms
                                                |
                                               s3
"""

from mininet.topo import Topo
from mininet.net import Mininet
from mininet.node import RemoteController, OVSSwitch
from mininet.link import TCLink
from mininet.cli import CLI
from mininet.log import setLogLevel, info


class NetworkTimeTopo(Topo):
    def build(self):
        # 1. Add OpenFlow switches
        s1 = self.addSwitch('s1', protocols='OpenFlow10')
        s2 = self.addSwitch('s2', protocols='OpenFlow10')
        s3 = self.addSwitch('s3', protocols='OpenFlow10')

        # 2. Add Hosts
        h1 = self.addHost('h1', ip='10.0.0.1/24', mac='00:00:00:00:00:01')
        h2 = self.addHost('h2', ip='10.0.0.2/24', mac='00:00:00:00:00:02')
        h3 = self.addHost('h3', ip='10.0.0.3/24', mac='00:00:00:00:00:03')
        h4 = self.addHost('h4', ip='10.0.0.4/24', mac='00:00:00:00:00:04')

        # 3. Host connections
        self.addLink(h1, s1, cls=TCLink, bw=100, delay='1ms')
        self.addLink(h2, s1, cls=TCLink, bw=100, delay='1ms')
        self.addLink(h3, s2, cls=TCLink, bw=100, delay='1ms')
        self.addLink(h4, s2, cls=TCLink, bw=100, delay='1ms')

        # 4. Inter-switch backbone links (Loop-free: s1 -- s2 -- s3)
        self.addLink(s1, s2, cls=TCLink, bw=10, delay='5ms')
        self.addLink(s2, s3, cls=TCLink, bw=10, delay='5ms')


topos = {'networktime': lambda: NetworkTimeTopo()}


def run():
    topo = NetworkTimeTopo()
    net = Mininet(
        topo=topo,
        controller=lambda name: RemoteController(name, ip='127.0.0.1', port=6653),
        switch=OVSSwitch,
        link=TCLink,
        autoSetMacs=True
    )
    net.start()
    info('*** Network Time Sync topology active. Starting CLI.\n')
    CLI(net)
    net.stop()


if __name__ == '__main__':
    setLogLevel('info')
    run()
