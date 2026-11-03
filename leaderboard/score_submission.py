"""Score your own agent's runs on AgentLens-Bench for a leaderboard submission.

Each run is matched against the task's published reference PTAs (the
``_submission`` donors in references/v1.json, five fixed draws) exactly as the
leaderboard scores new agents. Scoring is deterministic and makes no LLM calls.

Input is a CSV with one row per run:

    task_id,trajectory,resolved
    django__django-11066,runs/django__django-11066/run1.json,true
    ...

``trajectory`` is a path (relative to the CSV) to an OpenHands
``trajectory_openhands.json`` or an ATIF ``trajectory.json``. ``resolved`` is
the pass/fail result from the official SWE-bench harness.

Usage (requires the SDK: pip install ./sdk):
    python leaderboard/score_submission.py runs.csv --format openhands \\
        --name "My Agent + Model" --model "my-model" --agent "MyScaffold" \\
        --out leaderboard/submissions/my-agent

Writes <out>/metadata.json and <out>/scores.csv, and prints a summary.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from datetime import date
from pathlib import Path
from statistics import mean

from swe_trace_sdk import match, trace as trace_api

import protocol

HERE = Path(__file__).resolve().parent
BENCH = protocol.ROOT / "agentlens-bench"
REFERENCES = HERE / "references" / f"{protocol.VERSION}.json"
TRUE = {"1", "true", "yes", "pass", "passed", "resolved"}


def read_runs(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    missing = {"task_id", "trajectory", "resolved"} - set(rows[0] if rows else {})
    if missing:
        raise SystemExit(f"{path}: missing column(s) {sorted(missing)}")
    for r in rows:
        r["trajectory"] = str((path.parent / r["trajectory"]).resolve())
        r["resolved"] = r["resolved"].strip().lower() in TRUE
    return rows


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", type=Path, help="CSV with task_id, trajectory, resolved")
    ap.add_argument("--format", required=True, choices=["openhands", "atif", "trace"], help="trajectory file format")
    ap.add_argument("--name", required=True, help="display name on the leaderboard")
    ap.add_argument("--model", required=True, help="model name and version")
    ap.add_argument("--agent", required=True, help="agent scaffold / harness")
    ap.add_argument("--org", default="", help="organization (optional)")
    ap.add_argument("--trajectories-url", default="", help="public link to your trajectories (required to submit)")
    ap.add_argument("--out", type=Path, required=True, help="output folder, e.g. leaderboard/submissions/my-agent")
    args = ap.parse_args()

    refs = json.loads(REFERENCES.read_text(encoding="utf-8"))
    tasks = {r["task_id"] for r in protocol.load_annotations()}
    runs = read_runs(args.runs)

    unknown = sorted({r["task_id"] for r in runs} - tasks)
    if unknown:
        raise SystemExit(f"Unknown task ids (not in AgentLens-Bench): {unknown[:5]}{' ...' if len(unknown) > 5 else ''}")
    covered = {r["task_id"] for r in runs}
    if covered != tasks:
        print(f"Warning: runs cover {len(covered)} of {len(tasks)} tasks. Missing: {sorted(tasks - covered)[:5]} ...", file=sys.stderr)

    candidates = {}
    for i, r in enumerate(runs):
        r["run_id"] = f"{r['task_id']}#{i}"
        candidates[r["run_id"]] = trace_api.load(r["trajectory"], format=args.format)

    by_task: dict[str, list[dict]] = defaultdict(list)
    for r in runs:
        by_task[r["task_id"]].append(r)

    out_rows = []
    for draw, draw_refs in refs["draws"].items():
        for task, task_runs in sorted(by_task.items()):
            donors = draw_refs[task][protocol.SUBMISSION]
            task_dir = BENCH / "trajectories" / task
            reference = trace_api.merge(
                [trace_api.load(str(task_dir / f"{d}.json"), format="trace") for d in donors], use_llm=False
            )
            for r in task_runs:
                result = match.run(candidates[r["run_id"]], reference, use_llm=False)
                report = match.quality_assessment(result, candidates[r["run_id"]], reference, passed=r["resolved"])
                out_rows.append({
                    "trajectory_id": r["run_id"],
                    "task_id": task,
                    "passed": r["resolved"],
                    "draw": draw,
                    "quality_score": report.quality_score,
                })
        print(f"draw {draw}: scored {len(runs)} runs")

    args.out.mkdir(parents=True, exist_ok=True)
    with (args.out / "scores.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(out_rows[0]))
        writer.writeheader()
        writer.writerows(out_rows)
    metadata = {
        "name": args.name,
        "model": args.model,
        "agent": args.agent,
        "org": args.org,
        "trajectories_url": args.trajectories_url,
        "format": args.format,
        "reference_version": refs["version"],
        "date": date.today().isoformat(),
    }
    (args.out / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")

    passing = [r for r in out_rows if r["passed"]]
    n_runs = len(runs)
    per_draw = defaultdict(list)
    for r in passing:
        per_draw[r["draw"]].append(r["quality_score"])
    quality = mean(mean(v) for v in per_draw.values()) if per_draw else float("nan")
    lucky = mean(sum(s < 47 for s in v) / len(v) for v in per_draw.values()) * 100 if per_draw else 0.0
    print(f"\n{args.name}: {n_runs} runs on {len(covered)} tasks | pass rate {100 * sum(r['resolved'] for r in runs) / n_runs:.1f}% "
          f"| quality {quality:.1f} | Lucky {lucky:.1f}%")
    print(f"Wrote {args.out}/metadata.json and {args.out}/scores.csv")


if __name__ == "__main__":
    main()
