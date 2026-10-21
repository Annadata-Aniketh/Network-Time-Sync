"""
Custom POX OpenFlow Controller for Network Time Synchronization System (Project #23)
PES University - Computer Networks
"""

from pox.core import core
import pox.openflow.libopenflow_01 as of

log = core.getLogger()

TIME_SYNC_PORT = 12300


class TimeSyncController(object):
    def __init__(self, connection):
        self.connection = connection
        self.mac_to_port = {}
        connection.addListeners(self)

    def resend_packet(self, packet_in, out_port):
        msg = of.ofp_packet_out()
        msg.data = packet_in
        action = of.ofp_action_output(port=out_port)
        msg.actions.append(action)
        self.connection.send(msg)

    def _handle_PacketIn(self, event):
        try:
            packet = event.parsed
            if not packet or not packet.parsed:
                return
        except Exception:
            return

        packet_in = event.ofp
        dpid = event.dpid
        in_port = event.port

        # Learn source MAC to avoid flooding next time
        self.mac_to_port[packet.src] = in_port

        # Check for IPv4 and UDP Time Sync traffic (Port 12300)
        try:
            ip_pkt = packet.find('ipv4')
            if ip_pkt:
                udp_pkt = ip_pkt.find('udp')
                if udp_pkt and (udp_pkt.dstport == TIME_SYNC_PORT or udp_pkt.srcport == TIME_SYNC_PORT):
                    log.info(f"[SDN Controller] [Switch {dpid}] Priority Time-Sync packet detected: "
                             f"{ip_pkt.srcip}:{udp_pkt.srcport} -> {ip_pkt.dstip}:{udp_pkt.dstport}")

                    if packet.dst in self.mac_to_port:
                        out_port = self.mac_to_port[packet.dst]
                        msg = of.ofp_flow_mod()
                        msg.match = of.ofp_match(
                            dl_type=0x0800,
                            nw_proto=17,
                            tp_dst=udp_pkt.dstport
                        )
                        msg.idle_timeout = 30
                        msg.hard_timeout = 60
                        msg.priority = 100
                        msg.actions.append(of.ofp_action_output(port=out_port))
                        msg.data = packet_in
                        self.connection.send(msg)
                        return
        except Exception:
            pass

        # Standard L2 learning switch logic
        if packet.dst in self.mac_to_port:
            out_port = self.mac_to_port[packet.dst]
            msg = of.ofp_flow_mod()
            msg.match = of.ofp_match.from_packet(packet, in_port)
            msg.idle_timeout = 10
            msg.hard_timeout = 30
            msg.priority = 10
            msg.actions.append(of.ofp_action_output(port=out_port))
            msg.data = packet_in
            self.connection.send(msg)
        else:
            self.resend_packet(packet_in, of.OFPP_FLOOD)


def launch():
    def start_switch(event):
        log.info(f"[SDN Controller] Switch connected: DPID={event.dpid}")
        TimeSyncController(event.connection)

    core.openflow.addListenerByName("ConnectionUp", start_switch)
    log.info("[SDN Controller] Network Time Sync OpenFlow controller initialized.")
