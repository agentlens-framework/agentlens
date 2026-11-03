# AgentLens-Bench leaderboard

The [leaderboard](https://agentlens-framework.github.io/agentlens/leaderboard.html) ranks coding agents on the 47 SWE-bench Verified tasks of AgentLens-Bench by **process quality**: the mean AgentLens quality score (0–100) of each agent's passing runs, with the share of Ideal, Solid, and Lucky passes.

## Submit your agent

You run the benchmark with your own model and harness, score the runs on your machine, and open a pull request with the results. Scoring is deterministic, runs on CPU, and makes no LLM or API calls.

### 1. Get the benchmark

```bash
git clone https://github.com/agentlens-framework/agentlens
cd agentlens
pip install ./sdk
```

The task list is `agentlens-bench/annotations/tasks.csv` (column `task_id`, SWE-bench Verified instance ids). The reference runs used for scoring are in `agentlens-bench/trajectories/`.

### 2. Run your agent

- Run your agent on all 47 tasks, **five runs per task**.
- Check every patch with the official [SWE-bench harness](https://github.com/SWE-bench/SWE-bench) and record whether it was resolved.
- Save each run's trajectory as an OpenHands `trajectory_openhands.json` or an ATIF `trajectory.json`.

### 3. List your runs

Create `runs.csv` with one row per run. Paths are relative to the CSV file.

```csv
task_id,trajectory,resolved
django__django-11066,runs/django__django-11066/run1.json,true
django__django-11066,runs/django__django-11066/run2.json,false
```

### 4. Score

```bash
python leaderboard/score_submission.py runs.csv --format openhands \
  --name "My Agent" --model "my-model-2026-01" --agent "MyHarness" --org "My Lab" \
  --trajectories-url https://example.org/my-agent-trajectories \
  --out leaderboard/submissions/my-agent
```

Use `--format atif` for ATIF trajectories. The script scores every run against the same five reference draws used for the models on the leaderboard (about a minute per 200 runs), prints your quality score, pass rate, and Lucky rate, and writes:

- `leaderboard/submissions/my-agent/metadata.json`: name, model, harness, and the link to your trajectories
- `leaderboard/submissions/my-agent/scores.csv`: one score per run and reference draw

### 5. Open a pull request

Add your `leaderboard/submissions/my-agent/` folder in a pull request. `--trajectories-url` must point to a public download of the trajectories you scored (for example a release asset or a Hugging Face dataset). We re-score them before merging, then your agent appears on the leaderboard.

## How scores are computed

Each task's reference is a Prefix Tree Acceptor (PTA) merged from five passing runs of that task. A submitted agent is scored against the first five runs of each draw's shuffled order. A baseline model is scored only against runs from other models, so no model is compared against its own runs. Every run is scored under five fixed draws (seeds 42, 1, 2, 3, 4) and the leaderboard averages them. The donor lists for every draw, task, and model are in [`references/v1.json`](references/v1.json); `protocol.py` defines the rules.

Tiers: a passing run is **Ideal** at score ≥ 70, **Lucky** below 47, and **Solid** otherwise. A failing run is **Partial-fail** at score ≥ 40 and **Off-track** otherwise.

## For maintainers

All scripts run from the repository root.

| Step | Command | Needs |
|---|---|---|
| Regenerate donor lists | `python leaderboard/build_references.py` | standard library |
| Re-score the baseline runs (about 10 minutes) | `python leaderboard/score.py` | SDK |
| Rebuild the leaderboard page from baselines and `submissions/` | `python leaderboard/build.py` | standard library |

After merging a submission, run `build.py` and commit `website/leaderboard.html`; the Pages workflow publishes it.
