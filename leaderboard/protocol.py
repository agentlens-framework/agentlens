"""AgentLens-Bench v1 reference protocol: which passing runs form each reference PTA.

This follows the paper (k = 5 passing runs of the same task, never including
the run being scored) with two changes:

1. Leave-one-model-out. A run from model M is scored against passing runs from
   other models only. Otherwise a model whose own runs are among the donors
   gains about 3 quality points per same-model donor, which a new submission
   (with no runs in the references) would never get.
2. Five fixed draws. Donor choice moves scores by a few points, so every run is
   scored under five independent draws and the leaderboard averages them.

Per draw (seed), using one random.Random(seed) for all tasks in sorted order:
shuffle the task's passing runs (sorted by trajectory id) once. The reference
for model M is the first k runs in that order whose model is not M. A new
submission, which has no runs in the pool, uses the first k runs in that order.
If fewer than 2 other-model runs exist (a task solved by only one model), the
run falls back to the first k other passing runs of any model, excluding itself,
and is flagged.

Only the standard library is used, so this runs anywhere, including CI.
"""

from __future__ import annotations

import csv
import random
from collections import defaultdict
from pathlib import Path
from typing import Dict, List

VERSION = "v1"
K = 5
MIN_DONORS = 2
SEEDS = (42, 1, 2, 3, 4)
SUBMISSION = "_submission"

ROOT = Path(__file__).resolve().parent.parent
ANNOTATIONS = ROOT / "agentlens-bench" / "annotations" / "trajectories.csv"


def load_annotations(path: Path = ANNOTATIONS) -> List[Dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def select_references(rows: List[Dict[str, str]], seed: int) -> Dict[str, Dict]:
    """Donor ids for one draw: {task: {"by_model": {model: [...]}, "submission": [...], "fallback": {run: [...]}}}."""
    by_task: Dict[str, List[Dict[str, str]]] = defaultdict(list)
    for r in rows:
        by_task[r["task_id"]].append(r)

    rng = random.Random(seed)
    out: Dict[str, Dict] = {}
    for task in sorted(by_task):
        runs = sorted(by_task[task], key=lambda r: r["trajectory_id"])
        order = [r for r in runs if r["passed"] == "True"]
        rng.shuffle(order)

        by_model = {}
        fallback = {}
        for model in sorted({r["model"] for r in runs}):
            donors = [r["trajectory_id"] for r in order if r["model"] != model][:K]
            by_model[model] = donors
            if len(donors) < MIN_DONORS:
                for r in runs:
                    if r["model"] == model:
                        fallback[r["trajectory_id"]] = [o["trajectory_id"] for o in order if o["trajectory_id"] != r["trajectory_id"]][:K]
        out[task] = {
            "by_model": by_model,
            SUBMISSION: [r["trajectory_id"] for r in order][:K],
            "fallback": fallback,
        }
    return out


def reference_for(refs: Dict[str, Dict], task: str, model: str, trajectory_id: str) -> tuple[List[str], bool]:
    """Donor ids used to score one run, and whether the fallback rule applied."""
    task_refs = refs[task]
    if trajectory_id in task_refs["fallback"]:
        return task_refs["fallback"][trajectory_id], True
    if model in task_refs["by_model"]:
        return task_refs["by_model"][model], False
    return task_refs[SUBMISSION], False


def all_references(rows: List[Dict[str, str]] | None = None) -> Dict[str, Dict]:
    rows = rows if rows is not None else load_annotations()
    return {
        "version": VERSION,
        "k": K,
        "min_donors": MIN_DONORS,
        "seeds": list(SEEDS),
        "draws": {str(seed): select_references(rows, seed) for seed in SEEDS},
    }
