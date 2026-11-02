"""Every standalone client attempt must produce one CSV result."""

import csv
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import Mock

from app.client import TimeSyncClient
from app.protocol import PKT_TYPE_REQUEST, PKT_TYPE_RESPONSE, TimeSyncPacket


class TestClientAccounting(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.root = Path(directory.name)

    def rows(self, path):
        with path.open() as stream:
            return list(csv.DictReader(stream))

    def test_each_mismatched_field_records_an_invalid_attempt(self):
        for field, value in [('pkt_type', PKT_TYPE_REQUEST), ('client_id', 2),
                             ('seq_num', 2), ('t0', 9)]:
            with self.subTest(field=field):
                path = self.root / f'{field}.csv'
                clock = Mock()
                clock.get_time.side_effect = [10, 10.13]
                client = TimeSyncClient(clock=clock, csv_path=str(path))
                fields = dict(pkt_type=PKT_TYPE_RESPONSE, client_id=1, seq_num=1,
                              t0=10, t1=10.05, t2=10.06)
                fields[field] = value
                sock = Mock()
                sock.recvfrom.return_value = (TimeSyncPacket(**fields).to_bytes(),
                                               ('127.0.0.1', 12300))

                client.sync_once(sock)

                rows = self.rows(path)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]['seq_num'], '1')
                self.assertEqual(rows[0]['status'], 'INVALID')
                clock.adjust.assert_not_called()

    def test_malformed_reply_and_timeout_each_record_one_failure(self):
        for status in ['INVALID', 'TIMEOUT']:
            with self.subTest(status=status):
                path = self.root / f'{status}.csv'
                clock = Mock()
                clock.get_time.return_value = 10
                client = TimeSyncClient(clock=clock, csv_path=str(path))
                sock = Mock()
                if status == 'INVALID':
                    sock.recvfrom.return_value = (b'bad packet', ('127.0.0.1', 12300))
                else:
                    sock.recvfrom.side_effect = socket.timeout
                client.sync_once(sock)
                rows = self.rows(path)
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]['status'], status)
                clock.adjust.assert_not_called()

    def test_rejected_reply_does_not_hide_attempt_or_prevent_next_success(self):
        path = self.root / 'attempts.csv'
        clock = Mock()
        clock.get_time.side_effect = [10, 10.13, 20, 20.13, 20.13]
        client = TimeSyncClient(clock=clock, csv_path=str(path))
        sock = Mock()
        sock.recvfrom.side_effect = [
            (TimeSyncPacket(PKT_TYPE_RESPONSE, 2, 1, 10, 10.05, 10.06).to_bytes(),
             ('127.0.0.1', 12300)),
            (TimeSyncPacket(PKT_TYPE_RESPONSE, 1, 2, 20, 20.05, 20.06).to_bytes(),
             ('127.0.0.1', 12300)),
        ]

        client.sync_once(sock)
        client.sync_once(sock)

        rows = self.rows(path)
        self.assertEqual([row['seq_num'] for row in rows], ['1', '2'])
        self.assertEqual([row['status'] for row in rows], ['INVALID', 'SUCCESS'])
        clock.adjust.assert_called_once()
        self.assertAlmostEqual(clock.adjust.call_args.args[0], -.01)
