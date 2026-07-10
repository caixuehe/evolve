"""
population.py -- Population branching for stuck features.

Escalation ladder (loop.md documents the full flow):
    consecutive_fails >= 3  -> Mentor advice (existing behavior)
    consecutive_fails >= 6  -> BRANCH: spawn N candidate worktrees, each
                               seeded with a DISTINCT approach
    all candidates fail     -> forced_pass becomes AVAILABLE (user approval
                               still required; enforced by can_force_pass)

Candidate rounds are recorded in results.tsv with feature id
"{feature}@cand{i}" — auditable, but never spec.md features.

Agent MUST NOT modify this file.

Import convention: imports from prepare/worktree happen lazily inside
function bodies (prepare re-exports this module at its end).
"""

import json
from pathlib import Path

CAND_SEP = "@cand"
BRANCH_AFTER_CONSECUTIVE_FAILS = 6


def parent_feature(feature_id: str) -> str:
    """'F01@cand2' -> 'F01'; plain ids pass through."""
    return feature_id.split(CAND_SEP)[0]


def candidate_feature_id(feature: str, i: int) -> str:
    return f"{feature}{CAND_SEP}{i}"


def _state_path(evolve_dir: str, feature: str) -> Path:
    return Path(evolve_dir) / feature / "branching.json"


def _branching_state(evolve_dir: str, feature: str):
    """Read branching.json, or None if no branching round was started."""
    path = _state_path(evolve_dir, feature)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text())
    except (json.JSONDecodeError, OSError):
        return None


def _write_branching_state(evolve_dir: str, feature: str,
                           state: dict) -> None:
    path = _state_path(evolve_dir, feature)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2))


def should_branch(evolve_dir: str, feature: str) -> tuple:
    """Decide whether the escalation ladder has reached the branching
    step. Returns (branch: bool, reason: str). Code-enforced — O calls
    this instead of deciding by feel.
    """
    from prepare import scan_all_features, HARD_LIMITS

    info = next((f for f in scan_all_features(evolve_dir)
                 if f["name"] == feature), None)
    if info is None:
        return False, f"unknown feature: {feature}"

    state = _branching_state(evolve_dir, feature)
    rounds_used = state.get("round", 0) if state else 0
    if rounds_used >= HARD_LIMITS["max_branching_rounds_per_feature"]:
        return False, "branching budget exhausted"

    fails = info["consecutive_fails"]
    if fails >= BRANCH_AFTER_CONSECUTIVE_FAILS:
        return True, f"{fails} consecutive fails (>= " \
                     f"{BRANCH_AFTER_CONSECUTIVE_FAILS})"
    return False, (f"{fails} consecutive fails (< "
                   f"{BRANCH_AFTER_CONSECUTIVE_FAILS})")


def spawn_candidates(evolve_dir: str, feature: str,
                     approaches: list) -> list:
    """Fork N candidate worktrees for a stuck feature, each seeded with a
    distinct approach (O draws approaches from Mentor hypotheses and C's
    untried Pivot options).

    Returns [{"cand_id", "feature_id", "path", "branch", "approach"}].
    Raises ValueError if approaches is empty.
    """
    from prepare import HARD_LIMITS
    from worktree import (create_feature_worktree, feature_branch,
                          feature_slug, base_branch, _repo_root, _git)

    if not approaches:
        raise ValueError("spawn_candidates requires at least one approach")

    n = min(len(approaches), HARD_LIMITS["candidates_per_branching"])
    root = _repo_root(evolve_dir)

    # Fork from the feature's own branch if it exists, else the base branch.
    incumbent = feature_branch(evolve_dir, feature)
    if _git(["rev-parse", "--verify", "refs/heads/" + incumbent],
            root).returncode != 0:
        incumbent = base_branch(evolve_dir)

    state = _branching_state(evolve_dir, feature) or {"round": 0}
    candidates = []
    for i in range(1, n + 1):
        cand_name = f"{feature_slug(feature)}-cand{i}"
        wt = create_feature_worktree(evolve_dir, cand_name,
                                     from_branch=incumbent)
        feature_id = candidate_feature_id(feature, i)
        cand_dir = Path(evolve_dir) / feature_id
        cand_dir.mkdir(parents=True, exist_ok=True)
        (cand_dir / "strategy.md").write_text(
            f"# Candidate {i} strategy (seeded)\n\n"
            f"## Approach\n\n{approaches[i - 1]}\n\n"
            f"## Rules\n\n- Work ONLY in worktree {wt['path']}\n"
            f"- Record results.tsv rows with feature id {feature_id}\n"
        )
        candidates.append({"cand_id": i, "feature_id": feature_id,
                           "path": wt["path"], "branch": wt["branch"],
                           "approach": approaches[i - 1]})

    _write_branching_state(evolve_dir, feature, {
        "round": state.get("round", 0) + 1,
        "completed": False,
        "winner_outcome": None,
        "candidates": [{"cand_id": c["cand_id"],
                        "feature_id": c["feature_id"],
                        "branch": c["branch"],
                        "approach": c["approach"]} for c in candidates],
    })
    return candidates
