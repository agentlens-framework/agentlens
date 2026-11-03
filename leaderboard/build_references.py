"""Write the AgentLens-Bench v1 reference donor lists to leaderboard/references/v1.json.

The file lists, for every draw and task, which passing trajectories form each
reference PTA (see protocol.py). Reference PTAs are not stored; score.py
rebuilds them deterministically from these lists.

Usage:
    python leaderboard/build_references.py
"""

from __future__ import annotations

import json
from pathlib import Path

import protocol

OUT = Path(__file__).resolve().parent / "references" / f"{protocol.VERSION}.json"


def main() -> None:
    refs = protocol.all_references()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(refs, indent=1) + "\n", encoding="utf-8")
    n_fallback = sum(len(t["fallback"]) for t in refs["draws"][str(protocol.SEEDS[0])].values())
    print(f"Wrote {len(refs['draws'])} draws x {len(next(iter(refs['draws'].values())))} tasks "
          f"({n_fallback} fallback runs per draw) -> {OUT.relative_to(protocol.ROOT)}")


if __name__ == "__main__":
    main()
