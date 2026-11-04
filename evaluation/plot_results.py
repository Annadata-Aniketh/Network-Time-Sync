"""Summarize and plot a completed Mininet comparison from its results directory."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

COLORS = ["#b54747", "#247357"]


def load_datasets(data_dir):
    directory = Path(data_dir)
    metadata = json.loads((directory / "run.json").read_text())
    if (
        metadata.get("backend") != "mininet"
        or metadata.get("scenario") != "both"
        or metadata.get("status") != "complete"
    ):
        raise ValueError("Select a completed Mininet comparison directory.")
    frames = [
        pd.read_csv(directory / name)
        for name in ["baseline_metrics.csv", "sdn_optimized_metrics.csv"]
    ]
    for frame in frames:
        if frame.empty or not (frame["status"] == "SUCCESS").any():
            raise ValueError("Both scenarios need successful samples.")
    return frames


def calculate_convergence_time(df, threshold_ms=2.0):
    """First three successive sample rounds where every client meets the target."""
    grouped = df.groupby("elapsed_sec")["true_residual_error_ms"].max()

    if "seq" in df:
        grouped = df.groupby("seq").agg(
            elapsed_sec=("elapsed_sec", "max"), error=("true_residual_error_ms", "max")
        )
        counts = (
            df.groupby("seq")["client_id"].nunique()
            if "client_id" in df
            else df.groupby("seq").size()
        )
        expected = df["client_id"].nunique() if "client_id" in df else counts.max()
        grouped.loc[counts < expected, "error"] = np.nan
        if "status" in df:
            valid = df.groupby("seq")["status"].apply(lambda values: (values == "SUCCESS").all())
            grouped.loc[~valid, "error"] = np.nan
        samples = zip(grouped["elapsed_sec"], grouped["error"], strict=False)
    else:
        samples = grouped.items()
    consecutive = 0
    for elapsed, error in samples:
        consecutive = consecutive + 1 if error <= threshold_ms else 0
        if consecutive == 3:
            return float(elapsed)
    return float("nan")


def compute_summary_table(df_base, df_opt):
    def values(frame):
        success = frame[frame["status"] == "SUCCESS"] if "status" in frame else frame
        return {
            "Mean RTT (ms)": success["rtt_ms"].mean(),
            "P95 RTT (ms)": success["rtt_ms"].quantile(0.95),
            "Mean Jitter (ms)": success["jitter_ms"].mean(),
            "Mean Clock Error (ms)": frame["true_residual_error_ms"].mean(),
            "P95 Clock Error (ms)": frame["true_residual_error_ms"].quantile(0.95),
            "Convergence Time (s)": calculate_convergence_time(frame),
            "Failed samples (%)": 100 * (frame["status"] != "SUCCESS").mean()
            if "status" in frame
            else np.nan,
        }

    baseline, optimized = values(df_base), values(df_opt)
    stats = {key: (baseline[key], optimized[key]) for key in baseline}
    lines = [
        "# Time synchronization results",
        "",
        "| Metric | Baseline Mode | SDN-Optimized Mode | Reduction (%) |",
        "| --- | ---: | ---: | ---: |",
    ]
    for metric, (base, opt) in stats.items():
        improvement = (
            f"{100 * (base - opt) / base:+.2f}%" if base > 0 and np.isfinite(opt) else "N/A"
        )
        b_text = f"{base:.3f}" if np.isfinite(base) else "N/A"
        o_text = f"{opt:.3f}" if np.isfinite(opt) else "N/A"
        lines.append(f"| {metric} | {b_text} | {o_text} | {improvement} |")
    lines += [
        "",
        "RTT and jitter use successful replies only. Clock error includes failed attempts.",
        "Clock error is sampled immediately after correction, not continuously between requests.",
        "Convergence requires three successive rounds with all clients at or below 2 ms.",
        "N/A means unavailable or not confirmed. Positive reduction means a lower measured value.",
        "Use controller logs and flow counters to verify rerouting; these plots do not establish when it happened.",
    ]
    return stats, "\n".join(lines) + "\n"


def generate_all_plots(data_dir, out_dir=None):
    directory = Path(data_dir)
    out = Path(out_dir) if out_dir else directory / "plots"
    baseline, optimized = load_datasets(directory)
    metadata = json.loads((directory / "run.json").read_text())
    duration = metadata["duration"]
    out.mkdir(parents=True, exist_ok=True)
    _, summary = compute_summary_table(baseline, optimized)
    (directory / "summary_metrics.md").write_text(summary)
    print(summary)
    frames = [baseline, optimized]
    labels = ["Baseline", "Optimized"]

    fig, ax = plt.subplots(figsize=(9, 5))
    for frame, label, color in zip(frames, labels, COLORS, strict=False):
        for index, (_, client) in enumerate(frame.groupby("client_id")):
            ax.plot(
                client["elapsed_sec"],
                client["true_residual_error_ms"],
                color=color,
                alpha=0.7,
                label=label if index == 0 else None,
            )
    for boundary in [duration / 3, 2 * duration / 3]:
        ax.axvline(boundary, color="gray", linestyle="--", linewidth=1)
    ax.set(
        xlabel="Elapsed time (s)",
        ylabel="Post-correction clock error (ms)",
        title="Clock error per client",
        xlim=(0, duration),
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "offset_vs_time.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 5))
    for frame, label, color in zip(frames, labels, COLORS, strict=False):
        rtts = np.sort(frame.loc[frame["status"] == "SUCCESS", "rtt_ms"].dropna())
        ax.step(
            rtts, np.arange(1, len(rtts) + 1) / len(rtts), where="post", color=color, label=label
        )
    ax.set(
        xlabel="RTT (ms)",
        ylabel="Fraction of successful replies",
        title="Measured RTT distribution",
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "rtt_distribution.png", dpi=160)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(8, 5))
    x = np.arange(3)
    for i, (frame, label, color) in enumerate(zip(frames, labels, COLORS, strict=False)):
        means = [
            frame.loc[
                (frame["status"] == "SUCCESS") & frame["phase"].str.startswith(f"Phase {p}"),
                "jitter_ms",
            ].mean()
            for p in [1, 2, 3]
        ]
        ax.bar(x + (i - 0.5) * 0.35, means, width=0.35, color=color, label=label)
    ax.set(
        xticks=x,
        xticklabels=["Normal", "Load", "Load + delay"],
        ylabel="Mean successive RTT difference (ms)",
        title="Jitter by phase",
    )
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "jitter_by_phase.png", dpi=160)
    plt.close(fig)
    print(f"Plots: {out}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", required=True)
    parser.add_argument("--out-dir")
    args = parser.parse_args()
    try:
        generate_all_plots(args.data_dir, args.out_dir)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"Cannot plot results: {error}\n")
