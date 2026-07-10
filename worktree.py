"""
worktree.py -- Git worktree isolation for parallel Builders.

Each feature's B works in .evolve/worktrees/{slug} on branch
{base}--{slug}, where {base} is the evolve/<tag> branch of the MAIN
working tree. All functions here must be called from the main working
tree, not from inside a worktree.

Agent MUST NOT modify this file.

Import convention: imports from prepare/cascade happen lazily inside
function bodies (prepare re-exports this module at its end).
"""

import re
import subprocess
from pathlib import Path


def _repo_root(evolve_dir: str) -> str:
    """The project repo root is the parent of .evolve/."""
    return str(Path(evolve_dir).resolve().parent)


def _git(args: list, cwd: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git"] + args, cwd=cwd,
                          capture_output=True, text=True)


def feature_slug(feature: str) -> str:
    """Sanitize a feature name into a branch/dir-safe slug."""
    slug = re.sub(r"[^A-Za-z0-9._-]+", "-", feature).strip("-.")
    return slug or "feature"


def base_branch(evolve_dir: str) -> str:
    """Current branch of the main working tree (the evolve/<tag> branch)."""
    proc = _git(["rev-parse", "--abbrev-ref", "HEAD"], _repo_root(evolve_dir))
    if proc.returncode != 0:
        raise RuntimeError(f"git rev-parse failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def feature_branch(evolve_dir: str, feature: str) -> str:
    return f"{base_branch(evolve_dir)}--{feature_slug(feature)}"


def worktree_path(evolve_dir: str, feature: str) -> str:
    return str(Path(evolve_dir) / "worktrees" / feature_slug(feature))


def create_feature_worktree(evolve_dir: str, feature: str,
                            from_branch: str = None) -> dict:
    """Create (or reuse) the worktree + branch for a feature.

    Returns {"path": str, "branch": str, "created": bool}.
    Raises RuntimeError on git failure.
    """
    root = _repo_root(evolve_dir)
    branch = feature_branch(evolve_dir, feature)
    path = worktree_path(evolve_dir, feature)

    if Path(path).exists():
        return {"path": path, "branch": branch, "created": False}

    Path(path).parent.mkdir(parents=True, exist_ok=True)

    if _git(["rev-parse", "--verify", branch], root).returncode != 0:
        start = from_branch or base_branch(evolve_dir)
        proc = _git(["branch", branch, start], root)
        if proc.returncode != 0:
            raise RuntimeError(f"git branch failed: {proc.stderr.strip()}")

    proc = _git(["worktree", "add", path, branch], root)
    if proc.returncode != 0:
        raise RuntimeError(f"git worktree add failed: {proc.stderr.strip()}")

    return {"path": path, "branch": branch, "created": True}


def remove_feature_worktree(evolve_dir: str, feature: str,
                            delete_branch: bool = True) -> None:
    """Remove a feature's worktree (and branch). Idempotent."""
    root = _repo_root(evolve_dir)
    path = worktree_path(evolve_dir, feature)
    _git(["worktree", "remove", "--force", path], root)
    _git(["worktree", "prune"], root)
    if delete_branch:
        _git(["branch", "-D", feature_branch(evolve_dir, feature)], root)
