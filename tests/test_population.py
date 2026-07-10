import json
import subprocess
from pathlib import Path

import pytest
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from population import (parent_feature, candidate_feature_id,
                        should_branch, BRANCH_AFTER_CONSECUTIVE_FAILS,
                        spawn_candidates)
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


def _run(args, cwd):
    return subprocess.run(args, cwd=cwd, check=True,
                          capture_output=True, text=True)


def _git_evolve(tmp_path, rows=()):
    _run(["git", "init", "-b", "evolve/demo", "."], tmp_path)
    _run(["git", "config", "user.email", "t@example.com"], tmp_path)
    _run(["git", "config", "user.name", "t"], tmp_path)
    (tmp_path / "app.txt").write_text("v1\n")
    _run(["git", "add", "."], tmp_path)
    _run(["git", "commit", "-m", "init"], tmp_path)
    evolve = tmp_path / ".evolve"
    evolve.mkdir()
    (evolve / "spec.md").write_text("- [ ] F01\n")
    (evolve / "results.tsv").write_text(
        HEADER + "\n" + "".join("\t".join(r) + "\n" for r in rows))
    return str(evolve)


def test_spawn_candidates_creates_worktrees_and_seeds(tmp_path):
    evolve = _git_evolve(tmp_path)
    cands = spawn_candidates(evolve, "F01",
                             ["approach A", "approach B", "approach C"])
    assert len(cands) == 3
    for i, cand in enumerate(cands, 1):
        assert cand["feature_id"] == f"F01@cand{i}"
        assert Path(cand["path"], "app.txt").exists()
        strategy = Path(evolve) / cand["feature_id"] / "strategy.md"
        assert cand["approach"] in strategy.read_text()
    state = json.loads((Path(evolve) / "F01" / "branching.json").read_text())
    assert state["round"] == 1
    assert state["completed"] is False
    assert len(state["candidates"]) == 3


def test_spawn_candidates_caps_at_budget(tmp_path):
    evolve = _git_evolve(tmp_path)
    cands = spawn_candidates(evolve, "F01", ["a", "b", "c", "d", "e"])
    assert len(cands) == HARD_LIMITS["candidates_per_branching"]


def test_spawn_candidates_requires_approaches(tmp_path):
    evolve = _git_evolve(tmp_path)
    with pytest.raises(ValueError):
        spawn_candidates(evolve, "F01", [])
