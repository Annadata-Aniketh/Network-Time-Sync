"""Review completed VM runs, including failure counts by phase."""

import argparse
import json
from pathlib import Path

from evaluation.plot_results import load_datasets, compute_summary_table


def summarize_runs(runs_dir):
    root = Path(runs_dir)
    if not root.is_dir():
        raise ValueError(f'Results directory does not exist: {root}')
    lines = ['# VM experiment review', '',
             'Generated from raw CSVs and run metadata. Failed samples are not equivalent to network packet loss.', '',
             '| Run | Duration (s) | Interval (s) | Mode | Samples | Success | Timeout | Invalid | Other | Mean RTT (ms) | Mean error (ms) |',
             '| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    phases, recovery, skipped = [], [], []
    comparisons = 0
    for run in sorted(path for path in root.iterdir() if path.is_dir()):
        metadata_path = run / 'run.json'
        if not metadata_path.exists():
            continue
        metadata = json.loads(metadata_path.read_text())
        if metadata.get('status') != 'complete':
            skipped.append(run.name)
            continue
        if metadata.get('scenario') == 'recovery':
            result = json.loads((run / 'recovery_check.json').read_text())
            recovery.append(f'- {run.name}: {"PASS" if result["passed"] else "FAIL"}; '
                            f'Path B requests={result["path_b_packets"]}; Path A counter='
                            f'{result["path_a_packets_before"]} → {result["path_a_packets_after"]}.')
            continue
        if metadata.get('scenario') != 'both':
            continue
        baseline, optimized = load_datasets(run)
        stats, _ = compute_summary_table(baseline, optimized)
        comparisons += 1
        for index, (mode, frame) in enumerate([('baseline', baseline), ('optimized', optimized)]):
            counts = failure_counts(frame)
            lines.append(f'| {run.name} | {metadata["duration"]:g} | {metadata["interval"]:g} | {mode} | '
                         f'{len(frame)} | {counts} | {stats["Mean RTT (ms)"][index]:.3f} | '
                         f'{stats["Mean Clock Error (ms)"][index]:.3f} |')
            for phase, group in frame.groupby('phase', sort=True):
                phases.append(f'| {run.name} | {mode} | {phase} | {len(group)} | {failure_counts(group)} |')
    if comparisons == 0:
        raise ValueError('No completed Mininet comparisons found; legacy CSVs are not used.')
    lines += ['', '## Failures by phase', '',
              '| Run | Mode | Phase | Samples | Success | Timeout | Invalid | Other |',
              '| --- | --- | --- | ---: | ---: | ---: | ---: | ---: |', *phases,
              '', 'TIMEOUT means no valid reply arrived within the socket wait. INVALID means a reply was received',
              'but failed packet/request validation. Neither count alone establishes network packet loss.',
              'A late reply can also affect the next attempt; inspect client logs alongside the phase counts.',
              'RTT uses successful samples only. Error is measured after correction and includes failed attempts.',
              '', '## Automatic recovery', '', *(recovery or ['No completed recovery run found.']),
              '', '## Incomplete runs excluded', '', ', '.join(skipped) if skipped else 'None.', '']
    return '\n'.join(lines)


def failure_counts(frame):
    statuses = frame['status']
    success = int((statuses == 'SUCCESS').sum())
    timeout = int((statuses == 'TIMEOUT').sum())
    invalid = int((statuses == 'INVALID').sum())
    other = len(frame) - success - timeout - invalid
    return f'{success} | {timeout} | {invalid} | {other}'


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs-dir', default='evaluation/runs')
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    try:
        content = summarize_runs(args.runs_dir)
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(content)
        print(content)
        print(f'Saved review: {output}')
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f'Cannot review runs: {error}\n')
