"""Score AgentLens-Bench trajectories under the v1 reference protocol.

For every draw in leaderboard/references/v1.json, each trajectory is matched
against the reference PTA merged from its donor list (see protocol.py) and
assessed with swe_trace_sdk.match.quality_assessment. Pass/fail comes from the
dataset annotations. Writes one row per trajectory and draw to
leaderboard/results/v1_scores.csv, which leaderboard/build.py aggregates.

Usage (requires the SDK: pip install ./sdk):
    python leaderboard/build_references.py   # if references/v1.json is missing
    python leaderboard/score.py
"""

from __future__ import annotations

import csv
import json
import time
from pathlib import Path

from swe_trace_sdk import match, trace as trace_api

import protocol

HERE = Path(__file__).resolve().parent
BENCH = protocol.ROOT / "agentlens-bench"
REFERENCES = HERE / "references" / f"{protocol.VERSION}.json"
OUT = HERE / "results" / f"{protocol.VERSION}_scores.csv"


def main() -> None:
    refs = json.loads(REFERENCES.read_text(encoding="utf-8"))
    rows = protocol.load_annotations()
    by_task: dict[str, list[dict]] = {}
    for r in rows:
        by_task.setdefault(r["task_id"], []).append(r)

    start = time.time()
    out = []
    for seed, draw in refs["draws"].items():
        for task in sorted(by_task):
            task_dir = BENCH / "trajectories" / task
            traces: dict[str, object] = {}

            def load(tid: str):
                if tid not in traces:
                    traces[tid] = trace_api.load(str(task_dir / f"{tid}.json"), format="trace")
                return traces[tid]

            merged: dict[tuple, object] = {}
            for r in sorted(by_task[task], key=lambda r: r["trajectory_id"]):
                donors, fallback = protocol.reference_for(draw, task, r["model"], r["trajectory_id"])
                key = tuple(donors)
                if key not in merged:
                    merged[key] = trace_api.merge([load(d) for d in donors], use_llm=False)
                reference = merged[key]
                candidate = load(r["trajectory_id"])
                passed = r["passed"] == "True"
                result = match.run(candidate, reference, use_llm=False)
                report = match.quality_assessment(result, candidate, reference, passed=passed)
                out.append({
                    "trajectory_id": r["trajectory_id"],
                    "task_id": task,
                    "model": r["model"],
                    "passed": passed,
                    "draw": seed,
                    "quality_score": report.quality_score,
                    "k": len(donors),
                    "fallback": fallback,
                })
        print(f"draw {seed}: done ({time.time() - start:.0f}s)")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(out[0]))
        writer.writeheader()
        writer.writerows(out)
    print(f"Scored {len(rows)} trajectories x {len(refs['draws'])} draws in {time.time() - start:.0f}s -> {OUT.relative_to(protocol.ROOT)}")


if __name__ == "__main__":
    main()
