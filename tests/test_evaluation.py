"""Regression checks for benchmark measurements and result reporting."""

import csv
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pandas as pd

from app.client import VirtualClock
from app.protocol import PKT_TYPE_RESPONSE, TimeSyncPacket
from evaluation.benchmark import check_environment, write_csv
from evaluation.sync_worker import CSV_HEADER, phase_at, sample
from evaluation.plot_results import calculate_convergence_time, compute_summary_table, load_datasets


class TestBenchmarkMeasurements(unittest.TestCase):
    def test_timeout_has_no_fabricated_delay(self):
        sock = Mock()
        sock.recv.side_effect = socket.timeout
        clock = VirtualClock(initial_offset=.1, drift_rate=0)
        row = sample(sock, clock, 1, 1)
        self.assertEqual(row['status'], 'TIMEOUT')
        self.assertEqual(row['rtt_ms'], '')
        self.assertEqual(row['jitter_ms'], '')
        self.assertEqual(clock.correction, 0)

    def test_invalid_response_does_not_adjust_clock(self):
        for data in [b'bad packet', TimeSyncPacket(PKT_TYPE_RESPONSE, 2, 1, t0=10).to_bytes()]:
            with self.subTest(data=data):
                clock = Mock()
                clock.get_time.return_value = 10
                sock = Mock()
                sock.recv.return_value = data
                row = sample(sock, clock, 1, 1)
                self.assertEqual(row['status'], 'INVALID')
                clock.adjust.assert_not_called()

    def test_valid_response_math_and_correction(self):
        clock = Mock()
        clock.get_time.side_effect = [10, 10.13, 10.13]
        sock = Mock()
        sock.recv.return_value = TimeSyncPacket(PKT_TYPE_RESPONSE, 1, 1, 10, 10.05, 10.06).to_bytes()
        row = sample(sock, clock, 1, 1)
        self.assertEqual(row['status'], 'SUCCESS')
        self.assertAlmostEqual(row['rtt_ms'], 120)
        clock.adjust.assert_called_once()
        self.assertAlmostEqual(clock.adjust.call_args.args[0], -.01)

    def test_csv_schema_and_phase_boundaries(self):
        self.assertIn('Normal', phase_at(0, 60))
        self.assertIn('Congestion', phase_at(20, 60))
        self.assertIn('NetEm', phase_at(40, 60))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'metrics.csv'
            write_csv(path, [dict.fromkeys(CSV_HEADER, '')])
            with path.open() as stream:
                self.assertEqual(next(csv.reader(stream)), CSV_HEADER)

    def test_no_non_linux_fallback(self):
        with patch('evaluation.benchmark.sys.platform', 'darwin'):
            with self.assertRaisesRegex(RuntimeError, 'Linux VM'):
                check_environment()


class TestResults(unittest.TestCase):
    def test_unconfirmed_convergence_is_unavailable(self):
        frame = pd.DataFrame({'elapsed_sec': [0, 1, 2], 'true_residual_error_ms': [20, 1, 1]})
        self.assertTrue(pd.isna(calculate_convergence_time(frame)))

    def test_convergence_requires_all_clients_and_successful_rounds(self):
        rows = [dict(seq=seq, client_id=client, elapsed_sec=seq,
                     true_residual_error_ms=1, status='SUCCESS')
                for seq in range(1, 4) for client in [1, 2, 3]]
        frame = pd.DataFrame(rows)
        self.assertEqual(calculate_convergence_time(frame), 3)
        frame.loc[0, 'status'] = 'TIMEOUT'
        self.assertTrue(pd.isna(calculate_convergence_time(frame)))
        self.assertTrue(pd.isna(calculate_convergence_time(pd.DataFrame(rows[1:]))))

    def test_summary_excludes_failed_delay_and_reports_failures(self):
        frame = pd.DataFrame(dict(elapsed_sec=[0, 1, 2], rtt_ms=[10, 20, 999],
                                  jitter_ms=[0, 10, 999], true_residual_error_ms=[1, 1, 30],
                                  status=['SUCCESS', 'SUCCESS', 'TIMEOUT']))
        stats, summary = compute_summary_table(frame, frame)
        self.assertEqual(stats['Mean RTT (ms)'][0], 15)
        self.assertAlmostEqual(stats['Failed samples (%)'][0], 100 / 3)
        self.assertIn('N/A', summary)
        self.assertNotIn('sub-millisecond', summary)

    def test_legacy_results_require_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(FileNotFoundError):
                load_datasets(directory)

class TestMininetStartupCleanup(unittest.TestCase):
    def test_failed_build_stops_partial_network_and_controller(self):
        import sys
        import types
        from evaluation.benchmark import run_benchmark_scenario_mininet

        network = Mock()
        network.build.side_effect = Exception('interface creation failed')
        constructor = Mock(return_value=network)
        net_module = types.ModuleType('mininet.net')
        net_module.Mininet = constructor
        node_module = types.ModuleType('mininet.node')
        node_module.RemoteController = Mock()
        node_module.OVSSwitch = Mock()
        link_module = types.ModuleType('mininet.link')
        link_module.TCLink = Mock()
        process = Mock()
        process.poll.return_value = None
        modules = {'mininet.net': net_module, 'mininet.node': node_module, 'mininet.link': link_module}
        with tempfile.TemporaryDirectory() as directory, \
                patch.dict(sys.modules, modules), \
                patch('evaluation.benchmark.wait_for_controller'), \
                patch('evaluation.benchmark.subprocess.Popen', return_value=process):
            with self.assertRaisesRegex(RuntimeError, 'interface creation failed'):
                run_benchmark_scenario_mininet('baseline', directory)
        self.assertFalse(constructor.call_args.kwargs['build'])
        network.stop.assert_called_once()
        process.terminate.assert_called_once()
        network.start.assert_not_called()


class TestConnectivityDiagnostics(unittest.TestCase):
    def test_failed_pair_is_logged_and_reported(self):
        import io
        from evaluation.benchmark import check_connectivity
        first, second = Mock(), Mock()
        first.name, second.name = 'h_load', 'h_client1'
        first.cmd.return_value = '2 packets transmitted, 0 received'
        second.cmd.return_value = '2 packets transmitted, 2 received'
        net = Mock(hosts=[first, second])
        net._parsePing.side_effect = [(2, 0), (2, 2)]
        log = io.StringIO()
        self.assertEqual(check_connectivity(net, log), 50)
        self.assertIn('h_load -> h_client1: FAILED', log.getvalue())
        self.assertIn('h_client1 -> h_load: OK', log.getvalue())


class TestControllerStartup(unittest.TestCase):
    def test_waits_through_refused_connections(self):
        from evaluation.benchmark import wait_for_controller
        process = Mock()
        process.poll.return_value = None
        with patch('evaluation.benchmark.socket.create_connection',
                   side_effect=[ConnectionRefusedError(), MagicMock()]) as connect, \
                patch('evaluation.benchmark.time.sleep') as sleep:
            wait_for_controller(process)
        self.assertEqual(connect.call_count, 2)
        sleep.assert_called_once_with(.1)

    def test_exited_controller_is_reported_immediately(self):
        from evaluation.benchmark import wait_for_controller
        process = Mock()
        process.poll.return_value = 1
        with patch('evaluation.benchmark.socket.create_connection') as connect:
            with self.assertRaisesRegex(RuntimeError, 'exited during startup'):
                wait_for_controller(process)
        connect.assert_not_called()

    def test_listener_wait_has_a_deadline(self):
        from evaluation.benchmark import wait_for_controller
        process = Mock()
        process.poll.return_value = None
        with patch('evaluation.benchmark.time.monotonic', side_effect=[0, 0, 16]), \
                patch('evaluation.benchmark.time.sleep'), \
                patch('evaluation.benchmark.socket.create_connection', side_effect=ConnectionRefusedError()):
            with self.assertRaisesRegex(RuntimeError, 'did not listen'):
                wait_for_controller(process)


if __name__ == '__main__':
    unittest.main()
