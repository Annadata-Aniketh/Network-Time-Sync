"""The demo must distinguish measured data from its teaching animation."""

import io
import logging
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from evaluation.benchmark import wait_until
from scripts.terminal import Terminal, result_takeaways


class TestTerminal(unittest.TestCase):
    def test_live_frame_reads_samples_and_controller_recovery(self):
        stream = io.StringIO()
        terminal = Terminal(stream)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'client1.csv').write_text(
                'seq,status,rtt_ms,true_residual_error_ms\n'
                '7,SUCCESS,22.25,1.125\n8,TIMEOUT,,\n9,SU')
            (root / 'controller.log').write_text('Path B active\n')
            terminal.on_event(dict(kind='scenario_start', mode='optimized',
                                   duration=60, directory=directory))
            terminal.on_event(dict(kind='phase', phase='Congestion', elapsed=25))
            output = stream.getvalue()
            self.assertIn('Path B · alternate (controller reports)', output)
            self.assertIn('TIMEOUT', output)
            self.assertNotIn('22.250', output)  # The latest completed row is the timeout.
            self.assertIn('waiting for first sample', output)
            self.assertNotIn('\033', output)
            with (root / 'controller.log').open('a') as log:
                log.write('Primary Path A restored\n')
            terminal.on_event(dict(kind='phase', phase='Recovery', elapsed=45))
            self.assertIn('Path A · restored (controller reports)', stream.getvalue())

    def test_plain_explanation_is_labeled_and_does_not_sleep(self):
        stream = io.StringIO()
        with patch('scripts.terminal.time.sleep') as sleep:
            Terminal(stream).explain()
        sleep.assert_not_called()
        self.assertIn('ILLUSTRATION · not live packet tracing', stream.getvalue())
        self.assertIn('06 / 06', stream.getvalue())
        self.assertNotIn('\033', stream.getvalue())

    def test_summary_keeps_metric_table_before_its_notes(self):
        stream = io.StringIO()
        Terminal(stream).summary('# Results\n| Metric | Baseline | Optimized |\n'
                                 '| --- | --- | --- |\n| RTT | 120 | 22 |\n\nMeasured replies only.')
        output = stream.getvalue()
        self.assertLess(output.index('RTT'), output.index('Measured replies only.'))
        self.assertNotIn('|', output)

    def test_log_handler_is_restored_after_failure(self):
        root = logging.getLogger()
        previous = root.handlers[:]
        with self.assertRaises(RuntimeError):
            with Terminal(io.StringIO()).logs():
                raise RuntimeError('experiment failed')
        self.assertEqual(root.handlers, previous)

    def test_unterminated_csv_row_is_not_presented_as_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'client1.csv'
            path.write_text('seq,status,rtt_ms\n1,SUCCESS,22\n2,SUCCESS,7')
            terminal = Terminal(io.StringIO())
            terminal.state = {'directory': directory}
            terminal.read_samples()
            self.assertEqual(terminal.clients[0]['seq'], '1')
            path.write_text(path.read_text() + '\n')
            terminal.read_samples()
            self.assertEqual(terminal.clients[0]['seq'], '2')

    def test_phase_cues_explain_what_is_changing(self):
        terminal = Terminal(io.StringIO())
        for phase, mode, expected in [('Phase 1: Normal', 'baseline', 'drift'),
                                      ('Phase 2: iperf Congestion', 'optimized', 'Path B'),
                                      ('Phase 3: NetEm Delay+Jitter', 'baseline', 'bias'),
                                      ('Phase 3: Recovery (load stopped)', 'optimized', 'three')]:
            with self.subTest(phase=phase):
                terminal.state = dict(phase=phase, mode=mode)
                self.assertIn(expected, ' '.join(terminal.phase_context()))

    def test_guided_walkthrough_can_go_back_and_quit_without_starting_network(self):
        stream = io.StringIO()
        terminal = Terminal(stream)
        terminal.interactive = True
        with patch('builtins.input', side_effect=['', 'b', 'q']), \
                patch('scripts.terminal.time.sleep'):
            terminal.explain()
        self.assertIn('02 / 06', stream.getvalue())
        self.assertNotIn('03 / 06', stream.getvalue())
        self.assertEqual(terminal.frame_lines, 0)

    def test_wrapped_frame_counts_every_physical_line(self):
        stream = io.StringIO()
        terminal = Terminal(stream)
        terminal.interactive = True
        with patch('scripts.terminal.shutil.get_terminal_size', return_value=__import__('os').terminal_size((45, 30))):
            terminal.draw(['  ' + 'a simple explanation ' * 6, '  Done.'])
        self.assertEqual(terminal.frame_lines, len(stream.getvalue().splitlines()))
        self.assertNotIn('...', stream.getvalue())

    def test_result_takeaway_reports_slower_convergence_honestly(self):
        notes = result_takeaways('| Mean Clock Error (ms) | 50 | 1 | +98% |\n'
                                 '| Convergence Time (s) | 1 | 3 | -200% |')
        self.assertIn('lower', notes[0])
        self.assertIn('slower', notes[1])

    def test_result_takeaway_handles_worse_and_unavailable_results(self):
        self.assertIn('higher', result_takeaways('| Mean Clock Error (ms) | 1 | 5 | -400% |')[0])
        self.assertEqual(result_takeaways('| Mean Clock Error (ms) | N/A | nan | N/A |'), [])


class TestDemoSchedule(unittest.TestCase):
    def test_refresh_preserves_deadline_without_oversleeping(self):
        ticks = []
        with patch('evaluation.benchmark.time.monotonic', side_effect=[5, 5.25, 5.4]), \
                patch('evaluation.benchmark.time.sleep') as sleep:
            wait_until(5.4, lambda: ticks.append('refresh'))
        self.assertEqual(len(ticks), 3)
        self.assertAlmostEqual(sleep.call_args_list[0].args[0], .25)
        self.assertAlmostEqual(sleep.call_args_list[1].args[0], .15)
