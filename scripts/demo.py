"""Terminal menu for the Linux VM demonstration."""

import argparse
import logging
import subprocess
import sys
from pathlib import Path

from evaluation.benchmark import check_environment, run_benchmark
from scripts.terminal import Terminal


def show_summary(directory, terminal=None):
    path = directory / "summary_metrics.md"
    if path.exists():
        (terminal or Terminal()).summary(path.read_text())
    else:
        print("No summary yet. Generate plots for a completed comparison first.")


def make_plots(directory, terminal=None):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "evaluation.plot_results",
            "--data-dir",
            str(directory),
            "--out-dir",
            str(directory / "plots"),
        ],
        capture_output=True,
        text=True,
    )
    (directory / "plotting.log").write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Plotting failed; see plotting.log.")
    show_summary(directory, terminal)
    (terminal or Terminal()).notice(f"Plots saved: {directory / 'plots'}", "green")


def menu(duration=60.0, color=True):
    latest = None
    terminal = Terminal(color=color)
    while True:
        terminal.menu(duration, latest)
        try:
            choice = input("  › ").strip().lower()
            if choice == "0":
                return
            if choice == "1":
                check_environment()
                print("Environment checks passed.")
            elif choice in ["2", "3", "4", "9"]:
                scenario = {"2": "baseline", "3": "optimized", "4": "both", "9": "recovery"}[choice]
                if terminal.interactive:
                    with terminal.logs():
                        latest = run_benchmark(
                            duration=duration, scenario=scenario, observer=terminal.on_event
                        )
                    terminal.notice(f"Saved results: {latest}", "green")
                    if scenario == "recovery":
                        show_summary(latest, terminal)
                else:
                    latest = run_benchmark(duration=duration, scenario=scenario)
            elif choice in ["5", "6"]:
                entered = input(f"Results directory [{latest or 'required'}]: ").strip()
                directory = Path(entered).expanduser() if entered else latest
                if directory is None or not directory.is_dir():
                    print("Enter an existing results directory.")
                    continue
                latest = directory
                if choice == "5":
                    make_plots(directory, terminal)
                else:
                    show_summary(directory, terminal)
            elif choice == "7":
                value = float(input("Seconds per scenario (9–3600; 60 recommended): "))
                if not 9 <= value <= 3600:
                    raise ValueError("Choose a duration between 9 and 3600 seconds.")
                duration = value
            elif choice == "8":
                subprocess.run(
                    [sys.executable, "-m", "unittest", "discover", "-s", "tests"], check=True
                )
            elif choice == "i":
                terminal.explain()
            elif choice == "h":
                terminal.guide()
            elif choice == "w":
                terminal.notice("Try the interactive clocks: open web/index.html, or run:")
                terminal.line("  ./timesync web")
                terminal.line("  Browser: http://localhost:8080")
            else:
                terminal.notice("Choose one of the listed options.", "amber")
        except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as error:
            terminal.notice(f"Could not complete action: {error}", "red")
        except EOFError:
            return


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--explain", action="store_true", help="Explain the protocol with a terminal animation"
    )
    parser.add_argument("--no-color", action="store_true", help="Disable terminal colors")
    parser.add_argument("--batch", action="store_true", help="Run without the menu")
    parser.add_argument(
        "--scenario", choices=["baseline", "optimized", "both", "recovery"], default="both"
    )
    parser.add_argument("--duration", type=float, default=60)
    parser.add_argument("--interval", type=float, default=0.5)
    parser.add_argument("--output-dir")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    try:
        if args.explain:
            Terminal(color=not args.no_color).explain()
        elif args.batch:
            run_benchmark(
                output_dir=args.output_dir,
                duration=args.duration,
                interval=args.interval,
                scenario=args.scenario,
            )
        elif not sys.stdin.isatty():
            parser.error("Interactive menu needs a terminal; use --batch for automation.")
        else:
            menu(duration=args.duration, color=not args.no_color)
    except KeyboardInterrupt:
        print("\nStopped.")
        return 130
    except (ValueError, RuntimeError, OSError, subprocess.CalledProcessError) as error:
        print(error, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
