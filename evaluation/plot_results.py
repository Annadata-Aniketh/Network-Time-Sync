
import argparse
import csv
import os
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt


def load_results(filename):
    rows = []

    with open(filename, newline="") as file:
        reader = csv.DictReader(file)

        for row in reader:
            try:
                row["rtt"] = float(row["rtt"])
                row["offset"] = float(row["offset"])
                row["seq_num"] = int(row["seq_num"])
                rows.append(row)
            except (ValueError, TypeError, KeyError):
                continue

    return rows


def plot_results(input_file, output_dir):
    os.makedirs(output_dir, exist_ok=True)

    if not os.path.isfile(input_file):
        raise FileNotFoundError(
            f"Results file not found: {input_file}\n"
            "Run the benchmark first."
        )

    rows = load_results(input_file)

    if not rows:
        raise ValueError(
            "No valid measurements found in the results CSV."
        )

    modes = sorted(set(row["mode"] for row in rows))

    # Plot 1: Clock offset by sample number.
    plt.figure()
    for mode in modes:
        selected = [r for r in rows if r["mode"] == mode]
        plt.plot(
            range(1, len(selected) + 1),
            [r["offset"] for r in selected],
            marker="o",
            label=mode,
        )
    plt.xlabel("Measurement number")
    plt.ylabel("Clock offset (ms)")
    plt.title("Clock Offset Over Measurements")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "offset_error_vs_time.png"))
    plt.close()

    # Plot 2: Round-trip time distribution.
    plt.figure()
    for mode in modes:
        selected = [r for r in rows if r["mode"] == mode]
        plt.hist(
            [r["rtt"] for r in selected],
            bins=10,
            alpha=0.6,
            label=mode,
        )
    plt.xlabel("Round-trip time (ms)")
    plt.ylabel("Number of measurements")
    plt.title("Round-Trip Time Distribution")
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "rtt_distribution.png"))
    plt.close()

    # Plot 3: Absolute clock offset.
    plt.figure()
    for mode in modes:
        selected = [r for r in rows if r["mode"] == mode]
        plt.plot(
            range(1, len(selected) + 1),
            [abs(r["offset"]) for r in selected],
            marker=".",
            label=mode,
        )
    plt.xlabel("Measurement number")
    plt.ylabel("Absolute clock offset (ms)")
    plt.title("Absolute Synchronization Error")
    plt.legend()
    plt.grid(True)
    plt.tight_layout()
    plt.savefig(os.path.join(output_dir, "absolute_offset.png"))
    plt.close()

    print(f"Created plots in: {output_dir}")
    for filename in os.listdir(output_dir):
        if filename.endswith(".png"):
            print(f"  {filename}")


def main():
    parser = argparse.ArgumentParser(
        description="Plot network time synchronization results"
    )
    parser.add_argument(
        "--input",
        default="evaluation/data/benchmark_results.csv",
    )
    parser.add_argument(
        "--output-dir",
        default="evaluation/plots",
    )
    args = parser.parse_args()

    plot_results(args.input, args.output_dir)


if __name__ == "__main__":
    main()
