import json
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from population import (parent_feature, candidate_feature_id,
                        should_branch, BRANCH_AFTER_CONSECUTIVE_FAILS)
from prepare import HARD_LIMITS

HEADER = "commit\tphase\tfeature\tscores\ttotal\tstatus\tsummary"


def _evolve(tmp_path, features=("F01",), rows=()):
    evolve = tmp_path / ".evolve"
    evolve.mkdir(exist_ok=True)
    (evolve / "spec.md").write_text(
        "".join(f"- [ ] {f}\n" for f in features))
    (evolve / "results.tsv").write_text(
        HEADER + "\n" + "".join("\t".join(r) + "\n" for r in rows))
    return str(evolve)


def _fail_rows(feature, n):
    return [[f"c{i}", "eval", feature, "6/6", "6.0", "fail", f"r{i}"]
            for i in range(n)]


def test_candidate_id_roundtrip():
    cid = candidate_feature_id("F01", 2)
    assert cid == "F01@cand2"
    assert parent_feature(cid) == "F01"
    assert parent_feature("F01") == "F01"


def test_hard_limits_extended():
    assert HARD_LIMITS["max_branching_rounds_per_feature"] == 1
    assert HARD_LIMITS["candidates_per_branching"] == 3


def test_should_branch_below_threshold(tmp_path):
    evolve = _evolve(tmp_path, rows=_fail_rows("F01", 3))
    branch, reason = should_branch(evolve, "F01")
    assert branch is False


def test_should_branch_at_threshold(tmp_path):
    evolve = _evolve(tmp_path,
                     rows=_fail_rows("F01", BRANCH_AFTER_CONSECUTIVE_FAILS))
    branch, reason = should_branch(evolve, "F01")
    assert branch is True
    assert "consecutive fails" in reason


def test_should_branch_budget_exhausted(tmp_path):
    evolve = _evolve(tmp_path,
                     rows=_fail_rows("F01", BRANCH_AFTER_CONSECUTIVE_FAILS))
    state_dir = Path(evolve) / "F01"
    state_dir.mkdir(exist_ok=True)
    (state_dir / "branching.json").write_text(json.dumps(
        {"round": 1, "completed": True, "winner_outcome": "none"}))
    branch, reason = should_branch(evolve, "F01")
    assert branch is False
    assert "budget" in reason
