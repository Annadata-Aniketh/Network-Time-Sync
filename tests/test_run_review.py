"""Check failure classification and provenance handling in the run review."""

import json
from pathlib import Path
import tempfile
import unittest

from evaluation.benchmark import write_csv
from evaluation.summarize_runs import summarize_runs
from evaluation.sync_worker import CSV_HEADER


class TestRunReview(unittest.TestCase):
    def test_completed_runs_are_reviewed_without_calling_failures_packet_loss(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / 'comparison'
            run.mkdir()
            metadata = dict(status='complete', backend='mininet', scenario='both', duration=60, interval=.5)
            (run / 'run.json').write_text(json.dumps(metadata))
            rows = []
            for seq, status in enumerate(['SUCCESS', 'TIMEOUT', 'INVALID', 'UNEXPECTED'], 1):
                row = dict.fromkeys(CSV_HEADER, '')
                row.update(seq=seq, client_id='h_client1', elapsed_sec=seq, phase='Phase 1: Normal',
                           status=status, rtt_ms=10 if status == 'SUCCESS' else '',
                           true_residual_error_ms=1, jitter_ms=0 if status == 'SUCCESS' else '')
                rows.append(row)
            for name in ['baseline_metrics.csv', 'sdn_optimized_metrics.csv']:
                write_csv(run / name, rows)
            incomplete = root / 'failed-run'
            incomplete.mkdir()
            (incomplete / 'run.json').write_text(json.dumps(dict(status='incomplete')))
            recovery = root / 'recovery'
            recovery.mkdir()
            (recovery / 'run.json').write_text(json.dumps(dict(status='complete', scenario='recovery')))
            (recovery / 'recovery_check.json').write_text(json.dumps(dict(
                passed=True, path_b_packets=20, path_a_packets_before=10, path_a_packets_after=30)))
            report = summarize_runs(root)
            self.assertIn('| baseline | 4 | 1 | 1 | 1 | 1 | 10.000 | 1.000 |', report)
            self.assertIn('TIMEOUT means', report)
            self.assertIn('INVALID means', report)
            self.assertIn('recovery: PASS', report)
            self.assertIn('10 → 30', report)
            self.assertIn('failed-run', report)

    def test_legacy_data_without_metadata_is_not_used(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'legacy').mkdir()
            with self.assertRaisesRegex(ValueError, 'No completed Mininet comparisons'):
                summarize_runs(root)
