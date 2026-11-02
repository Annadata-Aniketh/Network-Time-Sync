"""Small terminal renderer with a plain-output fallback and no extra dependencies."""

from contextlib import contextmanager
import csv
import logging
import math
import os
from pathlib import Path
import re
import shutil
import sys
import textwrap
import time

ANSI = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')


class Terminal:
    def __init__(self, stream=None, color=True):
        self.stream = stream or sys.stdout
        self.interactive = self.stream.isatty() and os.environ.get('TERM') != 'dumb'
        self.color = self.interactive and color and 'NO_COLOR' not in os.environ
        self.frame_lines = 0
        self.state = {}
        self.last_sample_read = 0
        self.clients = []
        self.path = 'waiting for controller'

    @property
    def width(self):
        return min(shutil.get_terminal_size((90, 30)).columns, 110)

    def ink(self, value, style='muted'):
        codes = {'muted': '2', 'green': '38;5;115', 'red': '38;5;174',
                 'amber': '38;5;179', 'bold': '1', 'blue': '38;5;110'}
        return f'\033[{codes[style]}m{value}\033[0m' if self.color else str(value)

    def line(self, value=''):
        print(value, file=self.stream, flush=True)

    def rule(self):
        self.line(self.ink('─' * max(20, self.width - 4)))

    def clear_frame(self):
        if self.interactive and self.frame_lines:
            self.stream.write(f'\033[{self.frame_lines}A\033[J')
            self.stream.flush()
        self.frame_lines = 0

    def draw(self, lines):
        self.clear_frame()
        written = 0
        # Count wrapped lines so refreshing a narrow terminal never erases history.
        for line in lines:
            if len(ANSI.sub('', line)) > self.width - 2:
                wrapped = textwrap.wrap(ANSI.sub('', line), width=max(20, self.width - 2), subsequent_indent='  ')
            else:
                wrapped = [line]
            for part in wrapped:
                self.line(part)
                written += 1
        self.frame_lines = written if self.interactive else 0

    def notice(self, value, style='muted'):
        self.clear_frame()
        self.line('  ' + self.ink(value, style))

    def menu(self, duration, latest):
        self.line()
        self.rule()
        self.line('  ' + self.ink('timesync', 'bold') + self.ink('  /  network lab'))
        self.line('  UDP 12300  ·  Mininet  ·  OS-Ken  ·  Linux VM')
        self.rule()
        self.line('  ' + self.ink('RUN', 'green'))
        self.line('  2  Baseline                    3  Optimized')
        self.line('  4  Compare both modes          9  Verify automatic recovery')
        self.line()
        self.line('  ' + self.ink('REVIEW & SETUP', 'green'))
        self.line('  5  Generate plots              6  View results')
        self.line('  1  Check environment           7  Duration: ' + f'{duration:g}s per mode')
        self.line('  8  Run tests                   0  Exit')
        self.line()
        self.line('  i  Guided packet walkthrough   h  Ten-minute demo guide')
        self.line('  w  Interactive clock lab')
        self.line('  Start with i; use 4 to watch a real comparison.')
        self.rule()
        if latest:
            self.line('  ' + self.ink('Results  ') + str(latest))
        else:
            self.line('  ' + self.ink('Ready. Select an action; no experiment starts automatically.'))
        self.line()

    def read_samples(self):
        self.clients = []
        directory = Path(self.state['directory'])
        for client in range(1, 4):
            latest = None
            path = directory / f'client{client}.csv'
            if path.exists():
                try:
                    with path.open() as stream:
                        lines = stream.readlines()
                        if lines and not lines[-1].endswith('\n'):
                            lines.pop()  # A concurrent writer has not finished this row.
                        for row in csv.DictReader(lines):
                            if row.get('seq') and row.get('status') in ['SUCCESS', 'TIMEOUT', 'INVALID']:
                                latest = row
                except (OSError, csv.Error):
                    pass  # A writer may still be completing its first row.
            self.clients.append(latest)
        self.path = 'Path A · primary (initial policy)'
        try:
            log = (directory / 'controller.log').read_text(errors='replace')
            rerouted = log.rfind('Path B active')
            restored = log.rfind('Primary Path A restored')
            if rerouted > restored:
                self.path = 'Path B · alternate (controller reports)'
            elif restored >= 0:
                self.path = 'Path A · restored (controller reports)'
        except OSError:
            pass

    def phase_context(self):
        phase = self.state.get('phase', '')
        optimized = self.state.get('mode') == 'optimized'
        if 'Preparing' in phase:
            return 'BUILD  Connect four switches and check every host pair.', 'No samples yet. The experiment clock starts after setup.'
        if 'Recovery' in phase:
            return 'RECOVER  Background load has stopped.', 'Watch for Path A after three low-load polls; then verify flow counters.'
        if 'Congestion' in phase:
            return 'LOAD  UDP background traffic now competes on Path A.', (
                'Watch the route: the controller moves sync to Path B at 4 Mbps.' if optimized
                else 'Best effort: sync stays on Path A. Watch reply wait and timeouts.')
        if 'NetEm' in phase:
            return 'IMPAIR  Add delay and jitter to the forward link on Path A.', (
                'Path B avoids this link. Compare the clock gap with baseline.' if optimized
                else 'Unequal outward/return delay can bias the clock correction.')
        if 'complete' in phase.lower():
            return 'SAVED  Measurements and flow snapshots are ready.', 'Use 6 to interpret results; use 5 for plots.'
        return 'NORMAL  Three clients ask one server for the time over UDP.', 'Each reply corrects virtual time. The clocks drift between requests.'

    def network_lines(self, route, position=0, label=None):
        # Motion illustrates the logged route; it does not claim packet capture.
        a, b = ['─'] * 9, ['─'] * 9
        if route in ['A', 'B']:
            (a if route == 'A' else b)[position % 9] = '●'
        if self.width < 72:
            return [f'  {label or self.path}', '  clients → s1 → ' + ('s3' if route == 'B' else 's2') + ' → s4 → server']
        top = '                  ┌' + ''.join(a) + ' s2 · A ───────┐'
        bottom = '                  └' + ''.join(b) + ' s3 · B ───────┘'
        return [
            self.ink(top, 'green') if route == 'A' else top,
            '  clients → s1 ────┤                      s4 → reference',
            self.ink(bottom, 'green') if route == 'B' else bottom,
        ]

    def on_event(self, event):
        kind = event['kind']
        if kind == 'scenario_start':
            self.frame_lines = 0
            self.state = dict(event, elapsed=0, phase='Preparing controller and network')
            self.clients = []
            self.path = 'waiting for controller'
            self.last_sample_read = 0
        elif kind in ['phase', 'tick']:
            self.state.update(event)
            if time.monotonic() - self.last_sample_read >= 1 or kind == 'phase':
                self.read_samples()
                self.last_sample_read = time.monotonic()
        elif kind == 'scenario_complete':
            self.state.update(elapsed=self.state['duration'], phase='Scenario complete')
            self.read_samples()
        else:
            return
        duration = self.state['duration']
        elapsed = max(0, min(self.state['elapsed'], duration))
        filled = int(24 * elapsed / duration)
        bar = '━' * filled + '─' * (24 - filled)
        purpose, cue = self.phase_context()
        route = 'B' if self.path.startswith('Path B') else 'A' if self.path.startswith('Path A') else None
        position = int(time.monotonic() * 6) % 9 if self.interactive else 0
        lines = ['', '  ' + self.ink(self.state['mode'].upper(), 'green') + '  ' + self.state['phase'],
                 f'  {self.ink(bar, "green")}  {elapsed:5.1f} / {duration:g} s', '',
                 '  ' + purpose, '  ' + self.ink(cue), '']
        lines += self.network_lines(route, position)
        if self.width >= 72:
            lines.append('  ' + self.ink(self.path))
        compact = self.width < 72
        lines += ['', ('  CLIENT     RTT ms     GAP ms  STATUS' if compact else
                       f'  {"CLIENT":<12}{"SEQ":>7}{"RTT (ms)":>13}{"ERROR (ms)":>14}  STATUS')]
        for index in range(3):
            row = self.clients[index] if index < len(self.clients) else None
            if row:
                status = row['status']
                if compact:
                    line = f'  {index+1:<5}{number(row.get("rtt_ms")):>11}{number(row.get("true_residual_error_ms")):>11}  '
                else:
                    line = f'  client {index+1:<5}{row["seq"]:>7}{number(row.get("rtt_ms")):>13}{number(row.get("true_residual_error_ms")):>14}  '
                lines.append(line + self.ink(status, 'green' if status == 'SUCCESS' else 'amber'))
            else:
                lines.append(f'  client {index+1}   ' + self.ink('waiting for first sample'))
        if compact:
            lines += ['', '  RTT: reply wait. Gap: after attempt.',
                      '  CSV values; illustrated motion. Ctrl+C stops.', '']
        else:
            lines += ['', '  RTT = reply wait. Error = gap from server after the latest attempt.',
                      '  ' + self.ink('Numbers: real CSVs. Motion: route illustration, not capture. Ctrl+C stops.'), '']
        self.draw(lines)
        if kind == 'scenario_complete':
            self.frame_lines = 0  # Keep the finished scenario in scrollback.

    @contextmanager
    def logs(self):
        terminal = self

        class Handler(logging.Handler):
            def emit(self, record):
                terminal.notice(record.getMessage(), 'amber' if record.levelno >= logging.WARNING else 'muted')

        root = logging.getLogger()
        old = root.handlers[:]
        root.handlers = [Handler()]
        try:
            yield
        finally:
            self.frame_lines = 0
            root.handlers = old

    def table(self, rows):
        if not rows:
            return
        if self.width < 84:
            for row in rows[1:]:
                self.line('  ' + self.ink(row[0], 'bold'))
                self.line('    ' + '  '.join(f'{rows[0][i].split()[0]}: {row[i]}' for i in range(1, len(row))))
            return
        widths = [min(29, max(len(row[i]) for row in rows)) for i in range(len(rows[0]))]
        self.line()
        for index, row in enumerate(rows):
            self.line('  ' + '  '.join(cell[:widths[i]].ljust(widths[i]) for i, cell in enumerate(row)))
            if index == 0:
                self.line('  ' + self.ink('─' * min(sum(widths) + 6, self.width - 4)))
        self.line()

    def summary(self, content):
        self.line()
        for takeaway in result_takeaways(content):
            for line in textwrap.wrap(takeaway, width=max(30, self.width - 6)):
                self.line('  ' + self.ink(line, 'bold'))
        self.line()
        rows = []
        for line in content.splitlines():
            if line.startswith('|'):
                cells = [cell.strip().replace('**', '') for cell in line.strip('|').split('|')]
                if not all(re.fullmatch(r'[:\- ]+', c) for c in cells):
                    rows.append(cells)
                continue
            if rows:
                self.table(rows)
                rows = []
            if line.startswith('#'):
                self.line('  ' + self.ink(line.lstrip('# '), 'bold'))
            elif line.startswith('- PASS:') or line.startswith('- FAIL:'):
                ok = line.startswith('- PASS:')
                self.line('  ' + self.ink('[PASS]' if ok else '[FAIL]', 'green' if ok else 'red') + line.split(':', 1)[1])
            elif line.strip():
                for wrapped in textwrap.wrap(line, width=max(30, self.width - 6)):
                    self.line('  ' + self.ink(wrapped))
        self.table(rows)

    def guide(self):
        self.line()
        self.line('  ' + self.ink('TEN-MINUTE DEMO', 'bold'))
        for stamp, action in [('00–02', 'i  Explain drift, timestamps, and the two paths'),
                              ('02–05', '4  Run a 60-second-per-mode comparison'),
                              ('05–07', '5 / 6  Generate plots and inspect results'),
                              ('07–09', '9  Verify automatic recovery after load stops'),
                              ('09–10', 'Explain limits: virtual clocks, post-correction error, shared reference')]:
            self.line('  ' + self.ink(stamp, 'green') + ' min  ' + action)
        self.line()

    def explain(self):
        scenes = [
            ('Clocks drift apart', 'All clients begin 100 ms ahead; each runs at a different rate.', 'A',
             'Over 2 seconds: client 1 +140 ms, client 2 +70 ms, client 3 +160 ms.',
             'A shared reference is useful only if we keep asking it for the time.'),
            ('A request makes a round trip', 't0: client sends → t1: server receives → t2: replies → t3: client receives.', 'A',
             'UDP 12300 · three clients · one reference server',
             'The client records both ends of the trip; the server supplies the middle.'),
            ('Correct the time, then drift again', 'A client 100 ms ahead needs about −100 ms of correction on a symmetric path.', 'A',
             'gap: +100 ms → near 0 ms → grows again until the next reply',
             'RTT is waiting time. Clock error is the remaining gap. They are different.'),
            ('Make the primary path busy', 'UDP 5001 background load competes with sync traffic on Path A.', 'A',
             '12M offered · 10 Mbps core · baseline stays on this path',
             'A longer outward trip than return trip biases the four-timestamp estimate.'),
            ('Give sync a clearer path', 'The controller sees ≥4 Mbps and installs priority-200 rules for Path B.', 'B',
             'Sync takes s3; background traffic stays on Path A. Polls every 2 seconds.',
             'The network changes the route. The client still runs the same UDP protocol.'),
            ('Return when load clears', 'Three consecutive low-load polls remove the temporary Path B rules.', 'A',
             'Verify packets on B, removal of rules, then increasing Path A counters.',
             'Better timing alone cannot prove rerouting. That is why we save flow evidence.'),
        ]
        self.line()
        index = 0
        while index < len(scenes):
            title, explanation, route, detail, cue = scenes[index]
            frames = 9 if self.interactive and self.width >= 72 else 1
            for frame in range(frames):
                self.draw(['', '  ' + self.ink(f'{index+1:02} / 06   {title}', 'bold'),
                           '  ' + self.ink('ILLUSTRATION · not live packet tracing'), '',
                           *self.network_lines(route, frame, f'Path {route} · illustration'), '',
                           '  ' + explanation, '  ' + self.ink(detail, 'blue'), '',
                           '  EXPLAIN  ' + cue, '',
                           '  Enter: next   b: back   q: menu' if self.interactive else ''])
                if self.interactive:
                    time.sleep(.06)
            if self.interactive:
                # Leave this chapter visible while the presenter explains it.
                self.frame_lines = 0
                try:
                    answer = input('  › ').strip().lower()
                except EOFError:
                    return
                if answer == 'q':
                    return
                if answer == 'b':
                    index = max(0, index - 1)
                    continue
            index += 1
            self.frame_lines = 0
        self.frame_lines = 0


def number(value):
    try:
        parsed = float(value)
        return f'{parsed:.3f}' if math.isfinite(parsed) else '—'
    except (TypeError, ValueError):
        return '—'


def result_takeaways(content):
    """Interpret comparisons without promising that every metric improved."""
    metrics = {}
    for line in content.splitlines():
        if not line.startswith('|'):
            continue
        cells = [cell.strip() for cell in line.strip('|').split('|')]
        if len(cells) != 4:
            continue
        try:
            baseline, optimized = float(cells[1]), float(cells[2])
            if math.isfinite(baseline) and math.isfinite(optimized):
                metrics[cells[0]] = baseline, optimized
        except ValueError:
            continue
    notes = []
    if 'Mean Clock Error (ms)' in metrics:
        baseline, optimized = metrics['Mean Clock Error (ms)']
        direction = 'lower' if optimized < baseline else 'higher' if optimized > baseline else 'unchanged'
        notes.append(f'This run: optimized mean clock error is {direction}. This is the remaining gap, not reply wait.')
    if 'Convergence Time (s)' in metrics:
        baseline, optimized = metrics['Convergence Time (s)']
        if optimized > baseline:
            notes.append('Initial convergence was slower in optimized mode; the result does not show every metric improving.')
    return notes
