"""Terminal menu for the Linux VM demonstration."""

import argparse
import logging
from pathlib import Path
import subprocess
import sys

from evaluation.benchmark import check_environment, run_benchmark


def show_summary(directory):
    path = directory / 'summary_metrics.md'
    if path.exists():
        print(path.read_text())
    else:
        print('No summary yet. Generate plots for a completed comparison first.')


def make_plots(directory):
    subprocess.run([sys.executable, '-m', 'evaluation.plot_results',
                    '--data-dir', str(directory), '--out-dir', str(directory / 'plots')], check=True)


def menu():
    duration = 60.0
    latest = None
    while True:
        print(f'''
Network Time Synchronization | Team 11
Linux VM / Mininet / OS-Ken

  1  Check environment
  2  Run baseline (Path A, best effort)
  3  Run optimized (QoS and automatic rerouting)
  4  Run comparison (baseline, then optimized)
  5  Generate plots for a comparison
  6  Show summary
  7  Set duration (currently {duration:g}s per scenario)
  8  Run tests
  0  Exit

Results: {latest or 'no run selected'}''')
        try:
            choice = input('Select: ').strip()
            if choice == '0':
                return
            if choice == '1':
                check_environment()
                print('Environment checks passed.')
            elif choice in ['2', '3', '4']:
                scenario = {'2': 'baseline', '3': 'optimized', '4': 'both'}[choice]
                latest = run_benchmark(duration=duration, scenario=scenario)
            elif choice in ['5', '6']:
                entered = input(f'Results directory [{latest or "required"}]: ').strip()
                directory = Path(entered).expanduser() if entered else latest
                if directory is None or not directory.is_dir():
                    print('Enter an existing results directory.')
                    continue
                latest = directory
                if choice == '5':
                    make_plots(directory)
                else:
                    show_summary(directory)
            elif choice == '7':
                value = float(input('Seconds per scenario (9–3600; 60 recommended): '))
                if not 9 <= value <= 3600:
                    raise ValueError('Choose a duration between 9 and 3600 seconds.')
                duration = value
            elif choice == '8':
                subprocess.run([sys.executable, '-m', 'unittest', 'discover', '-s', 'tests'], check=True)
            else:
                print('Choose one of the listed options.')
        except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as error:
            print(f'Could not complete action: {error}')
        except EOFError:
            return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--batch', action='store_true', help='Run without the menu')
    parser.add_argument('--scenario', choices=['baseline', 'optimized', 'both'], default='both')
    parser.add_argument('--duration', type=float, default=60)
    parser.add_argument('--interval', type=float, default=0.5)
    parser.add_argument('--output-dir')
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(message)s')
    try:
        if args.batch:
            run_benchmark(output_dir=args.output_dir, duration=args.duration,
                          interval=args.interval, scenario=args.scenario)
        elif not sys.stdin.isatty():
            parser.error('Interactive menu needs a terminal; use --batch for automation.')
        else:
            menu()
    except KeyboardInterrupt:
        print('\nStopped.')
        return 130
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
