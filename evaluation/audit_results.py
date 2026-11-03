"""Recompute recorded metrics and recovery checks from the preserved VM archive."""

import csv
import hashlib
import json
from pathlib import Path
import re
import sys
import tarfile
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from evaluation.plot_results import load_datasets, compute_summary_table
from evaluation.benchmark import sync_request_count, verify_recovery
from evaluation.summarize_runs import summarize_runs

ARCHIVE = ROOT / 'evaluation/reference/vm-results.tar.gz'
OUTPUT = ROOT / 'evaluation/runs/audit'
OUTPUT.mkdir(parents=True, exist_ok=True)
trials, audits, phases, totals = [], [], [], {}
with tempfile.TemporaryDirectory() as directory:
    with tarfile.open(ARCHIVE) as archive:
        for member in archive.getmembers():
            if not (member.isdir() or member.isfile()) or '..' in Path(member.name).parts:
                raise ValueError(f'Unexpected archive entry: {member.name}')
        archive.extractall(directory, filter='data')
    runs = Path(directory) / 'evaluation/runs'
    (OUTPUT / 'raw_review.md').write_text(summarize_runs(runs))
    (OUTPUT / 'environment.txt').write_text((runs / 'environment.txt').read_text())
    for run in sorted(runs.iterdir()):
        if not run.is_dir():
            continue
        metadata = json.loads((run / 'run.json').read_text())
        if metadata.get('status') != 'complete':
            continue
        if metadata['scenario'] == 'recovery':
            import pandas as pd
            recovery = verify_recovery(run, pd.read_csv(run / 'sdn_optimized_metrics.csv').to_dict('records'))
            continue
        if metadata['scenario'] != 'both':
            continue
        frames = load_datasets(run)
        stats, summary = compute_summary_table(*frames)
        matching_summary = summary == (run / 'summary_metrics.md').read_text()
        if not matching_summary:
            raise ValueError(f'Summary does not match raw data: {run.name}')
        for index, (mode, frame) in enumerate(zip(['baseline', 'optimized'], frames)):
            status = frame.status.value_counts().to_dict()
            server_log = (run / mode / 'server.log').read_text()
            server = {(int(c), int(seq)) for c, seq in re.findall(r'Client ID: (\d+) \| Seq: (\d+)', server_log)}
            failed = frame[frame.status != 'SUCCESS']
            handled_failures = sum((int(r.client_id[-1]), int(r.seq)) in server for r in failed.itertuples())
            successful_not_logged = sum((int(r.client_id[-1]), int(r.seq)) not in server
                                        for r in frame[frame.status == 'SUCCESS'].itertuples())
            if successful_not_logged:
                raise ValueError('Successful response missing from server log')
            row = dict(run=run.name, mode=mode, samples=len(frame), success=int(status.get('SUCCESS', 0)),
                       timeout=int(status.get('TIMEOUT', 0)), invalid=int(status.get('INVALID', 0)))
            row.update({key: float(values[index]) for key, values in stats.items()})
            trials.append(row)
            qdisc = (run / mode / 'phase3-qdisc.txt').read_text()
            impairment_present = bool(re.search(r'delay\s+50ms\s+15ms', qdisc)) and 'limit 100' in qdisc
            if not impairment_present:
                raise ValueError(f'Impairment missing from {run.name}/{mode} qdisc snapshot')
            audits.append(dict(run=run.name, mode=mode, summary_matches_raw=matching_summary,
                               phase3_impairment_present=impairment_present,
                               normal_samples_all_success=bool((frame[frame.phase == 'Phase 1: Normal'].status == 'SUCCESS').all()),
                               failed_requests_logged_by_server=int(handled_failures),
                               successful_requests_missing_server_log=int(successful_not_logged),
                               path_b_requests=sync_request_count(run / mode / 'phase2-s1-flows.txt', 200, 6)))
            total = totals.setdefault(mode, dict(samples=0, success=0, timeout=0, invalid=0))
            for key in total:
                total[key] += row[key]
            for phase, group in frame.groupby('phase'):
                phases.append(dict(run=run.name, mode=mode, phase=phase, samples=len(group),
                                   timeout=int((group.status == 'TIMEOUT').sum()),
                                   invalid=int((group.status == 'INVALID').sum()),
                                   mean_error_ms=float(group.true_residual_error_ms.mean())))
    for name, rows in [('trial_metrics.csv', trials), ('phase_metrics.csv', phases)]:
        with (OUTPUT / name).open('w', newline='') as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    result = dict(archive_sha256=hashlib.sha256(ARCHIVE.read_bytes()).hexdigest(),
                  comparison_count=len(trials) // 2, totals=totals, trials=trials,
                  checks=audits, recovery=recovery)
    (OUTPUT / 'audit.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(dict(totals=totals, archive_sha256=result['archive_sha256']), indent=2))
