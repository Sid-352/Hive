import os
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.integration
def test_bundled_exe_inspector_smoke():
    if os.getenv("RUN_INTEGRATION") != "1":
        pytest.skip("Set RUN_INTEGRATION=1 to run integration tests")

    if sys.platform != "win32":
        pytest.skip("Bundle smoke test currently targets win32 executable")

    candidates = [
        Path("dist_fresh") / "Hive" / "Hive.exe",
        Path("dist") / "Hive" / "Hive.exe",
    ]
    exe_path = next((p for p in candidates if p.is_file()), None)
    if exe_path is None:
        pytest.skip("Bundled Hive.exe not found under dist_fresh/Hive or dist/Hive")

    result = subprocess.run(
        [str(exe_path), "--inspector"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stdout + "\n" + result.stderr
    assert "[OK] Agent Connectivity" in result.stdout
    assert "Diagnostic complete." in result.stdout
