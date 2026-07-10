"""
cascade.py -- Deterministic verification cascade for Evolve.

Runs cheap deterministic stages (build / lint / test / smoke) fail-fast
BEFORE any LLM judging. Generalizes the chat adapter's gate_fail: a
trivially broken build never reaches (or pays for) the judge.

Agent MUST NOT modify this file.

Import convention: this module never imports prepare at top level
(prepare re-exports it; a top-level import would be circular).
"""

import subprocess
from pathlib import Path

DEFAULT_STAGE_TIMEOUT = 300  # seconds


def load_cascade_config(eval_yml_path: str) -> list:
    """Parse the optional top-level `cascade:` section of eval.yml.

    Schema (line-based, same constrained style as load_eval_config):

        cascade:
          - name: build
            cmd: npm run build
            timeout: 300        # optional, default DEFAULT_STAGE_TIMEOUT

    Returns [] if the file has no cascade section (old projects unchanged).
    Raises FileNotFoundError if eval.yml missing.
    Raises ValueError if a stage has no cmd.
    """
    path = Path(eval_yml_path)
    if not path.exists():
        raise FileNotFoundError(f"eval.yml not found: {eval_yml_path}")

    stages = []
    in_cascade = False
    current = None

    for line in path.read_text().split("\n"):
        stripped = line.strip()
        if stripped == "" or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if indent == 0:
            if current:
                stages.append(current)
                current = None
            in_cascade = stripped.startswith("cascade:")
            continue
        if not in_cascade:
            continue
        if stripped.startswith("- name:"):
            if current:
                stages.append(current)
            current = {
                "name": stripped.split(":", 1)[1].strip(),
                "timeout": DEFAULT_STAGE_TIMEOUT,
            }
        elif current is not None and stripped.startswith("cmd:"):
            current["cmd"] = stripped.split(":", 1)[1].strip()
        elif current is not None and stripped.startswith("timeout:"):
            current["timeout"] = int(float(stripped.split(":", 1)[1].strip()))

    if current:
        stages.append(current)

    for stage in stages:
        if "cmd" not in stage:
            raise ValueError(f"cascade stage '{stage['name']}' missing cmd")

    return stages
