"""
Quality Distribution Figure
===========================
Reproduces the paper's Figure 1: the quality-score histogram of the passing
trajectories in AgentLens-Bench, shaded by tier (Lucky < 47, Solid, Ideal >= 70).

Reads the released annotations, so no SDK run is needed.

Usage:
    python experiments/plot_quality_distribution.py
    python experiments/plot_quality_distribution.py --csv agentlens-bench/annotations/trajectories.csv --out figures
"""

import argparse
import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPO_ROOT = Path(__file__).resolve().parent.parent
LUCKY_MAX_SCORE = 47  # passing runs below this are Lucky
IDEAL_MIN_SCORE = 70  # passing runs at or above this are Ideal

TIERS = [
    # (label, x position of the label, label color, shading color, lower, upper)
    ("Lucky", 23.5, "#e74c3c", "#e74c3c", 0, LUCKY_MAX_SCORE),
    ("Solid", 58.5, "#b7860b", "#f5b041", LUCKY_MAX_SCORE, IDEAL_MIN_SCORE),
    ("Ideal", 85.0, "#27ae60", "#2ecc71", IDEAL_MIN_SCORE, 100),
]


def load_passing_scores(csv_path: Path) -> list:
    with open(csv_path, newline="") as f:
        return [float(r["quality_score"]) for r in csv.DictReader(f) if r["passed"] == "True"]


def plot(scores: list, out_dir: Path) -> None:
    n = len(scores)
    counts = {name: sum(lo <= s < hi for s in scores) for name, _, _, _, lo, hi in TIERS}
    counts["Ideal"] += sum(s >= 100 for s in scores)  # the top bin includes 100

    plt.rcParams.update({"font.family": ["Arial", "Helvetica", "DejaVu Sans"], "pdf.fonttype": 42})
    fig, ax = plt.subplots(figsize=(5.4, 3.4))
    for _, _, _, shade, lo, hi in TIERS:
        ax.axvspan(lo, hi, color=shade, alpha=0.12, lw=0)
    ax.hist(scores, bins=[i * 2.5 for i in range(41)], color="#74b3e0", edgecolor="white", lw=0.8)
    ax.axvline(LUCKY_MAX_SCORE, color="#e74c3c", ls="--", lw=1.5)
    ax.axvline(IDEAL_MIN_SCORE, color="#2ecc71", ls="--", lw=1.5)

    # Leave headroom above the tallest bar so the tier labels never overlap the histogram.
    ax.set_ylim(0, 175)
    ax.set_yticks(range(0, 141, 20))
    for name, x, color, *_ in TIERS:
        c = counts[name]
        ax.text(x, 158, f"{name}\n{c} ({100 * c / n:.1f}%)", ha="center", va="center",
                color=color, fontsize=9, fontweight="bold")

    ax.set_xlim(0, 100)
    ax.set_xlabel("Quality Score", fontsize=11)
    ax.set_ylabel("Count", fontsize=11)
    ax.spines[["top", "right"]].set_visible(False)
    fig.tight_layout()

    out_dir.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_dir / "fig_quality_distribution.pdf")
    fig.savefig(out_dir / "fig_quality_distribution.png", dpi=300)
    print(f"{n} passing trajectories: " + ", ".join(f"{k} {v}" for k, v in counts.items()))
    print(f"Wrote {out_dir / 'fig_quality_distribution.pdf'} and .png")


def main():
    parser = argparse.ArgumentParser(description="Plot the quality-score distribution of passing trajectories (paper Figure 1).")
    parser.add_argument("--csv", type=Path, default=REPO_ROOT / "agentlens-bench" / "annotations" / "trajectories.csv",
                        help="AgentLens-Bench trajectory annotations")
    parser.add_argument("--out", type=Path, default=Path("figures"), help="Output directory")
    args = parser.parse_args()
    plot(load_passing_scores(args.csv), args.out)


if __name__ == "__main__":
    main()
