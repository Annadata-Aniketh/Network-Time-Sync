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
        # Leave room for narrow terminals; no escape sequences in redirected output.
        for line in lines:
            if len(ANSI.sub('', line)) > self.width - 2:
                line = ANSI.sub('', line)[:self.width - 5] + '...'
            self.line(line)
        self.frame_lines = len(lines) if self.interactive else 0

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
        self.line('  i  Animated explanation        h  Ten-minute demo guide')
        self.line('  w  Website instructions')
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
                        for row in csv.DictReader(stream):
                            if row.get('status') in ['SUCCESS', 'TIMEOUT', 'INVALID']:
                                latest = row
                except (OSError, csv.Error):
                    pass  # A writer may still be completing its first row.
            self.clients.append(latest)
        self.path = 'Path A · primary (initial policy)'
        try:
            log = (directory / 'controller.log').read_text()
            rerouted = log.rfind('Path B active')
            restored = log.rfind('Primary Path A restored')
            if rerouted > restored:
                self.path = 'Path B · alternate (controller reports)'
            elif restored >= 0:
                self.path = 'Path A · restored (controller reports)'
        except OSError:
            pass

    def on_event(self, event):
        kind = event['kind']
        if kind == 'scenario_start':
            self.frame_lines = 0
            self.state = dict(event, elapsed=0, phase='Preparing controller and network')
            self.clients = []
            self.path = 'waiting for controller'
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
        lines = ['', '  ' + self.ink(self.state['mode'].upper(), 'green') + '  ' + self.state['phase'],
                 f'  {self.ink(bar, "green")}  {elapsed:5.1f} / {duration:g} s',
                 '  clients → s1 → ' + self.ink('s3 → s4' if self.path.startswith('Path B') else 's2 → s4', 'green') + ' → reference',
                 '  ' + self.ink(self.path), '',
                 f'  {"CLIENT":<12}{"SEQ":>7}{"RTT (ms)":>13}{"ERROR (ms)":>14}  STATUS']
        for index in range(3):
            row = self.clients[index] if index < len(self.clients) else None
            if row:
                status = row['status']
                line = f'  client {index+1:<5}{row["seq"]:>7}{number(row.get("rtt_ms")):>13}{number(row.get("true_residual_error_ms")):>14}  '
                lines.append(line + self.ink(status, 'green' if status == 'SUCCESS' else 'amber'))
            else:
                lines.append(f'  client {index+1}   ' + self.ink('waiting for first sample'))
        lines += ['', '  ' + self.ink('Real CSV measurements · error after correction · Ctrl+C to stop'), '']
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
            ('Three clocks drift', 'Without correction, artificial drift changes each client clock.', 'A', '+100 ms initial error'),
            ('Exchange four timestamps', 't0 sends → t1 receives → t2 replies → t3 receives.', 'A', 'RTT = (t3−t0)−(t2−t1)'),
            ('Estimate the correction', 'offset = ((t1−t0)+(t2−t3))/2; add it to virtual time.', 'A', 'Symmetric delay is assumed'),
            ('Load the primary path', 'UDP 5001 background traffic competes with UDP 12300 sync.', 'A', '12M offered / 10 Mbps core'),
            ('Reroute under load', 'At ≥4 Mbps, the controller moves sync traffic to Path B.', 'B', 'Priority 200 / output port 6'),
            ('Recover automatically', 'Three consecutive low-load polls restore Path A.', 'A', 'Original rules remain intact'),
        ]
        self.line()
        for index, (title, explanation, route, detail) in enumerate(scenes):
            frames = 18 if self.interactive else 1
            for frame in range(frames):
                travel = '─' * frame + '●' + '─' * (frames - frame - 1)
                self.draw(['', '  ' + self.ink(f'{index+1:02} / 06   {title}', 'bold'),
                           '  ' + self.ink('ILLUSTRATION · not live packet tracing'), '',
                           '  client → s1 → ' + self.ink('s3 (Path B)' if route == 'B' else 's2 (Path A)', 'green') + ' → s4 → server',
                           '                  ' + self.ink(travel, 'green'), '',
                           '  ' + explanation, '  ' + self.ink(detail, 'blue'), ''])
                if self.interactive:
                    time.sleep(.055)
            if self.interactive:
                time.sleep(1)
            else:
                self.frame_lines = 0
        self.frame_lines = 0


def number(value):
    try:
        parsed = float(value)
        return f'{parsed:.3f}' if math.isfinite(parsed) else '—'
    except (TypeError, ValueError):
        return '—'
