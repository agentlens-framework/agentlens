"""Build the AgentLens leaderboard data and inject it into website/leaderboard.html.

Baseline scores come from leaderboard/results/v1_scores.csv (written by
score.py under the reference protocol in protocol.py). Submitted agents come
from leaderboard/submissions/<name>/ (metadata.json + scores.csv, written by
score_submission.py). Quality and tier shares are computed per draw, then
averaged over draws. Waste statistics are available for baseline runs only.
Uses only the standard library so it can run in CI without extra dependencies.

Usage:
    python leaderboard/build.py
"""

from __future__ import annotations

import csv
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from statistics import mean, stdev

import protocol

HERE = Path(__file__).resolve().parent
ROOT = protocol.ROOT
V1_SCORES = HERE / "results" / f"{protocol.VERSION}_scores.csv"
SUBMISSIONS = HERE / "submissions"
PAGE = ROOT / "website" / "leaderboard.html"
MODELS = HERE / "models.json"

REPO_URL = "https://github.com/agentlens-framework/agentlens"

# Tier thresholds on the 0-100 quality score (see swe_trace_sdk.match).
IDEAL_MIN = 70
LUCKY_MAX = 47
PARTIAL_FAIL_MIN = 40
HIST_BIN = 5  # histogram bin width in score points

WASTE_COLUMNS = {
    "regression_loops": "regression_loop_waste",
    "blind_retries": "blind_retry_waste",
    "redundant_steps": "redundant_step_waste",
    "unnecessary_exploration": "unnecessary_exploration_waste",
    "cyclic_patterns": "cyclic_pattern_waste",
}


def _read_csv(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _rank(values: dict[str, float]) -> dict[str, int]:
    """Competition ranking, highest value first."""
    ordered = sorted(values.values(), reverse=True)
    return {k: ordered.index(v) + 1 for k, v in values.items()}


def _pct(n: float, d: float) -> float:
    return 100 * n / d if d else 0.0


def build_entry(entry_id: str, rows: list[dict], meta: dict, annotations: dict[str, dict]) -> dict:
    """One leaderboard entry from per-trajectory, per-draw score rows.

    ``rows`` need trajectory_id, task_id, passed, quality_score and draw. Waste
    statistics are added when the trajectories are AgentLens-Bench runs.
    """
    draws: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        draws[r["draw"]].append(r)
    n_draws = len(draws)

    # Per-draw statistics, averaged over draws
    per_draw = []
    for d_rows in draws.values():
        q = [int(r["quality_score"]) for r in d_rows if r["passed"] == "True"]
        fq = [int(r["quality_score"]) for r in d_rows if r["passed"] != "True"]
        per_draw.append({
            "quality": mean(q) if q else 0.0,
            "ideal": sum(x >= IDEAL_MIN for x in q),
            "lucky": sum(x < LUCKY_MAX for x in q),
            "partial_fail": sum(x >= PARTIAL_FAIL_MIN for x in fq),
            "passing": len(q),
            "failing": len(fq),
        })
    avg = {k: mean(d[k] for d in per_draw) for k in per_draw[0]}

    # Trajectory-level scores (mean over draws) for the interval and histogram
    runs = {r["trajectory_id"]: r for r in rows}
    traj: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        if r["passed"] == "True":
            traj[r["trajectory_id"]].append(int(r["quality_score"]))
    traj_means = [mean(v) for v in traj.values()]
    hist = [0.0] * (100 // HIST_BIN)
    for r in rows:
        if r["passed"] == "True":
            hist[min(int(r["quality_score"]) // HIST_BIN, len(hist) - 1)] += 1 / n_draws

    ann_pass = [annotations[t] for t, r in runs.items() if r["passed"] == "True" and t in annotations]
    counts = {k: round(avg[k]) for k in ("passing", "failing", "ideal", "lucky", "partial_fail")}
    counts["solid"] = counts["passing"] - counts["ideal"] - counts["lucky"]
    counts["off_track"] = counts["failing"] - counts["partial_fail"]
    n_pass = sum(r["passed"] == "True" for r in runs.values())
    return {
        "id": entry_id,
        "model": meta.get("name", entry_id),
        "org": meta.get("org", ""),
        "agent": meta.get("agent", ""),
        "source": meta.get("source", "submission"),
        "date": meta.get("date", ""),
        "trajectories_url": meta.get("trajectories_url", ""),
        "trajectories": len(runs),
        "tasks": len({r["task_id"] for r in runs.values()}),
        "pass_rate": round(_pct(n_pass, len(runs)), 1),
        "quality": round(avg["quality"], 1),
        "ci95": round(1.96 * stdev(traj_means) / math.sqrt(len(traj_means)), 1) if len(traj_means) > 1 else 0.0,
        "draw_sd": round(stdev(d["quality"] for d in per_draw), 1) if n_draws > 1 else 0.0,
        "draws": n_draws,
        "ideal": round(_pct(avg["ideal"], avg["passing"]), 1),
        "lucky": round(_pct(avg["lucky"], avg["passing"]), 1),
        "fallback_runs": len({r["trajectory_id"] for r in rows if r.get("fallback") == "True"}),
        "waste": {k: round(mean(float(a[c]) for a in ann_pass), 1) for k, c in WASTE_COLUMNS.items()} if ann_pass else None,
        "counts": counts,
        "hist": [round(h, 2) for h in hist],
    }


def main() -> None:
    annotations = {r["trajectory_id"]: r for r in protocol.load_annotations()}
    models = json.loads(MODELS.read_text(encoding="utf-8"))

    if not V1_SCORES.exists():
        raise SystemExit(f"{V1_SCORES.relative_to(ROOT)} not found. Run leaderboard/score.py first.")
    by_model: dict[str, list[dict]] = defaultdict(list)
    for r in _read_csv(V1_SCORES):
        by_model[r["model"]].append(r)
    entries = [build_entry(m, rows, {**models.get(m, {}), "source": "baseline"}, annotations) for m, rows in by_model.items()]

    for sub in sorted(p for p in SUBMISSIONS.glob("*") if (p / "scores.csv").exists()):
        meta = json.loads((sub / "metadata.json").read_text(encoding="utf-8"))
        entries.append(build_entry(f"sub-{sub.name}", _read_csv(sub / "scores.csv"), {**meta, "source": "submission"}, annotations))

    qs_rank = _rank({e["id"]: e["quality"] for e in entries})
    pr_rank = _rank({e["id"]: e["pass_rate"] for e in entries})
    for e in entries:
        e["solid"] = round(100 - e["ideal"] - e["lucky"], 1)
        e["quality_rank"] = qs_rank[e["id"]]
        e["pass_rank"] = pr_rank[e["id"]]
    entries.sort(key=lambda e: e["quality_rank"])

    data = {
        "benchmark": "AgentLens-Bench (47 SWE-bench Verified tasks)",
        "thresholds": {"ideal_min": IDEAL_MIN, "lucky_max": LUCKY_MAX, "partial_fail_min": PARTIAL_FAIL_MIN},
        "protocol": {"version": protocol.VERSION, "k": protocol.K, "seeds": list(protocol.SEEDS),
                     "references_url": f"{REPO_URL}/blob/main/leaderboard/references/{protocol.VERSION}.json"},
        "repo_url": REPO_URL,
        "hist_bin": HIST_BIN,
        "entries": entries,
    }
    payload = json.dumps(data, separators=(",", ":"))

    page = PAGE.read_text(encoding="utf-8")
    pattern = re.compile(r'(<script id="leaderboard-data" type="application/json">)(.*?)(</script>)', re.S)
    if not pattern.search(page):
        raise SystemExit(f"Data block not found in {PAGE}")
    PAGE.write_text(pattern.sub(lambda m: m.group(1) + payload + m.group(3), page, count=1), encoding="utf-8")
    n_sub = sum(e["source"] == "submission" for e in entries)
    print(f"Wrote {len(entries)} entries ({n_sub} submitted) to {PAGE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
