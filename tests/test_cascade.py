import os, subprocess, tempfile, pytest
from pathlib import Path

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from cascade import load_cascade_config, DEFAULT_STAGE_TIMEOUT


def test_load_cascade_config_basic(tmp_path):
    yml = tmp_path / "eval.yml"
    yml.write_text(
        "dimensions:\n"
        "  - name: quality\n"
        "    type: llm-judged\n"
        "    threshold: 3.5\n"
        "cascade:\n"
        "  - name: build\n"
        "    cmd: npm run build\n"
        "    timeout: 120\n"
        "  - name: test\n"
        "    cmd: npx vitest run\n"
    )
    stages = load_cascade_config(str(yml))
    assert stages == [
        {"name": "build", "cmd": "npm run build", "timeout": 120},
        {"name": "test", "cmd": "npx vitest run", "timeout": DEFAULT_STAGE_TIMEOUT},
    ]


def test_load_cascade_config_absent_section(tmp_path):
    yml = tmp_path / "eval.yml"
    yml.write_text("dimensions:\n  - name: quality\n    threshold: 3.5\n")
    assert load_cascade_config(str(yml)) == []


def test_load_cascade_config_missing_file():
    with pytest.raises(FileNotFoundError):
        load_cascade_config("/nonexistent/eval.yml")


def test_load_cascade_config_stage_missing_cmd(tmp_path):
    yml = tmp_path / "eval.yml"
    yml.write_text("cascade:\n  - name: build\n")
    with pytest.raises(ValueError, match="missing cmd"):
        load_cascade_config(str(yml))


def test_load_cascade_config_ignores_dimensions_after(tmp_path):
    # cascade section ends when indentation returns to column 0
    yml = tmp_path / "eval.yml"
    yml.write_text(
        "cascade:\n"
        "  - name: lint\n"
        "    cmd: ruff check .\n"
        "dimensions:\n"
        "  - name: quality\n"
        "    cmd: should-not-leak\n"
    )
    stages = load_cascade_config(str(yml))
    assert len(stages) == 1
    assert stages[0]["cmd"] == "ruff check ."
