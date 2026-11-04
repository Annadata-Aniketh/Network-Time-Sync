"""Regressions for peer checks, bounded work, and malformed datagrams."""

import csv
import struct
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from app.background_traffic import SocketTrafficSender, run_iperf_client, start_background_traffic
from app.client import TimeSyncClient, VirtualClock
from app.protocol import PACKET_FORMAT, PKT_TYPE_REQUEST, PKT_TYPE_RESPONSE, TimeSyncPacket
from app.server import TimeServer
from sdn.controller import TimeSyncSDNController
from topology.custom_topo import _run_cmd


class TestServerAdmission(unittest.TestCase):
    def server(self, **options):
        server = TimeServer(**options)
        self.addCleanup(server.executor.shutdown, wait=True)
        return server

    def test_invalid_datagrams_never_enter_the_worker_pool(self):
        server = self.server()
        request = TimeSyncPacket(PKT_TYPE_REQUEST, 1, 1, 10).to_bytes()
        invalid = [
            b"",
            b"x",
            request[:-1],
            request + b"x",
            b"x" * 65507,
            TimeSyncPacket(PKT_TYPE_RESPONSE, 1, 1, 10).to_bytes(),
            struct.pack(PACKET_FORMAT, b"NTPS", 1, 1, 1, float("nan"), 0, 0),
        ]
        with patch.object(server.executor, "submit") as submit:
            for data in invalid:
                self.assertFalse(server.submit_request(Mock(), data, ("127.0.0.1", 1), 10))
        submit.assert_not_called()
        self.assertEqual(server.stats["invalid"], len(invalid))
        self.assertEqual(server.stats["pending"], 0)

    def test_overload_is_dropped_and_capacity_is_reusable(self):
        server = self.server(max_workers=1, max_pending=2)
        entered, release = threading.Event(), threading.Event()
        self.addCleanup(release.set)

        def slow_request(*args):
            entered.set()
            if not release.wait(3):
                raise RuntimeError("Worker test exceeded its deadline")

        server.handle_request = slow_request
        packet = TimeSyncPacket(PKT_TYPE_REQUEST, 1, 1, 10).to_bytes()
        self.assertTrue(server.submit_request(Mock(), packet, ("127.0.0.1", 1), 10))
        self.assertTrue(entered.wait(1))
        self.assertTrue(server.submit_request(Mock(), packet, ("127.0.0.1", 1), 10))
        for _ in range(1000):
            self.assertFalse(server.submit_request(Mock(), packet, ("127.0.0.1", 1), 10))
        self.assertEqual(server.stats["peak_pending"], 2)
        self.assertEqual(server.stats["overloaded"], 1000)
        release.set()
        server.executor.shutdown(wait=True)
        self.assertEqual(server.stats["pending"], 0)
        self.assertTrue(server._slots.acquire(blocking=False))
        self.assertTrue(server._slots.acquire(blocking=False))
        self.assertFalse(server._slots.acquire(blocking=False))

    def test_worker_failure_releases_capacity(self):
        server = self.server(max_workers=1, max_pending=1)
        server.handle_request = Mock(side_effect=OSError("Socket closed"))
        packet = TimeSyncPacket(PKT_TYPE_REQUEST, 1, 1, 10).to_bytes()
        self.assertTrue(server.submit_request(Mock(), packet, ("127.0.0.1", 1), 10))
        server.executor.shutdown(wait=True)
        self.assertEqual(server.stats["errors"], 1)
        self.assertEqual(server.stats["pending"], 0)
        self.assertTrue(server._slots.acquire(blocking=False))

    def test_invalid_worker_limits_fail_before_startup(self):
        for values in [(0, 1), (4, 2), (-1, 2)]:
            with self.subTest(values=values), self.assertRaises(ValueError):
                TimeServer(max_workers=values[0], max_pending=values[1])

    def test_default_listener_is_loopback(self):
        self.assertEqual(self.server().host, "127.0.0.1")


class TestClientPeerValidation(unittest.TestCase):
    def test_matching_packet_from_wrong_address_never_adjusts_clock(self):
        for address in [("127.0.0.2", 12300), ("127.0.0.1", 9999)]:
            with self.subTest(address=address), tempfile.TemporaryDirectory() as directory:
                clock = Mock()
                clock.get_time.side_effect = [10, 10.13]
                path = Path(directory) / "client.csv"
                client = TimeSyncClient(clock=clock, csv_path=str(path))
                sock = Mock()
                sock.recvfrom.return_value = (
                    TimeSyncPacket(PKT_TYPE_RESPONSE, 1, 1, 10, 10.05, 10.06).to_bytes(),
                    address,
                )
                client.sync_once(sock)
                clock.adjust.assert_not_called()
                with path.open() as stream:
                    self.assertEqual(list(csv.DictReader(stream))[0]["status"], "INVALID")

    def test_hostname_is_resolved_once_for_send_and_peer_check(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            patch("app.client.socket.gethostbyname", return_value="127.0.0.1") as resolve,
        ):
            client = TimeSyncClient(
                server_ip="reference.example", csv_path=f"{directory}/client.csv"
            )
            self.assertEqual(client.server_address, ("127.0.0.1", 12300))
            resolve.assert_called_once_with("reference.example")

    def test_invalid_client_settings_do_not_create_output(self):
        for options in [
            dict(interval=0),
            dict(timeout=float("nan")),
            dict(method="invalid"),
            dict(client_id=65536),
            dict(server_port=0),
        ]:
            with self.subTest(options=options), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "client.csv"
                with self.assertRaises(ValueError):
                    TimeSyncClient(csv_path=str(path), **options)
                self.assertFalse(path.exists())

    def test_invalid_clock_values_cannot_poison_corrections(self):
        for options in [
            dict(initial_offset=float("inf")),
            dict(drift_rate=-1),
            dict(max_slew_rate=0),
        ]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                VirtualClock(**options)
        clock = VirtualClock()
        for offset, method in [(float("nan"), "step"), (1, "invalid")]:
            with self.assertRaises(ValueError):
                clock.adjust(offset, method)
        self.assertEqual(clock.correction, 0)


class TestTrafficSafety(unittest.TestCase):
    def test_invalid_rates_and_sizes_fail_before_socket_creation(self):
        for options in [
            dict(rate_mbps=0),
            dict(rate_mbps=float("inf")),
            dict(packet_size=0),
            dict(packet_size=65508),
        ]:
            with self.subTest(options=options), self.assertRaises(ValueError):
                SocketTrafficSender(**options)

    def test_fractional_load_does_not_become_unlimited_iperf(self):
        with (
            patch("app.background_traffic.shutil.which", return_value="/usr/bin/iperf"),
            patch("app.background_traffic.subprocess.run") as run,
        ):
            self.assertTrue(run_iperf_client(duration=0.2, bandwidth="0.5M"))
            command = run.call_args.args[0]
            self.assertEqual(command[command.index("-t") + 1], "1")
            self.assertEqual(run.call_args.kwargs["timeout"], 6)

    def test_fractional_rate_is_preserved_by_the_background_helper(self):
        with patch("app.background_traffic.run_iperf_client", return_value=True) as run:
            thread, _ = start_background_traffic(rate_mbps=0.5, duration=0.2)
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(run.call_args.kwargs["bandwidth"], "0.5M")
            self.assertEqual(run.call_args.kwargs["duration"], 1)

    def test_topology_commands_never_use_a_shell(self):
        with patch("topology.custom_topo.subprocess.run") as run:
            run.return_value = Mock(returncode=0, stdout="ok", stderr="")
            self.assertEqual(_run_cmd(["echo", "$(touch should-not-exist)"]), (0, "ok", ""))
            self.assertIsInstance(run.call_args.args[0], list)
            self.assertFalse(run.call_args.kwargs.get("shell", False))


class TestControllerSettings(unittest.TestCase):
    def test_unknown_mode_is_rejected(self):
        with patch.dict("os.environ", SDN_MODE="invalid"), self.assertRaises(ValueError):
            TimeSyncSDNController()

    def test_invalid_polling_cannot_start_a_tight_loop(self):
        for value in [0, -1, float("nan"), float("inf")]:
            with (
                self.subTest(value=value),
                patch.object(
                    TimeSyncSDNController,
                    "_load_configuration",
                    return_value={"poll_interval_sec": value},
                ),
                self.assertRaises(ValueError),
            ):
                TimeSyncSDNController()
