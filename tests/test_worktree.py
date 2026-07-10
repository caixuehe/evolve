import subprocess
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from worktree import (feature_slug, base_branch, feature_branch,
                      worktree_path, create_feature_worktree,
                      remove_feature_worktree)


def _run(args, cwd):
    return subprocess.run(args, cwd=cwd, check=True,
                          capture_output=True, text=True)


def _git_repo(tmp_path):
    """Init a repo on branch evolve/demo with one commit and .evolve/."""
    _run(["git", "init", "-b", "evolve/demo", "."], tmp_path)
    _run(["git", "config", "user.email", "t@example.com"], tmp_path)
    _run(["git", "config", "user.name", "t"], tmp_path)
    (tmp_path / "app.txt").write_text("v1\n")
    _run(["git", "add", "."], tmp_path)
    _run(["git", "commit", "-m", "init"], tmp_path)
    evolve = tmp_path / ".evolve"
    evolve.mkdir()
    return str(evolve)


def test_feature_slug_sanitizes():
    assert feature_slug("F01 Pattern Mirror") == "F01-Pattern-Mirror"
    assert feature_slug("a/b:c") == "a-b-c"


def test_branch_and_path_naming(tmp_path):
    evolve = _git_repo(tmp_path)
    assert base_branch(evolve) == "evolve/demo"
    assert feature_branch(evolve, "F01 auth") == "evolve/demo/F01-auth"
    assert worktree_path(evolve, "F01 auth").endswith(
        ".evolve/worktrees/F01-auth")


def test_create_and_remove_worktree(tmp_path):
    evolve = _git_repo(tmp_path)
    wt = create_feature_worktree(evolve, "F01 auth")
    assert wt["created"] is True
    assert Path(wt["path"], "app.txt").exists()
    # branch exists
    r = subprocess.run(["git", "rev-parse", "--verify",
                        "evolve/demo/F01-auth"],
                       cwd=tmp_path, capture_output=True)
    assert r.returncode == 0
    # idempotent
    again = create_feature_worktree(evolve, "F01 auth")
    assert again["created"] is False
    assert again["path"] == wt["path"]

    remove_feature_worktree(evolve, "F01 auth")
    assert not Path(wt["path"]).exists()
    r = subprocess.run(["git", "rev-parse", "--verify",
                        "evolve/demo/F01-auth"],
                       cwd=tmp_path, capture_output=True)
    assert r.returncode != 0            # branch deleted too


def test_create_from_explicit_branch(tmp_path):
    evolve = _git_repo(tmp_path)
    _run(["git", "branch", "other-base"], tmp_path)
    wt = create_feature_worktree(evolve, "F02", from_branch="other-base")
    assert wt["branch"] == "evolve/demo/F02"
    assert Path(wt["path"]).exists()
