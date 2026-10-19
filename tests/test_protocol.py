import unittest
from app.protocol import (
    TimeSyncPacket,
    PKT_TYPE_REQUEST,
    PKT_TYPE_RESPONSE,
    PACKET_SIZE,
    DEFAULT_PORT,
    calculate_delay,
    calculate_offset,
)


class TestTimeSyncProtocol(unittest.TestCase):
    def test_packet_pack_unpack_roundtrip(self):
        """Verify packet serialization to exact 35 bytes and unpack integrity."""
        pkt = TimeSyncPacket(PKT_TYPE_REQUEST, client_id=42, seq_num=101, t0=1700000000.123)
        raw = pkt.to_bytes()

        self.assertEqual(len(raw), PACKET_SIZE)
        self.assertEqual(len(raw), 35)

        unpacked = TimeSyncPacket.from_bytes(raw)
        self.assertEqual(unpacked.pkt_type, PKT_TYPE_REQUEST)
        self.assertEqual(unpacked.client_id, 42)
        self.assertEqual(unpacked.seq_num, 101)
        self.assertAlmostEqual(unpacked.t0, 1700000000.123, places=6)
        self.assertEqual(unpacked.t1, 0.0)
        self.assertEqual(unpacked.t2, 0.0)

    def test_response_packet_roundtrip(self):
        """Verify full response packet with all 3 timestamps intact."""
        pkt = TimeSyncPacket(
            PKT_TYPE_RESPONSE,
            client_id=7,
            seq_num=999,
            t0=100.1,
            t1=100.2,
            t2=100.3,
        )
        raw = pkt.to_bytes()
        unpacked = TimeSyncPacket.from_bytes(raw)

        self.assertEqual(unpacked.pkt_type, PKT_TYPE_RESPONSE)
        self.assertEqual(unpacked.client_id, 7)
        self.assertEqual(unpacked.seq_num, 999)
        self.assertAlmostEqual(unpacked.t0, 100.1, places=6)
        self.assertAlmostEqual(unpacked.t1, 100.2, places=6)
        self.assertAlmostEqual(unpacked.t2, 100.3, places=6)

    def test_invalid_packet_handling(self):
        """Verify malformed or corrupted packets raise ValueError."""
        # Truncated packet
        with self.assertRaises(ValueError):
            TimeSyncPacket.from_bytes(b"too_short")

        # Corrupt magic number
        valid_pkt = TimeSyncPacket(PKT_TYPE_REQUEST, client_id=1, seq_num=1, t0=10.0)
        corrupted = b"XXXX" + valid_pkt.to_bytes()[4:]
        with self.assertRaises(ValueError):
            TimeSyncPacket.from_bytes(corrupted)

    def test_mathematical_formulas(self):
        """Verify RTT Delay and Clock Offset formulas against hand calculations."""
        t0 = 10.00
        t1 = 10.05
        t2 = 10.06
        t3 = 10.13

        # Delay = (t3 - t0) - (t2 - t1) = (10.13 - 10.00) - (10.06 - 10.05) = 0.12
        delay = calculate_delay(t0, t1, t2, t3)
        self.assertAlmostEqual(delay, 0.12, places=6)

        # Offset = ((t1 - t0) + (t2 - t3)) / 2 = ((0.05) + (-0.07)) / 2 = -0.01
        offset = calculate_offset(t0, t1, t2, t3)
        self.assertAlmostEqual(offset, -0.01, places=6)

    def test_repr_formatting(self):
        """Verify string representation of packet."""
        pkt = TimeSyncPacket(PKT_TYPE_REQUEST, client_id=1, seq_num=5, t0=10.0)
        s = repr(pkt)
        self.assertIn("REQUEST", s)
        self.assertIn("client_id=1", s)
        self.assertIn("seq=5", s)


if __name__ == "__main__":
    unittest.main()
