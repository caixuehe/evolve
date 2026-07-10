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
